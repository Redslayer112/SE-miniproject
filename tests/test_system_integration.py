"""Issue #33 (S3-07): system integration across network, signal, demand, engine, metrics,
store, comparison, reporting and the Workbench. Workflow ids (SI-xx) and defect ids (SI-Dx)
are defined in docs/system_integration_report.md.

Every test uses temporary storage and a fixed seed. Durations are shortened so each test
runs in a few seconds. Blocked scenarios are checked by outcome (no engine, no stored run),
not by exception class, so these tests hold with or without the S3-02 validate_scenario change.
"""
import copy
import csv
import json
import math
from dataclasses import asdict
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QMessageBox

import tms_sim.ui.app as app_module
from tms_sim.network import validate
from tms_sim.network.serialization import network_from_dict
from tms_sim.reporting import compute_metrics, export_run_csv, generate_run_csv
from tms_sim.reporting.comparison import ComparisonStatus, SimulationRunRecord, compare_runs
from tms_sim.signal import validate_signal_plan
from tms_sim.signal.serialization import plan_from_dict
from tms_sim.sim.demand import generate_vehicles
from tms_sim.sim.scenario import build_engine, engine_from_document
from tms_sim.sim.serialization import load_scenario_document, save_scenario_document, scenario_from_dict
from tms_sim.storage.store import ScenarioStore
from tms_sim.ui.app import RoadCanvas, Workbench, set_scenario_signal_plans

ROOT = Path(__file__).resolve().parents[1]
SMALL = ROOT / "fixtures" / "valid" / "small_valid_scenario.json"
PERF = ROOT / "fixtures" / "valid" / "performance_10_intersections.json"
STOP_YIELD = ROOT / "fixtures" / "valid" / "small_stop_yield_scenario.json"
TIMESTAMP = "2026-11-04T10:00:00"


def load(path, **simulation):
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["simulation"].update(simulation)
    return doc


def run_to_end(engine):
    engine.start()
    while not engine.finished:
        engine.step()
    return engine


def persist(store, engine, doc, run_id, scenario_name=None, timestamp=TIMESTAMP):
    """The Workbench capture contract (ui/app.py capture_current_run) without the UI."""
    record = SimulationRunRecord.from_engine(
        engine, scenario_name=scenario_name or doc["scenario_id"], label=run_id, run_id=run_id,
        timestamp=timestamp, scenario_snapshot=copy.deepcopy(doc), seed=doc["simulation"]["seed"],
        run_config=dict(doc["simulation"]))
    store.save_run(record.run_id, record.scenario_name, record.label, record.timestamp, record.seed,
                   record.scenario_snapshot, asdict(record.metrics), record.run_config)
    return record


def reload(store, run_id):
    return SimulationRunRecord.from_stored(store.load_run(run_id))


@pytest.fixture
def store(tmp_path):
    with ScenarioStore(tmp_path / "si.sqlite3") as s:
        yield s


# --- SI-01: network -> signal plan -> demand -> engine -> finalize ---------------------------

def test_document_builds_validated_modules_and_runs_to_duration_once():
    doc = load(SMALL, duration_s=120)
    network = network_from_dict(doc)
    plan = plan_from_dict(doc)
    assert validate(network).is_valid
    assert validate_signal_plan(plan, network).is_valid

    finished = []
    engine = build_engine(network, [plan], doc["demand"], doc["simulation"], on_finish=finished.append)
    entry_ratios = {"R2": {"TM1": 1.0}}  # TM1 leaves entry R2
    assert engine.vehicles == generate_vehicles(42, doc["demand"]["arrival_rates_vehicles_per_hour"],
                                                entry_ratios, duration_s=120)

    run_to_end(engine)
    assert engine.time == pytest.approx(120, abs=engine.p.dt)
    assert finished == [engine]
    engine.step()  # finished engine: no second finalize
    assert finished == [engine]
    assert engine.exited and all(c.route == ["R2", "R1"] for c in engine.exited)


# --- SI-03: engine events -> metrics -> store.save_run -> reload -----------------------------

