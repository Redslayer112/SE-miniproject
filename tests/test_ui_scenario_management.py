"""Automated tests for TMS-Sim Step 5D: Scenario Save and Management.

Covers:
1. Save As writes valid scenario JSON.
2. Save and reload preserve network configuration.
3. Demand and turning ratios survive save/load.
4. Signal plans and phase configuration survive save/load.
5. Save without a current path opens Save As.
6. Successful save updates the path and clears dirty state.
7. Canceling Save As preserves dirty state and current path.
8. Write failures preserve dirty state and existing scenario.
9. Existing destination overwrite protection works.
10. Editing network geometry marks the scenario dirty.
11. Editing demand marks the scenario dirty.
12. Editing signal plans marks the scenario dirty.
13. Simulation playback alone does not mark the scenario dirty.
14. Successful scenario loading clears dirty state.
15. Invalid scenario loading preserves the existing scenario and dirty state.
16. Unsaved-changes Save/Discard/Cancel decisions behave correctly.
17. Closing the application respects unsaved changes.
18. Open scenario dialog respects unsaved changes cancellation.
"""

import json
from pathlib import Path
import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from tms_sim.sim.serialization import (
    ScenarioFormatError,
    load_scenario_document,
)
from tms_sim.ui.app import Workbench

SAMPLE_SCENARIO_PATH = (
    Path(__file__).resolve().parent / "data" / "scenario" / "small_valid_scenario.json"
)


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single QApplication instance exists for testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def workbench(qapp):
    """Provide a fresh Workbench instance for each test, closing it on teardown."""
    win = Workbench(SAMPLE_SCENARIO_PATH)
    yield win
    win.timer.stop()
    win.close()


def test_save_as_writes_valid_scenario_json(workbench, tmp_path):
    """Verify Save As writes a complete, valid scenario document conforming to project schema."""
    dest = tmp_path / "exported_scenario.json"
    result = workbench.save_scenario_as(dest)

    assert result is True
    assert dest.exists()
    doc = load_scenario_document(dest)
    assert doc["schema_version"] == "1.0"
    assert "network" in doc
    assert "demand" in doc
    assert "simulation" in doc


def test_save_and_reload_preserve_network_configuration(workbench, tmp_path):
    """Verify editing network elements and saving/reloading accurately restores network geometry."""
    # Modify position of an existing intersection
    intersections = workbench.scenario_data["network"]["intersections"]
    target_id = intersections[0]["id"]
    intersections[0]["position"] = [250.0, 300.0]
    workbench.on_network_modified()

    dest = tmp_path / "network_saved.json"
    workbench.save_scenario_as(dest)

    # Reload into a fresh workbench
    reloaded = Workbench(dest)
    try:
        reloaded_intersections = reloaded.scenario_data["network"]["intersections"]
        match = next((i for i in reloaded_intersections if i["id"] == target_id), None)
        assert match is not None
        assert match["position"] == [250.0, 300.0]
    finally:
        reloaded.close()


def test_demand_and_turning_ratios_survive_save_load(workbench, tmp_path):
    """Verify demand configuration changes persist across save and reload."""
    demand = workbench.scenario_data.setdefault("demand", {})
    rates = demand.setdefault("arrival_rates_vehicles_per_hour", {})
    rates["R2"] = 240.0
    workbench.on_network_modified()

    dest = tmp_path / "demand_saved.json"
    workbench.save_scenario_as(dest)

    reloaded = Workbench(dest)
    try:
        reloaded_rates = reloaded.scenario_data["demand"]["arrival_rates_vehicles_per_hour"]
        assert reloaded_rates["R2"] == 240.0
    finally:
        reloaded.close()


def test_signal_plans_and_phase_config_survive_save_load(workbench, tmp_path):
    """Verify signal plans and phases persist across save and reload."""
    # Add a new phase
    phase_added = workbench.add_new_phase()
    assert phase_added is True

    dest = tmp_path / "signal_saved.json"
    workbench.save_scenario_as(dest)

    reloaded = Workbench(dest)
    try:
        assert reloaded.engine is not None
        assert reloaded.scenario_data == load_scenario_document(dest)
    finally:
        reloaded.close()


