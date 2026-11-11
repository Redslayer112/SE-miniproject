"""End-to-end Run Simulation flow: network (#3) + signal plan (#5) + demand (#6) -> engine (#7)."""
import copy
import json
from pathlib import Path

import pytest

from tms_sim.network import ControlType, NetworkBlockedError
from tms_sim.network.serialization import network_from_dict
from tms_sim.signal import SignalPhase, SignalPlan, SignalPlanBlockedError
from tms_sim.signal.serialization import plan_from_dict
from tms_sim.sim.demand import DemandError
from tms_sim.sim.scenario import build_engine, engine_from_document, load_scenario, phase_green
from tms_sim.sim.serialization import load_scenario_document, save_scenario_document
from tms_sim.storage.store import ScenarioStore

FIXTURE = Path(__file__).parent / "data" / "scenario" / "small_valid_scenario.json"
DOC = json.loads(FIXTURE.read_text())


def engine_from(doc):
    plans = [plan_from_dict(doc)] if doc.get("signal_plan") else []
    return build_engine(network_from_dict(doc), plans, doc["demand"], doc["simulation"])


def finish(e):
    e.start()
    while not e.finished:
        e.advance(1.0)
    return e


def test_shared_fixture_runs_to_completion():
    e = finish(load_scenario(FIXTURE))
    assert e.time == pytest.approx(600.0, abs=e.p.dt)
    assert e.p.dt == 0.1
    assert e.exited, "vehicles should complete R2 -> TM1 -> R1"
    assert all(c.route == ["R2", "R1"] for c in e.exited)


def test_same_scenario_same_seed_identical_events():  # AC-032 at engine level
    assert finish(load_scenario(FIXTURE)).events == finish(load_scenario(FIXTURE)).events


def test_no_vehicle_crosses_on_red():
    e = load_scenario(FIXTURE)  # one phase: green 20 s, yellow 3, all-red 1 -> cycle 24 s
    e.start()
    on_r2 = set()
    while not e.finished:
        now = {c.id for c in e.cars if c.leg == 0}
        e.advance(e.p.dt)
        crossed = on_r2 - {c.id for c in e.cars if c.leg == 0} - {c.id for c in e.exited}
        moved = {c.id for c in e.cars if c.leg == 1} & on_r2
        for _ in moved | crossed:
            # green 0-20 s; a car already unable to stop when it ends may still clear during yellow (20-23)
            assert (e.time - e.p.dt) % 24 < 23
        on_r2 = now | {c.id for c in e.cars if c.leg == 0}


def test_phase_green_windows():
    plan = SignalPlan("X", (SignalPhase(1, ("A",), 20, 3, 1), SignalPhase(2, ("B",), 10, 3, 1)))
    a, b = phase_green(plan, "A"), phase_green(plan, "B")
    assert a(0) and a(19.9) and not a(20) and not a(23.9)  # yellow/all-red count as red
    assert not b(23.9) and b(24) and not b(34) and a(38)  # cycle = 38 s


def test_invalid_network_blocks_the_run():  # TC-NET-03 at run start
    doc = copy.deepcopy(DOC)
    doc["network"]["segments"][0]["length_m"] = 0
    with pytest.raises(NetworkBlockedError):
        engine_from(doc)


def test_missing_signal_plan_blocks_the_run():
    doc = copy.deepcopy(DOC)
    del doc["signal_plan"]
    with pytest.raises(SignalPlanBlockedError):
        engine_from(doc)


def test_ratio_for_unknown_movement_rejected():
    doc = copy.deepcopy(DOC)
    doc["demand"]["turning_ratios"] = {"NOPE": 1.0}
    with pytest.raises(DemandError):
        engine_from(doc)