def test_engine_metrics_persist_and_reload_unchanged(store):
    doc = load(SMALL, duration_s=120)
    engine = run_to_end(engine_from_document(doc))
    metrics = compute_metrics(engine)
    assert metrics.status == "Completed"
    assert metrics.vehicles_completed == len(engine.exited) > 0
    assert metrics.vehicles_entered == sum(e["type"] == "spawn" for e in engine.metric_events)

    persist(store, engine, doc, "si-03")
    stored = store.load_run("si-03")
    assert stored["metrics"] == asdict(metrics)
    assert stored["seed"] == 42
    assert stored["scenario_snapshot"] == doc
    assert stored["run_config"] == doc["simulation"]
    assert reload(store, "si-03").metrics == metrics


# --- SI-04: comparison of persisted runs -------------------------------------------------------

UNITS = {"mean_travel_time": "s", "vehicles_completed": "veh", "vehicles_in_network": "veh",
         "vehicles_entered": "veh", "vehicles_generated": "veh", "duration": "s",
         "average_speed_mps": "m/s", "throughput_vph": "veh/h", "average_delay_s": "s",
         "maximum_delay_s": "s", "queue_length_veh": "veh"}


def test_two_persisted_runs_compare_with_correct_unit_aware_differences(store):
    base_doc, cand_doc = load(SMALL, duration_s=120), load(SMALL, duration_s=120, seed=43)
    persist(store, run_to_end(engine_from_document(base_doc)), base_doc, "base")
    persist(store, run_to_end(engine_from_document(cand_doc)), cand_doc, "cand")
    base, cand = reload(store, "base"), reload(store, "cand")

    comparison = compare_runs(base, cand)
    assert comparison.duration_compatible
    for key, unit in UNITS.items():
        m = comparison.get_metric(key)
        assert m.unit == unit, key
        b, c = getattr(base.metrics, key), getattr(cand.metrics, key)
        assert (m.baseline_value, m.candidate_value) == (b, c)
        if b is None or c is None:
            assert m.status == ComparisonStatus.UNAVAILABLE
        else:
            assert m.absolute_change == round(c - b, 2), key
    queue_keys = {m.key for m in comparison.metrics if m.key.startswith("queue:")}
    assert queue_keys == {f"queue:{a}" for a in base.metrics.average_queue_length_by_approach}
    # Same scenario, different seed: the documented configuration warning, nothing else.
    assert comparison.warning == ("Scenario configurations differ; interpret metric changes with the "
                                  "configuration snapshots. Run configurations differ; interpret metric "
                                  "changes with the saved run settings.")


def test_incomplete_and_cross_scenario_comparisons_are_flagged(store):
    doc = load(SMALL, duration_s=120)
    complete = persist(store, run_to_end(engine_from_document(doc)), doc, "complete")

    partial = engine_from_document(doc)
    partial.start()
    while partial.time < 30:
        partial.step()
    metrics = compute_metrics(partial)
    assert metrics.status == "Running"
    store.save_run("partial", doc["scenario_id"], "partial", TIMESTAMP, 42, doc, asdict(metrics), doc["simulation"])

    other_doc = load(STOP_YIELD, duration_s=120)
    persist(store, run_to_end(engine_from_document(other_doc)), other_doc, "other")

    incomplete = compare_runs(reload(store, "complete"), reload(store, "partial"))
    assert "At least one run is incomplete; metric differences are provisional." in incomplete.warning
    assert all(m.status == ComparisonStatus.INCOMPATIBLE for m in incomplete.metrics)

    cross = compare_runs(complete, reload(store, "other"))
    assert "Scenario names differ; treat differences as cross-scenario results." in cross.warning
    assert cross.duration_compatible


# --- SI-05: CSV report matches compute_metrics, before and after persistence ---------------------

def csv_values(path):
    with open(path, encoding="utf-8", newline="") as f:
        return {row["Metric Key"]: row for row in csv.DictReader(f)}


def fmt(value):
    return "N/A" if value is None else f"{value:.1f}" if isinstance(value, float) else str(value)


