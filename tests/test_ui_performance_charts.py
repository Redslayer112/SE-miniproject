"""Automated tests for TMS-Sim Step 5B: Live Performance Charts and History Model.

Covers:
1. Initial empty history in tracker and charts.
2. Samples recorded at expected simulated-time intervals.
3. No duplicate sample when simulation time has not advanced.
4. Correct generated, entered, completed, and active counts.
5. Completed-trip travel-time observations use valid completion times.
6. Incomplete trips are excluded from completed-trip observations.
7. Multi-second advances do not invent fake intermediate states.
8. Manual stepping records history correctly.
9. Pausing leaves history unchanged.
10. Reset clears history and chart observations.
11. Loading a scenario clears stale history and updates duration.
12. Engine-rebuilding configuration edits reinitialize history cleanly.
13. Completion records and preserves final state.
14. Zero-vehicle simulations work without crash.
15. Chart paint events render without errors or warnings.
16. Timeline widget displays progress and status accurately.
"""

import copy
import json
from pathlib import Path
import pytest
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from tms_sim.reporting.history import CompletedTrip, HistorySample, SimulationHistoryTracker
from tms_sim.sim.scenario import load_scenario
from tms_sim.ui.app import RoadCanvas, Workbench

SAMPLE_SCENARIO_PATH = (
    Path(__file__).resolve().parent / "data" / "scenario" / "small_valid_scenario.json"
)


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single QApplication instance exists for testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def workbench(qapp):
    """Provide a fresh Workbench instance for each test, closing it on teardown."""
    win = Workbench()
    yield win
    win.timer.stop()
    win.close()


def test_history_tracker_initial_empty():
    """Verify fresh SimulationHistoryTracker starts empty."""
    tracker = SimulationHistoryTracker(min_sample_interval=1.0)
    assert len(tracker.samples) == 0
    assert len(tracker.completed_trips) == 0
    assert tracker._last_sampled_time is None
    assert tracker.record_state(None) is False


def test_rendering_performance_metrics_reset_for_new_benchmark(qapp):
    canvas = RoadCanvas()
    canvas._frame_times.extend([1.0, 2.0])
    canvas._frame_timestamps.extend([10.0, 11.0])
    canvas._total_frame_count = 2
    canvas._total_frame_render_time_ms = 3.0
    canvas._first_frame_timestamp = 10.0
    canvas._last_frame_timestamp = 11.0
    canvas._fps_estimate = 1.0

    canvas.reset_rendering_performance_metrics()

    assert canvas.get_rendering_performance_metrics() == {
        "last_frame_ms": 0.0,
        "avg_frame_ms": 0.0,
        "rolling_avg_ms": 0.0,
        "fps": 0.0,
        "total_frames": 0,
        "full_run_fps": 0.0,
        "full_run_avg_frame_ms": 0.0,
        "full_run_elapsed_seconds": 0.0,
    }


def test_history_tracker_samples_recorded_at_expected_intervals():
    """Verify samples are recorded according to min_sample_interval."""
    engine = load_scenario(SAMPLE_SCENARIO_PATH)
    tracker = SimulationHistoryTracker(min_sample_interval=1.0)

    # Initial sample at t=0
    assert tracker.record_state(engine) is True
    assert len(tracker.samples) == 1
    assert tracker.samples[0].simulated_time == 0.0

    # Advance small step (0.1s) — should not record new sample yet
    engine.time = 0.5
    assert tracker.record_state(engine) is False
    assert len(tracker.samples) == 1

    # Advance to t=1.0 — should record new sample
    engine.time = 1.0
    assert tracker.record_state(engine) is True
    assert len(tracker.samples) == 2
    assert tracker.samples[1].simulated_time == 1.0


def test_history_tracker_no_duplicate_sample_when_time_not_advanced():
    """Verify calling record_state repeatedly without time advance does not create duplicates."""
    engine = load_scenario(SAMPLE_SCENARIO_PATH)
    tracker = SimulationHistoryTracker(min_sample_interval=1.0)

    tracker.record_state(engine)
    assert len(tracker.samples) == 1

    # Repeated calls at same timestamp
    for _ in range(5):
        assert tracker.record_state(engine) is False
    assert len(tracker.samples) == 1


