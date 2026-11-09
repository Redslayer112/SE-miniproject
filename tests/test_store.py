"""Scenario Store (#9): TC-NET-04 round trip, TC-LIB-01 CRUD + restart persistence, safe import."""
import copy
import json
import sqlite3
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


def test_store_constructor_closes_connection_if_schema_setup_fails(tmp_path, monkeypatch):
    import tms_sim.storage.store as store_module

    db_path = tmp_path / "broken-schema.sqlite3"
    connections = []
    connect = sqlite3.connect

    def tracked_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(store_module.sqlite3, "connect", tracked_connect)
    monkeypatch.setattr(store_module, "_SCHEMA", "CREATE TABLE partial (value); INVALID SQL;")

    with pytest.raises(sqlite3.OperationalError):
        ScenarioStore(db_path)

    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connections[0].execute("SELECT 1")
    db_path.unlink()


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

def test_run_record_round_trip_preserves_metadata_and_metrics(store):
    scenario_snapshot = copy.deepcopy(DOC)
    metrics = {
        "mean_travel_time": 16.4,
        "vehicles_generated": 30,
        "vehicles_entered": 30,
        "vehicles_completed": 30,
        "vehicles_in_network": 0,
    }

    store.save_run(
        run_id="run_round_trip",
        scenario_name="Test Scenario",
        label="Baseline Run",
        timestamp="2026-10-29T10:00:00",
        seed=42,
        scenario_snapshot=scenario_snapshot,
        metrics=metrics,
        run_config={"duration_s": 600.0, "time_step_s": 0.5},
    )

    restored = store.load_run("run_round_trip")

    assert restored["run_id"] == "run_round_trip"
    assert restored["scenario_name"] == "Test Scenario"
    assert restored["label"] == "Baseline Run"
    assert restored["timestamp"] == "2026-10-29T10:00:00"
    assert restored["seed"] == 42
    assert restored["scenario_snapshot"] == scenario_snapshot
    assert restored["metrics"] == metrics
    assert restored["run_config"] == {"duration_s": 600.0, "time_step_s": 0.5}


def test_completed_run_round_trips_after_store_reopen(tmp_path):
    db_path = tmp_path / "run-history.sqlite3"
    scenario_snapshot = copy.deepcopy(DOC)
    run_config = {"duration_s": 600.0, "time_step_s": 0.5, "speed_multiplier": 1}
    metrics = {
        "status": "Completed",
        "simulated_time": 600.0,
        "duration": 600.0,
        "vehicles_generated": 30,
        "total_scheduled": 30,
        "vehicles_entered": 30,
        "vehicles_completed": 30,
        "vehicles_in_network": 0,
        "mean_travel_time": 16.4,
        "average_speed_mps": 8.7,
        "throughput_vph": 180.0,
        "average_delay_s": 2.2,
        "maximum_delay_s": 6.0,
        "queue_length_veh": 1.5,
        "average_queue_length_by_approach": {"R1": 0.5, "R2": 1.0},
    }

    with ScenarioStore(db_path) as first_store:
        first_store.save_run(
            run_id="run_persists_after_reopen",
            scenario_name="Persistence Scenario",
            label="Completed Run",
            timestamp="2026-10-29T10:00:00",
            seed=42,
            scenario_snapshot=scenario_snapshot,
            metrics=metrics,
            run_config=run_config,
        )

    with ScenarioStore(db_path) as second_store:
        assert second_store is not first_store
        restored = second_store.load_run("run_persists_after_reopen")

        assert restored["run_id"] == "run_persists_after_reopen"
        assert restored["scenario_name"] == "Persistence Scenario"
        assert restored["label"] == "Completed Run"
        assert restored["timestamp"] == "2026-10-29T10:00:00"
        assert restored["seed"] == 42
        assert restored["scenario_snapshot"] == scenario_snapshot
        assert restored["scenario_snapshot"]["simulation"]["seed"] == 42
        assert restored["run_config"] == run_config
        assert restored["metrics"] == metrics
        assert restored["metrics"]["status"] == "Completed"
        assert restored["metrics"]["mean_travel_time"] == 16.4
        assert restored["metrics"]["average_queue_length_by_approach"] == {
            "R1": 0.5,
            "R2": 1.0,
        }


def test_malformed_saved_run_is_reported_as_store_error(store):
    store.save_run("bad-json", "Scenario", "Broken", "2026-10-29T00:00:00", 42,
                   DOC, {"vehicles_completed": 0}, {"duration_s": 10.0})
    store._db.execute("UPDATE runs SET metrics = ? WHERE run_id = ?", ("{broken", "bad-json"))
    with pytest.raises(ScenarioStoreError, match="unreadable"):
        store.load_run("bad-json")


def test_non_json_run_data_is_refused(store):
    with pytest.raises(ScenarioStoreError, match="Could not save run"):
        store.save_run("nan", "Scenario", "Bad", "2026-10-29T00:00:00", 1,
                       DOC, {"bad": float("nan")})


def test_existing_run_database_is_migrated_with_empty_run_config(tmp_path):
    db = tmp_path / "old-library.sqlite3"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, scenario_name TEXT NOT NULL, label TEXT NOT NULL, timestamp TEXT NOT NULL, seed INTEGER, scenario_snapshot TEXT NOT NULL, metrics TEXT NOT NULL)")
    connection.commit()
    connection.close()
    with ScenarioStore(db) as upgraded:
        upgraded.save_run("new", "Scenario", "New", "2026-10-29T12:00:00", 1,
                          DOC, {"vehicles_completed": 0}, {"duration_s": 20.0})
        assert upgraded.load_run("new")["run_config"] == {"duration_s": 20.0}


@pytest.mark.parametrize("text", [
    "",
    "[]",
    json.dumps({k: v for k, v in DOC.items() if k != "demand"}),
    json.dumps({k: v for k, v in DOC.items() if k != "simulation"}),
    json.dumps({k: v for k, v in DOC.items() if k != "network"}),
    json.dumps({**DOC, "schema_version": "2.0"}),
    json.dumps({**DOC, "simulation": {**DOC["simulation"], "seed": "42"}}),
    json.dumps({**DOC, "demand": []}),
], ids=["empty", "non_object", "no_demand", "no_simulation", "no_network", "wrong_version", "seed_string",
        "demand_list"])
def test_incomplete_import_is_rejected_with_nothing_stored(store, tmp_path, text):  # Issue #28
    f = tmp_path / "bad.json"
    f.write_text(text, encoding="utf-8")
    with pytest.raises(ScenarioFormatError):
        store.import_scenario(f)
    if text.startswith("{"):
        with pytest.raises(ScenarioFormatError):
            store.save_scenario("bad", json.loads(text))
    assert store.list_scenarios() == []