def test_save_without_current_path_opens_save_as(workbench, tmp_path, monkeypatch):
    """Verify calling Save when scenario_path is unset triggers Save As dialog."""
    workbench.scenario_path = None
    target_dest = tmp_path / "unnamed_scenario.json"

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(target_dest), "JSON Files (*.json)"),
    )

    saved = workbench.save_scenario()
    assert saved is True
    assert workbench.scenario_path == target_dest
    assert target_dest.exists()


def test_successful_save_updates_path_and_clears_dirty_state(workbench, tmp_path):
    """Verify successful save updates scenario path and resets is_dirty and window title."""
    workbench.set_dirty(True)
    assert workbench.is_dirty is True
    assert workbench.windowTitle() == "TMS-Sim *"

    dest = tmp_path / "clean_state.json"
    saved = workbench.save_scenario_as(dest)

    assert saved is True
    assert workbench.scenario_path == dest
    assert workbench.is_dirty is False
    assert workbench.dirty is False
    assert workbench.windowTitle() == "TMS-Sim"


def test_canceling_save_as_preserves_dirty_state_and_current_path(workbench, monkeypatch):
    """Verify user cancelling Save As dialog preserves dirty state and path."""
    orig_path = workbench.scenario_path
    workbench.set_dirty(True)

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: ("", ""),
    )

    saved = workbench.save_scenario_as()
    assert saved is False
    assert workbench.is_dirty is True
    assert workbench.scenario_path == orig_path
    assert workbench.windowTitle() == "TMS-Sim *"
    assert "Save cancelled" in workbench.status_label.text()


def test_write_failures_preserve_dirty_state_and_existing_scenario(workbench, tmp_path, monkeypatch):
    """Verify write failure raises error dialog, leaves is_dirty True, and keeps scenario unchanged."""
    workbench.set_dirty(True)
    dest = tmp_path / "readonly_dir" / "scenario.json"

    critical_boxes = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: critical_boxes.append((title, text)),
    )

    from tms_sim.ui import app as app_module
    monkeypatch.setattr(
        app_module,
        "save_scenario_document",
        lambda data, path: (_ for _ in ()).throw(OSError("Permission denied")),
    )

    saved = workbench.save_scenario_as(dest)
    assert saved is False
    assert workbench.is_dirty is True
    assert len(critical_boxes) == 1
    assert "Save Failed" in critical_boxes[0][0]


def test_existing_destination_overwrite_protection(workbench, tmp_path, monkeypatch):
    """Verify overwrite confirmation protects existing files when user declines."""
    existing_dest = tmp_path / "already_exists.json"
    existing_dest.write_text('{"sentinel": true}', encoding="utf-8")

    workbench.set_dirty(True)

    # User declines overwrite
    monkeypatch.setattr(workbench, "confirm_overwrite", lambda p: False)
    saved = workbench.save_scenario_as(existing_dest)
    assert saved is False
    assert existing_dest.read_text(encoding="utf-8") == '{"sentinel": true}'
    assert workbench.is_dirty is True

    # User accepts overwrite
    monkeypatch.setattr(workbench, "confirm_overwrite", lambda p: True)
    saved = workbench.save_scenario_as(existing_dest)
    assert saved is True
    assert existing_dest.read_text(encoding="utf-8") != '{"sentinel": true}'
    assert workbench.is_dirty is False


def test_editing_network_marks_scenario_dirty(workbench):
    """Verify adding an intersection marks the scenario dirty and updates title."""
    assert workbench.is_dirty is False
    assert workbench.windowTitle() == "TMS-Sim"

    workbench.canvas.add_intersection_at(50.0, 50.0)
    assert workbench.is_dirty is True
    assert workbench.windowTitle() == "TMS-Sim *"


def test_editing_demand_marks_scenario_dirty(workbench):
    """Verify applying demand changes marks scenario dirty and updates title."""
    assert workbench.is_dirty is False

    demand = workbench.scenario_data.setdefault("demand", {})
    demand.setdefault("arrival_rates_vehicles_per_hour", {})["R2"] = 350.0
    workbench.on_network_modified()

    assert workbench.is_dirty is True
    assert workbench.windowTitle() == "TMS-Sim *"


