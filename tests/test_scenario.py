"""End-to-end Run Simulation flow: network (#3) + signal plan (#5) + demand (#6) -> engine (#7)."""
import copy
import json
from pathlib import Path

import pytest

from tms_sim.network import NetworkBlockedError
from tms_sim.network.serialization import network_from_dict
from tms_sim.signal import SignalPhase, SignalPlan, SignalPlanBlockedError
from tms_sim.signal.serialization import plan_from_dict
from tms_sim.sim.demand import DemandError
from tms_sim.sim.scenario import build_engine, load_scenario, phase_green

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