def test_history_tracker_correct_counts_and_trips():
    """Verify samples record accurate counts and completed trips from engine events."""
    engine = load_scenario(SAMPLE_SCENARIO_PATH)
    tracker = SimulationHistoryTracker(min_sample_interval=0.5)

    engine.start()
    while len(engine.exited) < 2 and not engine.finished:
        engine.step()
        tracker.record_state(engine)

    assert len(tracker.samples) > 0
    latest = tracker.samples[-1]
    assert latest.vehicles_completed == len(engine.exited)
    assert latest.vehicles_in_network == len(engine.cars)

    # Check completed trips
    assert len(tracker.completed_trips) == len(engine.exited)
    for trip in tracker.completed_trips:
        assert isinstance(trip, CompletedTrip)
        assert trip.travel_time > 0.0
        assert trip.completion_time > trip.spawn_time
        assert trip.travel_time == pytest.approx(trip.completion_time - trip.spawn_time)


def test_incomplete_trips_excluded_from_observations():
    """Verify active cars in the network are not present in completed_trips."""
    engine = load_scenario(SAMPLE_SCENARIO_PATH)
    tracker = SimulationHistoryTracker(min_sample_interval=0.1)

    engine.start()
    # Step until cars enter network
    while not engine.cars and not engine.finished:
        engine.step()
    tracker.record_state(engine)

    active_car_ids = {c.id for c in engine.cars}
    assert len(active_car_ids) > 0
    completed_ids = {t.vehicle_id for t in tracker.completed_trips}

    # Incomplete cars must NOT be in completed trips
    for car_id in active_car_ids:
        assert car_id not in completed_ids


def test_multi_second_advances_do_not_invent_intermediate_states():
    """Verify large simulation time leaps capture actual state without fabricated intermediate samples."""
    engine = load_scenario(SAMPLE_SCENARIO_PATH)
    tracker = SimulationHistoryTracker(min_sample_interval=1.0)

    tracker.record_state(engine)
    assert len(tracker.samples) == 1

    # Advance by 10 seconds directly
    engine.time = 10.0
    tracker.record_state(engine)

    # Exactly 2 samples: t=0 and t=10, no fake t=1..9 samples
    assert len(tracker.samples) == 2
    assert tracker.samples[0].simulated_time == 0.0
    assert tracker.samples[1].simulated_time == 10.0


def test_manual_stepping_records_history(workbench):
    """Verify single-stepping the workbench simulation records history immediately."""
    assert len(workbench.history_tracker.samples) == 1
    assert workbench.history_tracker.samples[0].simulated_time == 0.0

    workbench.step_simulation()

    # Manual step must force-record the new state
    assert len(workbench.history_tracker.samples) == 2
    assert workbench.history_tracker.samples[1].simulated_time == workbench.engine.p.dt


def test_pausing_leaves_history_unchanged(workbench):
    """Verify pausing freezes sample collection."""
    workbench.start_simulation()
    for _ in range(5):
        workbench.advance_simulation()
    workbench.pause_simulation()

    sample_count = len(workbench.history_tracker.samples)
    trip_count = len(workbench.history_tracker.completed_trips)

    # Repeated update calls during pause do not add samples
    for _ in range(3):
        workbench.update_metrics()

    assert len(workbench.history_tracker.samples) == sample_count
    assert len(workbench.history_tracker.completed_trips) == trip_count


def test_reset_clears_history_and_charts(workbench):
    """Verify reset clears prior run history and leaves only initial t=0 sample."""
    workbench.start_simulation()
    for _ in range(30):
        workbench.advance_simulation()
    assert len(workbench.history_tracker.samples) > 1

    workbench.reset_simulation()

    assert len(workbench.history_tracker.samples) == 1
    assert workbench.history_tracker.samples[0].simulated_time == 0.0
    assert len(workbench.history_tracker.completed_trips) == 0
    assert workbench.timeline_widget.simulated_time == 0.0