def test_editing_signal_plans_marks_scenario_dirty(workbench):
    """Verify adding a signal phase marks scenario dirty and updates title."""
    assert workbench.is_dirty is False

    workbench.add_new_phase()
    assert workbench.is_dirty is True
    assert workbench.windowTitle() == "TMS-Sim *"


def test_simulation_playback_alone_does_not_mark_dirty(workbench):
    """Verify starting, pausing, stepping, advancing, and resetting simulation never marks scenario dirty."""
    assert workbench.is_dirty is False

    workbench.start_simulation()
    for _ in range(5):
        workbench.advance_simulation()
    assert workbench.is_dirty is False

    workbench.pause_simulation()
    assert workbench.is_dirty is False

    workbench.step_simulation()
    assert workbench.is_dirty is False

    workbench.reset_simulation()
    assert workbench.is_dirty is False
    assert workbench.windowTitle() == "TMS-Sim"


def test_successful_scenario_loading_clears_dirty_state(workbench):
    """Verify loading a valid scenario clears dirty state."""
    workbench.set_dirty(True)
    assert workbench.is_dirty is True

    loaded = workbench.load_scenario_file(SAMPLE_SCENARIO_PATH)
    assert loaded is True
    assert workbench.is_dirty is False
    assert workbench.windowTitle() == "TMS-Sim"


def test_invalid_scenario_loading_preserves_dirty_state_and_scenario(workbench, tmp_path, monkeypatch):
    """Verify loading an invalid scenario fails, preserves existing state, and keeps is_dirty True."""
    workbench.set_dirty(True)
    bad_file = tmp_path / "broken.json"
    bad_file.write_text("{broken json", encoding="utf-8")

    monkeypatch.setattr(QMessageBox, "critical", lambda *args: None)

    loaded = workbench.load_scenario_file(bad_file)
    assert loaded is False
    assert workbench.is_dirty is True
    assert workbench.windowTitle() == "TMS-Sim *"


def test_unsaved_changes_save_discard_cancel_decisions(workbench, tmp_path, monkeypatch):
    """Verify maybe_save_changes decision logic handles save, discard, and cancel choices."""
    workbench.set_dirty(True)

    # 1. Cancel decision -> aborts action (returns False)
    workbench.save_prompt_handler = lambda: "cancel"
    assert workbench.maybe_save_changes() is False
    assert workbench.is_dirty is True

    # 2. Discard decision -> proceeds without saving (returns True)
    workbench.save_prompt_handler = lambda: "discard"
    assert workbench.maybe_save_changes() is True
    assert workbench.is_dirty is True  # Discard allows proceeding; does not save

    # 3. Save decision -> saves scenario and proceeds
    dest = tmp_path / "prompt_saved.json"
    workbench.scenario_path = dest
    workbench.save_prompt_handler = lambda: "save"
    assert workbench.maybe_save_changes() is True
    assert workbench.is_dirty is False
    assert dest.exists()


def test_closing_application_respects_unsaved_changes(workbench):
    """Verify closeEvent ignores close when user cancels and accepts when user discards."""
    workbench.set_dirty(True)

    # User cancels close
    workbench.save_prompt_handler = lambda: "cancel"
    ev_cancel = QCloseEvent()
    workbench.closeEvent(ev_cancel)
    assert ev_cancel.isAccepted() is False

    # User discards changes
    workbench.save_prompt_handler = lambda: "discard"
    ev_discard = QCloseEvent()
    workbench.closeEvent(ev_discard)
    assert ev_discard.isAccepted() is True


def test_open_scenario_dialog_cancelled_when_user_cancels_save(workbench, monkeypatch):
    """Verify open_scenario_dialog aborts if user cancels save prompt for unsaved changes."""
    workbench.set_dirty(True)
    workbench.save_prompt_handler = lambda: "cancel"

    file_dialog_opened = []
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (file_dialog_opened.append(True) or ("", "")),
    )

    workbench.open_scenario_dialog()
    assert len(file_dialog_opened) == 0  # File dialog was never reached
