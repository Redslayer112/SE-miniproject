import json
from pathlib import Path

import pytest

from tms_sim.signal.validation import validate_signal_plan
from tms_sim.network.serialization import network_from_dict
from tms_sim.network.validation import validate
from tms_sim.signal.serialization import plan_from_dict
from tms_sim.sim.demand import DemandError, validate_demand
from tms_sim.sim.serialization import scenario_from_dict

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
INVALID = FIXTURES / "invalid"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "name",
    [
        "disconnected_network.json",
        "zero_length_segment.json",
        "zero_lane_segment.json",
        "missing_receiving_lane.json",
    ],
)
def test_reference_network_fixtures_are_rejected(name):
    data = read_json(INVALID / name)
    result = validate(network_from_dict(data))
    assert not result.is_valid, name



def test_invalid_signal_timing_fixture_is_rejected(network):
    data = read_json(INVALID / "invalid_signal_plan.json")
    plan = plan_from_dict(data)
    result = validate_signal_plan(plan, network)

    assert not result.is_valid
    assert any(issue.code == "INVALID_GREEN" for issue in result.errors)


def test_conflicting_signal_plan_fixture_is_rejected(network):
    data = read_json(INVALID / "conflicting_signal_plan.json")

    # Adapt the fixture to the shared test network.
    data["signal_plan"]["intersection_id"] = "X"

    plan = plan_from_dict(data)
    result = validate_signal_plan(plan, network)

    assert any(
        issue.code == "CONFLICTING_MOVEMENTS"
        for issue in result.errors
    )


def test_invalid_demand_fixture_is_rejected():
    data = read_json(INVALID / "invalid_demand.json")
    demand = data["demand"]

    with pytest.raises(DemandError):
        validate_demand(
            demand["arrival_rates_vehicles_per_hour"],
            {"R2": demand["turning_ratios"]},
        )


def test_malformed_import_fixture_is_invalid_json():
    path = INVALID / "malformed_import.json"

    with pytest.raises(json.JSONDecodeError):
        read_json(path)


def test_valid_reference_scenario_is_accepted():
    data = read_json(FIXTURES / "valid" / "small_valid_scenario.json")
    assert scenario_from_dict(data)