def test_stop_controlled_intersection_yields_to_conflicting_approach():
    doc = copy.deepcopy(DOC)
    net = doc["network"]
    net["intersections"] = [
        {"id": "C", "position": [0, 0], "control_type": "stop_controlled"},
        {"id": "S", "position": [0, -100]}, {"id": "N", "position": [0, 100]},
        {"id": "W", "position": [-100, 0]}, {"id": "E", "position": [100, 0]},
    ]
    seg = lambda i, a, b: {"id": i, "from": a, "to": b, "length_m": 100, "lane_count": 1, "speed_limit_mps": 13.9}
    net["segments"] = [seg("SC", "S", "C"), seg("CN", "C", "N"), seg("WC", "W", "C"), seg("CE", "C", "E"),
                       seg("NS", "N", "S"), seg("EW", "E", "W")]  # return roads keep the graph connected
    net["turning_movements"] = [
        {"id": "SN", "intersection": "C", "from_segment": "SC", "to_segment": "CN"},
        {"id": "WE", "intersection": "C", "from_segment": "WC", "to_segment": "CE"},
    ]
    del doc["signal_plan"]
    doc["demand"] = {"arrival_rates_vehicles_per_hour": {"SC": 300, "WC": 300},
                     "turning_ratios": {"SN": 1.0, "WE": 1.0}}
    e = engine_from(doc)
    assert e.yields_to == {"SC": ["WC"], "WC": ["SC"]}  # crossing movements conflict
    assert finish(e).exited


def permitted_turns_doc():
    """E -> I1 (signalized) -> S -> I2 (stop) -> O1 or O2. Only S -> O2 is a configured turn at I2,
    although O1 also leaves I2 and has the lower id."""
    seg = lambda i, a, b: {"id": i, "from": a, "to": b, "length_m": 100, "lane_count": 1, "speed_limit_mps": 13.9}
    return {
        "schema_version": "1.0",
        "network": {
            "intersections": [
                {"id": "I0", "position": [0, 0], "control_type": "uncontrolled"},
                {"id": "I1", "position": [100, 0], "control_type": "signalized"},
                {"id": "I2", "position": [200, 0], "control_type": "stop_controlled"},
                {"id": "I3", "position": [300, 0], "control_type": "yield_controlled"},
                {"id": "I4", "position": [200, 100], "control_type": "uncontrolled"},
            ],
            "segments": [seg("E", "I0", "I1"), seg("S", "I1", "I2"), seg("O1", "I2", "I3"), seg("O2", "I2", "I4")],
            "turning_movements": [
                {"id": "TM_A", "intersection": "I1", "from_segment": "E", "to_segment": "S"},
                {"id": "TM_B", "intersection": "I2", "from_segment": "S", "to_segment": "O2"},
            ],
        },
        "signal_plan": {"intersection_id": "I1",
                        "phases": [{"order": 1, "movement_ids": ["TM_A"], "green_s": 20, "yellow_s": 3, "all_red_s": 1}]},
        "demand": {"arrival_rates_vehicles_per_hour": {"E": 600}, "turning_ratios": {"TM_A": 1.0}},
        "simulation": {"seed": 7, "duration_s": 300, "time_step_s": 0.5},
    }


def test_only_configured_turning_movements_are_used_in_a_run():  # TC-NET-02, TMS-F-011
    e = finish(engine_from_document(permitted_turns_doc()))
    assert set(map(tuple, e.routes.values())) == {("E", "S", "O2")}
    assert e.exited
    assert all(c.route == ["E", "S", "O2"] for c in e.exited + e.cars)  # nobody takes the unconfigured S -> O1


def test_control_types_survive_save_and_reload(tmp_path):  # TC-NET-02, TMS-F-011
    doc = permitted_turns_doc()
    expected = {"I0": ControlType.UNCONTROLLED, "I1": ControlType.SIGNALIZED,
                "I2": ControlType.STOP_CONTROLLED, "I3": ControlType.YIELD_CONTROLLED, "I4": ControlType.UNCONTROLLED}
    f = tmp_path / "turns.json"
    save_scenario_document(doc, f)
    from_file = load_scenario_document(f)
    with ScenarioStore(tmp_path / "lib.sqlite3") as store:
        store.save_scenario("turns", doc)
    with ScenarioStore(tmp_path / "lib.sqlite3") as store:
        from_store = store.load_scenario("turns")
    for reloaded in (from_file, from_store):
        assert reloaded == doc
        net = network_from_dict(reloaded)
        assert {i.id: i.control_type for i in net.intersections} == expected
        assert [(m.id, m.from_segment, m.to_segment) for m in net.turning_movements] == [
            ("TM_A", "E", "S"), ("TM_B", "S", "O2")]
        assert finish(engine_from_document(reloaded)).exited