def test_csv_export_parses_back_to_compute_metrics(store, tmp_path):
    doc = load(SMALL, duration_s=120)
    engine = run_to_end(engine_from_document(doc))
    record = persist(store, engine, doc, "csv-run")
    m = compute_metrics(engine)

    out = tmp_path / "run.csv"
    export_run_csv(reload(store, "csv-run"), out)
    rows = csv_values(out)
    expected = {
        "vehicles_generated": m.vehicles_generated, "total_scheduled": m.total_scheduled,
        "vehicles_entered": m.vehicles_entered, "vehicles_completed": m.vehicles_completed,
        "vehicles_in_network": m.vehicles_in_network, "mean_travel_time_s": m.mean_travel_time,
        "maximum_delay_s": m.maximum_delay_s, "average_delay_s": m.average_delay_s,
        "throughput_vph": m.throughput_vph, "average_speed_mps": m.average_speed_mps,
        "average_queue_length_veh": m.queue_length_veh,
    }
    for key, value in expected.items():
        assert rows[key]["Value"] == fmt(value), key
    for approach, value in m.average_queue_length_by_approach.items():
        assert rows[f"average_queue_length_veh:{approach}"]["Value"] == fmt(value)
    assert rows["run_status"]["Value"] == "Completed"
    assert rows["throughput_vph"]["Unit"] == "veh/h" and rows["mean_travel_time_s"]["Unit"] == "s"
    assert generate_run_csv(reload(store, "csv-run")) == generate_run_csv(record)  # persistence is lossless


