"""Scenario Library dialog (#9, TC-LIB-01 through the workbench)."""
import copy
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from tms_sim.storage.store import ScenarioStore
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


def test_import_export(lib, tmp_path):
    _, d = lib
    assert d.import_file(SAMPLE)
    assert names(d) == ["small_valid_scenario"]
    out = tmp_path / "out.json"
    assert d.export_selected(out)
    assert json.loads(out.read_text()) == json.loads(SAMPLE.read_text())
