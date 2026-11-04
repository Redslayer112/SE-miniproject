"""Issue #28 (S3-02): scenario-level validation, one result with every problem, checked before a run."""
import copy
import json
from pathlib import Path

import pytest

from tms_sim.network.serialization import network_from_dict
from tms_sim.signal.serialization import plan_from_dict
from tms_sim.sim.demand import DemandError
from tms_sim.sim.scenario import build_engine, validate_scenario

FIXTURE = Path(__file__).parent / "data" / "scenario" / "small_valid_scenario.json"
DOC = json.loads(FIXTURE.read_text())


def check(doc):
    return validate_scenario(network_from_dict(doc), doc["demand"], doc["simulation"])


def run(doc):
    return build_engine(network_from_dict(doc), [plan_from_dict(doc)], doc["demand"], doc["simulation"])


def issues(result):
    return {(i.code, i.element_type, i.element_id, i.severity) for i in result.issues}


def test_reference_scenario_is_valid():
    assert check(DOC).issues == []


@pytest.mark.parametrize("path, value, expected", [
    (("simulation", "time_step_s"), 0.05, ("INVALID_TIME_STEP", "simulation", "time_step_s")),
    (("simulation", "time_step_s"), 1.5, ("INVALID_TIME_STEP", "simulation", "time_step_s")),
    (("simulation", "time_step_s"), "0.5", ("INVALID_TIME_STEP", "simulation", "time_step_s")),
    (("simulation", "duration_s"), 0, ("INVALID_DURATION", "simulation", "duration_s")),
    (("simulation", "duration_s"), -10, ("INVALID_DURATION", "simulation", "duration_s")),
    (("simulation", "seed"), "42", ("INVALID_SEED", "simulation", "seed")),
    (("simulation", "seed"), 4.2, ("INVALID_SEED", "simulation", "seed")),
    (("simulation", "seed"), True, ("INVALID_SEED", "simulation", "seed")),
    (("demand", "turning_ratios"), {"TM1": 0.5}, ("TURNING_RATIO_SUM", "segment", "R2")),
    (("demand", "turning_ratios"), {"TM1": 1.0, "GHOST": 0.0}, ("UNKNOWN_MOVEMENT", "turning_movement", "GHOST")),
    (("demand", "arrival_rates_vehicles_per_hour"), {"R2": 180, "R9": 60},
     ("UNKNOWN_ENTRY_SEGMENT", "segment", "R9")),
])
def test_each_blocking_code(path, value, expected):
    doc = copy.deepcopy(DOC)
    doc[path[0]][path[1]] = value
    result = check(doc)
    assert not result.is_valid
    assert expected + ("error",) in issues(result)
    assert all(i.message for i in result.issues)
    with pytest.raises(DemandError) as exc:  # blocked before any engine work
        run(doc)
    assert expected in {(i.code, i.element_type, i.element_id) for i in exc.value.issues}
    assert any(expected[2] in m for m in exc.value.errors)


def test_ratio_sum_within_tolerance_is_accepted():
    doc = copy.deepcopy(DOC)
    doc["demand"]["turning_ratios"] = {"TM1": 1.0 + 5e-7}
    assert check(doc).is_valid


def test_entry_that_is_not_a_network_entry_is_a_warning_only():
    doc = copy.deepcopy(DOC)
    # R1 is fed by TM1 (R2 -> R1), so it is not where traffic enters the network.
    doc["network"]["turning_movements"].append(
        {"id": "TM2", "intersection": "I2", "from_segment": "R1", "to_segment": "R2"})
    doc["demand"] = {"arrival_rates_vehicles_per_hour": {"R2": 180, "R1": 60},
                     "turning_ratios": {"TM1": 1.0, "TM2": 1.0}}
    result = check(doc)
    assert result.is_valid
    assert {(w.code, w.element_id) for w in result.warnings} == {("NOT_NETWORK_ENTRY", "R1"), ("NOT_NETWORK_ENTRY", "R2")}
    assert run(doc) is not None  # warnings never block a run


def test_every_problem_reported_at_once():
    doc = copy.deepcopy(DOC)
    doc["simulation"] = {"seed": "x", "duration_s": 0, "time_step_s": 2}
    doc["demand"] = {"arrival_rates_vehicles_per_hour": {"R2": 180, "NOPE": 10},
                     "turning_ratios": {"TM1": 0.3, "GHOST": 0.7}}
    codes = {i.code for i in check(doc).errors}
    assert {"INVALID_SEED", "INVALID_DURATION", "INVALID_TIME_STEP", "UNKNOWN_ENTRY_SEGMENT",
            "UNKNOWN_MOVEMENT", "TURNING_RATIO_SUM"} <= codes
    with pytest.raises(DemandError) as exc:
        run(doc)
    assert {i.code for i in exc.value.issues} == codes


def test_non_object_demand_parts_are_reported():
    result = validate_scenario(network_from_dict(DOC), {"arrival_rates_vehicles_per_hour": []}, DOC["simulation"])
    assert ("INVALID_DEMAND", "demand", "", "error") in issues(result)


def test_time_step_error_is_still_a_value_error():  # callers that caught the old bare ValueError still work
    doc = copy.deepcopy(DOC)
    doc["simulation"]["time_step_s"] = 5
    with pytest.raises(ValueError, match="time_step_s"):
        run(doc)
