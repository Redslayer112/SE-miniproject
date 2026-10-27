"""Scenario Store (#9): TC-NET-04 round trip, TC-LIB-01 CRUD + restart persistence, safe import."""
import copy
import json
from pathlib import Path

import pytest

from tms_sim.sim.scenario import engine_from_document
from tms_sim.sim.serialization import ScenarioFormatError
from tms_sim.storage.store import ScenarioStore, ScenarioStoreError

ROOT = Path(__file__).parent.parent
VALID = ROOT / "fixtures" / "valid" / "small_valid_scenario.json"
DOC = json.loads(VALID.read_text())


@pytest.fixture
def store(tmp_path):
    with ScenarioStore(tmp_path / "lib.sqlite3") as s:
        yield s


def test_save_list_load(store):
    store.save_scenario("B", DOC)
    store.save_scenario("a", DOC)
    assert store.list_scenarios() == ["a", "B"]  # case-insensitive order
    assert store.load_scenario("a") == DOC


def test_loaded_scenario_runs(store):
    store.save_scenario("demo", DOC)
    e = engine_from_document(store.load_scenario("demo"))
    e.start()
    while not e.finished:
        e.advance(1.0)
    assert e.exited


def test_survives_restart(tmp_path):  # AC-060: persists across restarts
    db = tmp_path / "lib.sqlite3"
    with ScenarioStore(db) as s:
        s.save_scenario("kept", DOC)
        s.save_scenario("gone", DOC)
        s.rename_scenario("kept", "renamed")
        s.delete_scenario("gone")
    with ScenarioStore(db) as s:
        assert s.list_scenarios() == ["renamed"]
        assert s.load_scenario("renamed") == DOC


def test_duplicate_and_rename(store):
    store.save_scenario("orig", DOC)
    store.duplicate_scenario("orig", "copy")
    store.rename_scenario("copy", "moved")
    assert store.list_scenarios() == ["moved", "orig"]


def test_refuses_name_clash_unless_overwrite(store):
    store.save_scenario("x", DOC)
    changed = copy.deepcopy(DOC)
    changed["simulation"]["seed"] = 7
    with pytest.raises(ScenarioStoreError, match="already exists"):
        store.save_scenario("x", changed)
    assert store.load_scenario("x")["simulation"]["seed"] == 42  # untouched
    store.save_scenario("x", changed, overwrite=True)
    assert store.load_scenario("x")["simulation"]["seed"] == 7
    store.save_scenario("y", DOC)
    with pytest.raises(ScenarioStoreError, match="already exists"):
        store.rename_scenario("y", "x")


@pytest.mark.parametrize("op", [
    lambda s: s.load_scenario("nope"),
    lambda s: s.delete_scenario("nope"),
    lambda s: s.rename_scenario("nope", "z"),
    lambda s: s.duplicate_scenario("nope", "z"),
    lambda s: s.save_scenario("   ", DOC),
    lambda s: s.save_scenario("x" * 101, DOC),
])
def test_actionable_errors(store, op):
    with pytest.raises(ScenarioStoreError):
        op(store)


def test_export_import_round_trip(store, tmp_path):  # AC-013
    store.save_scenario("src", DOC)
    out = tmp_path / "exported.json"
    store.export_scenario("src", out)
    with ScenarioStore(tmp_path / "clean.sqlite3") as clean:  # "clean install"
        assert clean.import_scenario(out) == "exported"
        assert clean.load_scenario("exported") == DOC


@pytest.mark.parametrize("bad", ["malformed_import.json"])
def test_malformed_file_rejected_with_nothing_stored(store, bad):
    with pytest.raises(ScenarioFormatError):
        store.import_scenario(ROOT / "fixtures" / "invalid" / bad)
    assert store.list_scenarios() == []


def test_unsupported_version_rejected(store, tmp_path):
    doc = copy.deepcopy(DOC)
    doc["schema_version"] = "9.9"
    f = tmp_path / "future.json"
    f.write_text(json.dumps(doc))
    with pytest.raises(ScenarioFormatError, match="schema_version"):
        store.import_scenario(f)
    with pytest.raises(ScenarioFormatError):
        store.save_scenario("future", doc)
    assert store.list_scenarios() == []


def test_run_records_keep_their_own_snapshot(store):  # contract for #10 / AC-052
    store.save_scenario("s", DOC)
    store.save_run("r1", "s", "baseline", "2026-10-27T10:00:00", 42, DOC, {"throughput": 30, "avg_delay_s": 1.5})
    store.delete_scenario("s")
    run = store.load_run("r1")
    assert run["scenario_snapshot"] == DOC and run["metrics"]["throughput"] == 30
    assert [r["run_id"] for r in store.list_runs("s")] == ["r1"]
    with pytest.raises(ScenarioStoreError):
        store.load_run("missing")
