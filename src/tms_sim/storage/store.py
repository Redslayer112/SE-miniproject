"""Scenario Store (SAD §3.4/§4.3 Interface 5; TMS-F-013, TMS-F-060, TMS-F-052 contract).

Local library in one SQLite file (issue #1 item 5), using only the stdlib sqlite3 module.
Scenario documents are validated with the versioned-JSON rules from sim/serialization.py on
every write and read, so nothing invalid is stored and nothing is silently dropped.

Run-record contract for issue #10: save_run(run_id, scenario_name, label, timestamp, seed,
scenario_snapshot, metrics) where scenario_snapshot is the full scenario document used for the
run and metrics is any JSON-serialisable dict (e.g. dataclasses.asdict(SimulationMetrics)).
A run keeps its own snapshot, so it reloads even after its scenario is renamed or deleted.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tms_sim.sim.serialization import (
    ScenarioFormatError,
    load_scenario_document,
    save_scenario_document,
    scenario_from_dict,
)

MAX_NAME = 100
_SCHEMA = """
CREATE TABLE IF NOT EXISTS scenarios (
    name TEXT PRIMARY KEY,
    document TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    scenario_name TEXT NOT NULL,
    label TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    seed INTEGER,
    scenario_snapshot TEXT NOT NULL,
    metrics TEXT NOT NULL,
    run_config TEXT NOT NULL DEFAULT '{}'
);
"""


class ScenarioStoreError(ValueError):
    """A library operation was refused; the message says what to do."""


def default_db_path() -> Path:
    return Path.home() / ".tms_sim" / "library.sqlite3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _name(name) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ScenarioStoreError("Scenario name must not be empty.")
    name = name.strip()
    if len(name) > MAX_NAME:
        raise ScenarioStoreError(f"Scenario name must be at most {MAX_NAME} characters.")
    return name


class ScenarioStore:
    def __init__(self, db_path: str | Path | None = None):
        path = Path(db_path) if db_path else default_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.executescript(_SCHEMA)
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(runs)")}
        if "run_config" not in columns:
            self._db.execute("ALTER TABLE runs ADD COLUMN run_config TEXT NOT NULL DEFAULT '{}' ")

    def close(self) -> None:
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- scenarios ----
    def save_scenario(self, name: str, document: dict, *, overwrite: bool = False) -> str:
        name = _name(name)
        text = json.dumps(scenario_from_dict(document), sort_keys=True)  # raises ScenarioFormatError
        with self._db:
            if not overwrite and self._exists(name):
                raise ScenarioStoreError(f"A scenario named '{name}' already exists. Choose another name or overwrite it.")
            self._db.execute("INSERT OR REPLACE INTO scenarios VALUES (?, ?, ?)", (name, text, _now()))
        return name

    def list_scenarios(self) -> list[str]:
        return [r[0] for r in self._db.execute("SELECT name FROM scenarios ORDER BY name COLLATE NOCASE")]

    def load_scenario(self, name: str) -> dict:
        name = _name(name)
        row = self._db.execute("SELECT document FROM scenarios WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise ScenarioStoreError(f"No scenario named '{name}' in the library.")
        try:
            return scenario_from_dict(json.loads(row[0]))
        except (json.JSONDecodeError, ScenarioFormatError) as exc:
            raise ScenarioStoreError(f"Stored scenario '{name}' is unreadable: {exc}") from exc

    def duplicate_scenario(self, name: str, new_name: str) -> str:
        return self.save_scenario(new_name, self.load_scenario(name))

    def rename_scenario(self, name: str, new_name: str) -> str:
        name, new_name = _name(name), _name(new_name)
        with self._db:
            if not self._exists(name):
                raise ScenarioStoreError(f"No scenario named '{name}' in the library.")
            if new_name != name and self._exists(new_name):
                raise ScenarioStoreError(f"A scenario named '{new_name}' already exists.")
            self._db.execute("UPDATE scenarios SET name = ?, updated_at = ? WHERE name = ?", (new_name, _now(), name))
        return new_name

    def delete_scenario(self, name: str) -> None:
        name = _name(name)
        with self._db:
            if self._db.execute("DELETE FROM scenarios WHERE name = ?", (name,)).rowcount == 0:
                raise ScenarioStoreError(f"No scenario named '{name}' in the library.")

    def import_scenario(self, path: str | Path, name: str | None = None, *, overwrite: bool = False) -> str:
        """Import a versioned JSON file (TMS-F-013). Invalid files are refused before anything is stored."""
        document = load_scenario_document(path)  # raises ScenarioFormatError
        return self.save_scenario(name or Path(path).stem, document, overwrite=overwrite)

    def export_scenario(self, name: str, path: str | Path) -> None:
        save_scenario_document(self.load_scenario(name), path)

    def _exists(self, name: str) -> bool:
        return self._db.execute("SELECT 1 FROM scenarios WHERE name = ?", (name,)).fetchone() is not None

    # ---- completed runs (contract for #10) ----
    def save_run(self, run_id: str, scenario_name: str, label: str, timestamp: str, seed: int | None,
                 scenario_snapshot: dict, metrics: dict, run_config: dict | None = None) -> None:
        if not all(isinstance(value, str) and value.strip() for value in (run_id, scenario_name, label, timestamp)):
            raise ScenarioStoreError("Run ID, scenario name, label, and timestamp must be non-empty strings.")
        if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
            raise ScenarioStoreError("Run seed must be an integer or null.")
        if not isinstance(scenario_snapshot, dict) or not isinstance(metrics, dict):
            raise ScenarioStoreError("Run scenario snapshot and metrics must be JSON objects.")
        if run_config is None:
            run_config = {}
        if not isinstance(run_config, dict):
            raise ScenarioStoreError("Run configuration must be a JSON object.")
        try:
            values = (
                json.dumps(scenario_snapshot, sort_keys=True, allow_nan=False),
                json.dumps(metrics, sort_keys=True, allow_nan=False),
                json.dumps(run_config, sort_keys=True, allow_nan=False),
            )
            with self._db:
                self._db.execute(
                    "INSERT INTO runs (run_id, scenario_name, label, timestamp, seed, scenario_snapshot, metrics, run_config) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_id, scenario_name, label, timestamp, seed, *values),
                )
        except (TypeError, ValueError, sqlite3.Error) as exc:
            raise ScenarioStoreError(f"Could not save run '{run_id}': {exc}") from exc

    def list_runs(self, scenario_name: str | None = None) -> list[dict]:
        sql = "SELECT run_id, scenario_name, label, timestamp, seed FROM runs"
        rows = self._db.execute(sql + " WHERE scenario_name = ? ORDER BY timestamp" if scenario_name
                                else sql + " ORDER BY timestamp", (scenario_name,) if scenario_name else ())
        return [dict(zip(("run_id", "scenario_name", "label", "timestamp", "seed"), r)) for r in rows]

    def load_run(self, run_id: str) -> dict:
        try:
            row = self._db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        except sqlite3.Error as exc:
            raise ScenarioStoreError(f"Could not read run '{run_id}': {exc}") from exc
        if row is None:
            raise ScenarioStoreError(f"No run '{run_id}' in the library.")
        keys = ("run_id", "scenario_name", "label", "timestamp", "seed", "scenario_snapshot", "metrics", "run_config")
        run = dict(zip(keys, row))
        try:
            run["scenario_snapshot"] = json.loads(run["scenario_snapshot"])
            run["metrics"] = json.loads(run["metrics"])
            run["run_config"] = json.loads(run["run_config"])
            if not all(isinstance(run[key], dict) for key in ("scenario_snapshot", "metrics", "run_config")):
                raise ValueError("stored fields must be JSON objects")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ScenarioStoreError(f"Stored run '{run_id}' is unreadable: {exc}") from exc
        return run

    # SAD §4.3 names
    saveScenario = save_scenario
    loadScenario = load_scenario
    listScenarios = list_scenarios
    saveRun = save_run