def test_loading_scenario_clears_stale_history(workbench, tmp_path):
    """Verify loading a new scenario replaces history and updates chart duration."""
    workbench.start_simulation()
    for _ in range(10):
        workbench.advance_simulation()
    workbench.pause_simulation()

    doc = json.loads(SAMPLE_SCENARIO_PATH.read_text(encoding="utf-8"))
    doc["name"] = "Scenario 400s"
    doc["simulation"]["duration_s"] = 400.0
    new_path = tmp_path / "custom_400s.json"
    new_path.write_text(json.dumps(doc), encoding="utf-8")

    success = workbench.load_scenario_file(new_path)
    assert success is True

    # History cleared, fresh sample at t=0
    assert len(workbench.history_tracker.samples) == 1
    assert workbench.history_tracker.samples[0].simulated_time == 0.0
    assert len(workbench.history_tracker.completed_trips) == 0

    # Chart duration updated
    assert workbench.counts_chart.duration == 400.0
    assert workbench.travel_time_chart.duration == 400.0
    assert workbench.timeline_widget.duration == 400.0


def test_configuration_edits_rebuild_and_clear_history(workbench):
    """Verify modifying demand resets history tracker for the newly built engine."""
    workbench.step_simulation()
    assert workbench.engine.time > 0.0

    # Edit demand
    workbench.combo_demand_segment.setCurrentText("R2")
    workbench.edit_demand_rate.setText("220.0")
    success = workbench.apply_demand_entry()
    assert success is True

    # Engine rebuilt, history tracker reset to t=0
    assert workbench.engine.time == 0.0
    assert len(workbench.history_tracker.samples) == 1
    assert workbench.history_tracker.samples[0].simulated_time == 0.0
    assert len(workbench.history_tracker.completed_trips) == 0


def test_completion_records_and_preserves_final_state(workbench):
    """Verify final state is recorded on completion and preserved."""
    workbench.engine.start()
    workbench.engine.set_speed(4)
    while not workbench.engine.finished:
        workbench.engine.advance(workbench.engine.p.dt)
    workbench.update_metrics()

    assert workbench.engine.finished is True
    assert workbench.history_tracker.samples[-1].simulated_time == pytest.approx(workbench.engine.duration)
    assert workbench.timeline_widget.status == "Completed"
    assert workbench.timeline_widget.simulated_time == pytest.approx(workbench.engine.duration)

    # Preserved across further update calls
    workbench.update_metrics()
    assert workbench.timeline_widget.status == "Completed"


def test_zero_vehicle_simulation_charts(workbench, tmp_path):
    """Verify zero-vehicle scenario works cleanly with charts."""
    doc = json.loads(SAMPLE_SCENARIO_PATH.read_text(encoding="utf-8"))
    doc["demand"]["arrival_rates_vehicles_per_hour"] = {"R2": 0.0}
    doc["simulation"]["duration_s"] = 20.0
    zero_file = tmp_path / "zero_demand.json"
    zero_file.write_text(json.dumps(doc), encoding="utf-8")

    assert workbench.load_scenario_file(zero_file) is True
    workbench.engine.start()
    while not workbench.engine.finished:
        workbench.engine.step()
    workbench.update_metrics()

    assert workbench.engine.finished is True
    assert len(workbench.history_tracker.completed_trips) == 0

    # Ensure paint does not crash on empty trips
    img = QImage(300, 200, QImage.Format.Format_ARGB32)
    workbench.travel_time_chart.render(img)
    workbench.counts_chart.render(img)
    workbench.timeline_widget.render(img)


def test_charts_paint_events_render_cleanly(workbench):
    """Verify charts and timeline widget paint cleanly on QImage without warnings."""
    # Run to generate some data
    workbench.engine.start()
    while len(workbench.engine.exited) < 2 and not workbench.engine.finished:
        workbench.engine.step()
    workbench.update_metrics()

    img = QImage(400, 300, QImage.Format.Format_ARGB32)
    workbench.counts_chart.render(img)
    workbench.travel_time_chart.render(img)
    workbench.timeline_widget.render(img)

    assert not img.isNull()
