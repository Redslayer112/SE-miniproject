import json
from pathlib import Path

import pytest

from tms_sim.sim.serialization import (
    ScenarioFormatError,
    load_scenario_document,
    save_scenario_document,
    scenario_from_dict,
    scenario_to_dict,
)


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "valid"
    / "small_valid_scenario.json"
)


def test_scenario_dict_round_trip():
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))

    loaded = scenario_from_dict(original)
    exported = scenario_to_dict(loaded)

    assert exported == original


def test_scenario_file_round_trip(tmp_path):
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    destination = tmp_path / "saved_scenario.json"

    save_scenario_document(original, destination)
    loaded = load_scenario_document(destination)

    assert loaded == original


def test_missing_schema_version_is_rejected():
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    original.pop("schema_version")

    with pytest.raises(ScenarioFormatError):
        scenario_from_dict(original)


def test_unsupported_schema_version_is_rejected():
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    original["schema_version"] = "99.0"

    with pytest.raises(ScenarioFormatError):
        scenario_from_dict(original)


def test_missing_demand_is_rejected():
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    original.pop("demand")

    with pytest.raises(ScenarioFormatError):
        scenario_from_dict(original)


def test_both_signal_plan_formats_are_rejected_together():
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    original["signal_plans"] = [original["signal_plan"]]

    with pytest.raises(ScenarioFormatError):
        scenario_from_dict(original)


def test_malformed_json_file_is_rejected(tmp_path):
    malformed_file = tmp_path / "malformed.json"
    malformed_file.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(ScenarioFormatError):
        load_scenario_document(malformed_file)


def test_invalid_scenario_does_not_overwrite_existing_file(tmp_path):
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    destination = tmp_path / "scenario.json"

    save_scenario_document(original, destination)
    original_content = destination.read_text(encoding="utf-8")

    invalid = dict(original)
    invalid.pop("schema_version")

    with pytest.raises(ScenarioFormatError):
        save_scenario_document(invalid, destination)

    assert destination.read_text(encoding="utf-8") == original_content


def test_multiple_signal_plans_round_trip():
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    original["signal_plans"] = [original.pop("signal_plan")]

    assert scenario_to_dict(scenario_from_dict(original)) == original


def test_missing_simulation_field_is_rejected():
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    del original["simulation"]["time_step_s"]

    with pytest.raises(ScenarioFormatError):
        scenario_from_dict(original)
