"""Scenario Library dialog (#9, TC-LIB-01 through the workbench)."""
import copy
import json
import sqlite3
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from tms_sim.storage.store import ScenarioStore, ScenarioStoreError
from tms_sim.ui.app import Workbench

SAMPLE = Path(__file__).resolve().parent / "data" / "scenario" / "small_valid_scenario.json"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def warnings(monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a[2]))
    return shown


@pytest.fixture
def lib(qapp, tmp_path, warnings):
    win = Workbench(SAMPLE)
    win.library_path = tmp_path / "lib.sqlite3"
    dialog = win.open_scenario_library()
    yield win, dialog
    dialog.close()
    win.timer.stop()
    win.close()


def names(dialog):
    return [dialog.list.item(i).text() for i in range(dialog.list.count())]


def test_menu_action_exists(lib):
    win, _ = lib
    assert win.library_action.text() == "Scenario &Library..."


def test_save_rename_duplicate_delete(lib):
    win, d = lib
    assert d.save_current("Demo")
    assert names(d) == ["Demo"]
    assert d.duplicate_selected("Demo 2") and d.rename_selected("Renamed")
    assert names(d) == ["Demo", "Renamed"]
    d.select("Demo")
    assert d.delete_selected(confirm=True)
    assert names(d) == ["Renamed"]
    assert "Deleted 'Demo'" in win.status_label.text()


def test_load_from_library_replaces_scenario_and_clears_path(lib):
    win, d = lib
    doc = copy.deepcopy(win.scenario_data)
    doc["simulation"]["seed"] = 99
    with ScenarioStore(win.library_path) as s:
        s.save_scenario("Seed 99", doc)
    d.refresh()
    assert d.load_selected("Seed 99")
    assert win.scenario_data["simulation"]["seed"] == 99
    assert win.scenario_path is None  # Save now goes to Save As instead of overwriting the old file
    assert "Seed 99" in win.status_label.text()


def test_invalid_library_entry_keeps_current_scenario(lib, warnings):
    win, d = lib
    bad = copy.deepcopy(win.scenario_data)
    bad["network"]["segments"][0]["length_m"] = 0  # structurally fine, fails network validation
    with ScenarioStore(win.library_path) as s:
        s.save_scenario("Broken", bad)
    before = copy.deepcopy(win.scenario_data)
    assert not d.load_selected("Broken")
    assert win.scenario_data == before and warnings


def test_name_clash_reports_error(lib, warnings):
    _, d = lib
    d.save_current("Same")
    assert not d.save_current("Same", overwrite=False)
    assert "already exists" in warnings[-1]


def test_storage_failures_are_recorded_without_changing_library_error_flow(lib, monkeypatch, warnings):
    win, dialog = lib

    def fail_save(*_args, **_kwargs):
        raise ScenarioStoreError("test storage failure")

    monkeypatch.setattr(dialog.store, "save_scenario", fail_save)

    assert not dialog.save_current("Broken")
    assert warnings[-1] == "test storage failure"
    assert win.storage_errors == [
        {"operation": "scenario library operation", "error": "test storage failure"}
    ]


def test_sqlite_read_failure_is_recorded_and_reported(lib, monkeypatch, warnings):
    win, dialog = lib

    def fail_load(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(dialog.store, "load_scenario", fail_load)

    assert not dialog.load_selected("Broken")
    assert warnings[-1] == "database is locked"
    assert win.storage_errors == [
        {"operation": "scenario library operation", "error": "database is locked"}
    ]


def test_library_initialization_failure_closes_database_connection(qapp, tmp_path, monkeypatch):
    import tms_sim.ui.library as library_module

    created_stores = []
    original_store = library_module.ScenarioStore

    class FailingReadStore(original_store):
        def __init__(self, path):
            super().__init__(path)
            created_stores.append(self)

        def list_scenarios(self):
            raise sqlite3.OperationalError("test initial read failure")

    monkeypatch.setattr(library_module, "ScenarioStore", FailingReadStore)
    workbench = Workbench(SAMPLE)
    workbench.library_path = tmp_path / "initialization-failure.sqlite3"
    try:
        with pytest.raises(sqlite3.OperationalError, match="initial read failure"):
            workbench.open_scenario_library()
        assert workbench.storage_errors == [
            {"operation": "scenario library refresh", "error": "test initial read failure"},
            {"operation": "open scenario library", "error": "test initial read failure"},
        ]
        assert len(created_stores) == 1
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            created_stores[0]._db.execute("SELECT 1")
    finally:
        workbench.timer.stop()
        workbench.close()


def test_import_export(lib, tmp_path):
    _, d = lib
    assert d.import_file(SAMPLE)
    assert names(d) == ["small_valid_scenario"]
    out = tmp_path / "out.json"
    assert d.export_selected(out)
    assert json.loads(out.read_text()) == json.loads(SAMPLE.read_text())
