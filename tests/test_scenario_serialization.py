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


# Issue #28 (S3-02): incomplete and malformed documents are rejected and nothing is stored.

def _without(key):
    def change(doc):
        del doc[key]
    return change


def _set(path, value):
    def change(doc):
        target = doc
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    return change


BAD_DOCUMENTS = {
    "missing_demand": _without("demand"),
    "missing_simulation": _without("simulation"),
    "missing_network": _without("network"),
    "missing_signal_plan": _without("signal_plan"),
    "missing_schema_version": _without("schema_version"),
    "wrong_schema_version": _set(["schema_version"], "2.0"),
    "numeric_schema_version": _set(["schema_version"], 1.0),
    "network_is_list": _set(["network"], []),
    "demand_is_list": _set(["demand"], []),
    "simulation_is_string": _set(["simulation"], "fast"),
    "rates_are_list": _set(["demand", "arrival_rates_vehicles_per_hour"], []),
    "ratios_are_number": _set(["demand", "turning_ratios"], 1.0),
    "segment_length_is_string": _set(["network", "segments", 0, "length_m"], "100"),
    "lane_count_is_float": _set(["network", "segments", 0, "lane_count"], 1.5),
    "unknown_control_type": _set(["network", "intersections", 0, "control_type"], "roundabout"),
    "seed_is_string": _set(["simulation", "seed"], "42"),
    "seed_is_bool": _set(["simulation", "seed"], True),
    "duration_is_string": _set(["simulation", "duration_s"], "600"),
    "time_step_is_null": _set(["simulation", "time_step_s"], None),
    "phases_are_object": _set(["signal_plan", "phases"], {}),
}


@pytest.mark.parametrize("change", BAD_DOCUMENTS.values(), ids=BAD_DOCUMENTS.keys())
def test_incomplete_or_malformed_document_is_rejected_and_not_saved(tmp_path, change):
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    change(document)
    destination = tmp_path / "out.json"

    with pytest.raises(ScenarioFormatError) as exc:
        scenario_from_dict(document)
    assert str(exc.value)
    with pytest.raises(ScenarioFormatError):
        save_scenario_document(document, destination)
    assert list(tmp_path.iterdir()) == []  # no file, no leftover temp file


@pytest.mark.parametrize("text", ["", "   \n", "[]", '"scenario"', "42", "null"],
                         ids=["empty", "whitespace", "list", "string", "number", "null"])
def test_empty_or_non_object_json_file_is_rejected(tmp_path, text):
    source = tmp_path / "bad.json"
    source.write_text(text, encoding="utf-8")

    with pytest.raises(ScenarioFormatError, match="JSON"):
        load_scenario_document(source)