# --- SI-06 / SI-02: Workbench driven offscreen ------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialogs(monkeypatch):
    shown = []
    for name in ("warning", "critical", "information"):
        monkeypatch.setattr(QMessageBox, name,
                            lambda *a, _n=name, **k: shown.append((_n, a[2] if len(a) > 2 else "")) or QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    return shown


@pytest.fixture
def win(qapp, tmp_path, dialogs):
    w = Workbench(SMALL)
    w.library_path = tmp_path / "workbench.sqlite3"
    w.canvas.resize(800, 600)
    yield w
    w.timer.stop()
    for name in ("comparison_dialog", "history_dialog", "library_dialog"):
        if getattr(w, name, None) is not None:
            getattr(w, name).close()
    w.set_dirty(False)
    w.close()


def run_in_workbench(w):
    w.start_simulation()
    w.engine.set_speed(4)
    for _ in range(100_000):
        if w.engine.finished:
            break
        w.advance_simulation()  # the timer callback: engine, canvas, dashboard, auto-capture
    assert w.engine.finished


def dashboard_matches(w, m):
    assert w.metric_status_label.text() == "Completed"
    assert w.vehicle_count_label.text() == str(m.vehicles_in_network)
    assert w.completed_label.text() == str(m.vehicles_completed)
    assert w.generated_label.text() == str(m.vehicles_generated)
    assert w.entered_label.text() == str(m.vehicles_entered)
    assert w.mean_travel_time_label.text() == (f"{m.mean_travel_time:.1f} s" if m.mean_travel_time is not None else "N/A")
    assert w.throughput_label.text() == (f"{m.throughput_vph:.1f} veh/h" if m.throughput_vph is not None else "Not available")
    assert w.average_speed_label.text() == (
        f"Average speed: {m.average_speed_mps:.1f} m/s" if m.average_speed_mps is not None else "Average speed: Not available")


def save_to_library(w, name, doc):
    with ScenarioStore(w.library_path) as s:
        s.save_scenario(name, doc)


def stored_runs(w):
    with ScenarioStore(w.library_path) as s:
        return [s.load_run(r["run_id"]) for r in s.list_runs()]


def test_workbench_library_run_dashboard_history_comparison_and_csv(win, tmp_path):
    save_to_library(win, "SI baseline", load(SMALL, duration_s=60))
    save_to_library(win, "SI candidate", load(SMALL, duration_s=60, seed=43))
    library = win.open_scenario_library()
    library.refresh()

    assert library.load_selected("SI baseline")
    run_in_workbench(win)
    dashboard_matches(win, compute_metrics(win.engine))
    assert len(stored_runs(win)) == 1  # auto-captured on completion

    assert library.load_selected("SI candidate")
    run_in_workbench(win)
    candidate_metrics = compute_metrics(win.engine)
    dashboard_matches(win, candidate_metrics)

    runs = stored_runs(win)
    assert [r["seed"] for r in runs] == [42, 43]
    assert runs[1]["metrics"] == asdict(candidate_metrics)
    assert runs[1]["scenario_snapshot"]["simulation"]["seed"] == 43

    history = win.open_run_history_dialog()
    assert history.table.rowCount() == 2
    assert {history.table.item(row, 1).text() for row in range(2)} == {r["label"] for r in runs}

    base_id, cand_id = runs[0]["run_id"], runs[1]["run_id"]
    comparison_dialog = win.open_comparison_dialog(base_id, cand_id)
    shown = comparison_dialog.current_comparison
    expected = compare_runs(SimulationRunRecord.from_stored(runs[0]), SimulationRunRecord.from_stored(runs[1]))
    assert (shown.baseline.run_id, shown.candidate.run_id) == (base_id, cand_id)
    assert [(m.key, m.unit, m.absolute_change, m.status) for m in shown.metrics] == [
        (m.key, m.unit, m.absolute_change, m.status) for m in expected.metrics]
    assert comparison_dialog.table.rowCount() == len(expected.metrics)

    out = tmp_path / "workbench_run.csv"
    assert win.export_current_run_csv(out)
    rows = csv_values(out)
    assert rows["vehicles_completed"]["Value"] == win.completed_label.text()
    assert rows["vehicles_in_network"]["Value"] == win.vehicle_count_label.text()
    assert rows["mean_travel_time_s"]["Value"] + " s" == win.mean_travel_time_label.text()
    assert rows["throughput_vph"]["Value"] + " veh/h" == win.throughput_label.text()


def test_run_after_library_load_is_auto_captured(win):
    save_to_library(win, "first", load(SMALL, duration_s=30))
    save_to_library(win, "second", load(SMALL, duration_s=30, seed=43))
    library = win.open_scenario_library()
    library.refresh()
    assert library.load_selected("first")
    run_in_workbench(win)
    assert library.load_selected("second")
    run_in_workbench(win)  # no Reset pressed
    assert [r["seed"] for r in stored_runs(win)] == [42, 43]


def test_run_after_network_modification_is_auto_captured(win):
    run_in_workbench(win)
    assert len(stored_runs(win)) == 1

    win.on_network_modified()
    run_in_workbench(win)

    runs = stored_runs(win)
    assert [run["seed"] for run in runs] == [42, 42]


# --- SI-02: visualization equals engine state (TC-SIM-04) ------------------------------------------

class RecordingPainter(QPainter):
    """Records what RoadCanvas.paintEvent actually draws: vehicle rectangles and fill colours of ellipses."""
    calls: list = []

    def __init__(self, *args):
        super().__init__(*args)
        self._fill = None

    def setBrush(self, brush):
        self._fill = brush.name() if isinstance(brush, QColor) else None
        super().setBrush(brush)

    def drawEllipse(self, *args):
        RecordingPainter.calls.append(("ellipse", self._fill, None))
        super().drawEllipse(*args)

    def drawRoundedRect(self, *args):
        if len(args) == 6:  # int form: vehicles and the legend box
            x, y, w, h = args[:4]
            RecordingPainter.calls.append(("rect", self._fill, (x + w / 2, y + h / 2)))
        super().drawRoundedRect(*args)


def test_canvas_draws_engine_vehicles_and_signal_states(win, monkeypatch):
    doc = load(SMALL, duration_s=60)
    doc["demand"]["arrival_rates_vehicles_per_hour"]["R2"] = 900  # enough cars on screen
    assert win.load_scenario_data(doc, "visual")
    monkeypatch.setattr(app_module, "QPainter", RecordingPainter)
    vehicle_fills = {c.name() for c in RoadCanvas.VEHICLE_COLORS}
    colour = {state: getattr(RoadCanvas, f"COLOR_{state}").name() for state in ("GREEN", "YELLOW", "RED")}
    plan = plan_from_dict(doc)
    positions = {i["id"]: i["position"] for i in doc["network"]["intersections"]}
    engine = win.engine
    engine.start()
    drawn_total = 0
    # Cycle 24 s: green 0-20, yellow 20-23, all-red 23-24. Two cycles, every state.
    for target in (10.0, 21.5, 23.5, 34.0, 45.5, 47.5):
        while engine.time < target:
            engine.step()
        RecordingPainter.calls = []
        win.canvas.grab()  # runs paintEvent offscreen
        drawn = [centre for kind, fill, centre in RecordingPainter.calls if kind == "rect" and fill in vehicle_fills]
        assert len(drawn) == len(engine.cars), target
        for centre, car in zip(drawn, engine.cars):  # drawn in engine.cars order
            seg = next(sg for sg in doc["network"]["segments"] if sg["id"] == car.route[car.leg])
            a, b = (win.canvas.scenario_to_screen(positions[seg[end]]) for end in ("from", "to"))
            f = max(0.0, min(1.0, car.x / seg["length_m"]))
            assert centre[0] == pytest.approx(a.x() + (b.x() - a.x()) * f, abs=1.0), (target, car.id)
            assert centre[1] == pytest.approx(a.y() + (b.y() - a.y()) * f, abs=1.0), (target, car.id)
        drawn_total += len(drawn)

        engine_green = engine.signals[("R2", "R1")](engine.time)
        shown = plan.movement_state("TM1", engine.time)
        assert (shown == "GREEN") == engine_green, target  # engine: only green is green
        ellipses = [fill for kind, fill, _ in RecordingPainter.calls if kind == "ellipse"]
        for state, fill in colour.items():
            # One legend dot per colour, plus the I1 badge and the R2 stop-line indicator.
            assert ellipses.count(fill) == 1 + (2 if state == shown else 0), (target, state)
    assert drawn_total > 0


# --- SI-07: determinism through the persisted path --------------------------------------------------

def test_same_scenario_and_seed_store_identical_metrics(store):
    doc = load(SMALL, duration_s=120)
    first, second = run_to_end(engine_from_document(doc)), run_to_end(engine_from_document(doc))
    assert first.metric_events == second.metric_events
    persist(store, first, doc, "det-1")
    persist(store, second, doc, "det-2")
    assert store.load_run("det-1")["metrics"] == store.load_run("det-2")["metrics"]


# --- SI-08: representative scenarios ----------------------------------------------------------------

@pytest.mark.parametrize("path, duration", [(SMALL, 600), (PERF, 120), (STOP_YIELD, 120)],
                         ids=["small_valid", "performance_10_intersections_120s", "small_stop_yield"])
def test_representative_scenario_store_run_persist(store, path, duration):
    doc = load(path, duration_s=duration)
    store.save_scenario("rep", doc)
    loaded = store.load_scenario("rep")
    assert loaded == doc
    engine = run_to_end(engine_from_document(loaded))
    assert engine.time == pytest.approx(duration, abs=engine.p.dt)
    assert engine.exited
    persist(store, engine, loaded, "rep-run")
    assert reload(store, "rep-run").metrics == compute_metrics(engine)


def test_stop_yield_scenario_yields_and_saves_without_signal_plans(tmp_path):  # SI-D1 regression
    doc = load(STOP_YIELD)
    assert doc["signal_plans"] == []
    assert scenario_from_dict(doc) == doc
    save_scenario_document(doc, tmp_path / "stop_yield.json")
    assert load_scenario_document(tmp_path / "stop_yield.json") == doc
    engine = engine_from_document(doc)
    assert engine.yields_to == {"SC": ["WC"], "WC": ["SC"], "CN": ["XN"], "XN": ["CN"]}
    assert engine.signals == {}


def test_signalized_intersection_without_plan_is_still_blocked():
    doc = load(SMALL)
    del doc["signal_plan"]
    doc["signal_plans"] = []
    scenario_from_dict(doc)  # storable ...
    with pytest.raises(Exception):  # ... but a signalized I1 with no plan cannot run
        engine_from_document(doc)


def test_removing_last_plan_in_workbench_keeps_scenario_saveable(tmp_path):
    doc = load(SMALL)
    doc["network"]["intersections"][0]["control_type"] = "stop_controlled"
    set_scenario_signal_plans(doc, [])
    save_scenario_document(doc, tmp_path / "no_plan.json")


def _zero_length(doc):
    doc["network"]["segments"][0]["length_m"] = 0


def _unknown_movement(doc):
    doc["demand"]["turning_ratios"] = {"GHOST": 1.0}


def _bad_time_step(doc):
    doc["simulation"]["time_step_s"] = 5


@pytest.mark.parametrize("break_it", [_zero_length, _unknown_movement, _bad_time_step],
                         ids=["zero_length_segment", "unknown_movement", "time_step_out_of_range"])
def test_invalid_scenario_is_blocked_and_no_run_is_stored(win, dialogs, break_it):
    bad = load(SMALL, duration_s=30)
    break_it(bad)
    with pytest.raises(Exception):
        engine_from_document(bad)

    before = copy.deepcopy(win.scenario_data)
    assert win.load_scenario_data(bad, "broken") is False
    assert any(kind == "critical" for kind, _ in dialogs)
    assert win.scenario_data == before  # the broken document was not partly loaded
    assert stored_runs(win) == []
    assert math.isfinite(win.engine.time) and win.engine.time == 0.0  # nothing ran
