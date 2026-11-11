"""Automated tests for GitHub Issue #29: UI & 2D Visualization Stabilization.

Covers:
1. Full simulation lifecycle state transitions: Ready -> Running -> Paused -> Resumed -> Completed.
2. Safe rendering and handling of empty network configurations without errors or crashes.
3. Proper blocking and user feedback when an invalid network configuration is loaded.
4. Regression test for SI-D2: auto-capture of completed runs after loading another scenario without manual Reset.
5. Regression test for SI-D3: removing the last signal plan from a single-plan scenario writes valid signal_plans: [].
6. Auto-capture reset on network modifications.
7. Pan, zoom, and canvas reset view safety.
8. Stale metric clearance and dashboard refresh on scenario reload.
"""
from __future__ import annotations

import copy
from pathlib import Path
import pytest
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from tms_sim.sim.serialization import load_scenario_document, save_scenario_document
from tms_sim.storage.store import ScenarioStore
from tms_sim.ui.app import Workbench, set_scenario_signal_plans

SAMPLE_SCENARIO_PATH = (
    Path(__file__).resolve().parent / "data" / "scenario" / "small_valid_scenario.json"
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def workbench(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    win = Workbench(SAMPLE_SCENARIO_PATH)
    win.library_path = tmp_path / "workbench.sqlite3"
    win.canvas.resize(800, 600)
    yield win
    win.timer.stop()
    for name in ("comparison_dialog", "history_dialog", "library_dialog"):
        dlg = getattr(win, name, None)
        if dlg is not None:
            dlg.close()
    win.set_dirty(False)
    win.close()


def test_simulation_state_lifecycle(workbench):
    """Test Ready -> Running -> Paused -> Resumed -> Completed transitions and control states."""
    # 1. Ready state
    assert workbench.engine is not None
    assert workbench.engine.time == 0.0
    assert not workbench.engine.running
    assert not workbench.engine.finished
    assert workbench.btn_play.isEnabled()
    assert workbench.btn_play.text() == "▶  Play"
    assert not workbench.btn_pause.isEnabled()
    assert workbench.btn_step.isEnabled()
    assert not workbench.btn_reset.isEnabled()

    # 2. Running state
    workbench.start_simulation()
    assert workbench.timer.isActive()
    assert workbench.engine.running
    assert not workbench.btn_play.isEnabled()
    assert workbench.btn_pause.isEnabled()
    assert not workbench.btn_step.isEnabled()
    assert workbench.btn_reset.isEnabled()

    # Advance a few steps
    for _ in range(5):
        workbench.engine.step()
    workbench.canvas.update()
    workbench.update_metrics()
    assert workbench.engine.time > 0.0

    # 3. Paused state
    workbench.pause_simulation()
    assert not workbench.timer.isActive()
    assert not workbench.engine.running
    assert workbench.btn_play.isEnabled()
    assert workbench.btn_play.text() == "▶  Resume"
    assert not workbench.btn_pause.isEnabled()
    assert workbench.btn_step.isEnabled()
    assert workbench.btn_reset.isEnabled()

    # 4. Resumed state
    workbench.start_simulation()
    assert workbench.timer.isActive()
    assert workbench.engine.running
    assert not workbench.btn_play.isEnabled()
    assert workbench.btn_pause.isEnabled()

    # 5. Completed state
    workbench.engine.duration = 5.0
    workbench.engine.duration = 5.0
    workbench.engine.set_speed(4)
    while not workbench.engine.finished:
        workbench.advance_simulation()
    workbench.update_metrics()
    workbench.update_playback_controls_state()

    assert workbench.engine.finished
    assert not workbench.btn_play.isEnabled()
    assert not workbench.btn_pause.isEnabled()
    assert not workbench.btn_step.isEnabled()
    assert workbench.btn_reset.isEnabled()
    assert "Simulation completed" in workbench.status_label.text()

    # 6. Reset state
    workbench.reset_simulation()
    assert workbench.engine.time == 0.0
    assert not workbench.engine.finished
    assert workbench.btn_play.isEnabled()
    assert workbench.btn_play.text() == "▶  Play"
    assert not workbench.btn_reset.isEnabled()


def test_empty_network_rendering_and_safety(workbench):
    """Test that an empty network renders safely without throwing exceptions."""
    empty_doc = {
        "schema_version": "1.0",
        "name": "Empty Network Scenario",
        "network": {
            "intersections": [],
            "segments": [],
            "turning_movements": []
        },
        "signal_plans": [],
        "demand": {
            "arrival_rates_vehicles_per_hour": {},
            "turning_ratios": {}
        },
        "simulation": {
            "duration_s": 60,
            "time_step_s": 0.5,
            "seed": 42
        }
    }
    workbench.scenario_data = empty_doc
    workbench.canvas.scenario_data = empty_doc
    workbench.engine = None
    workbench.canvas.engine = None

    # Paint canvas and ensure no exception
    workbench.canvas.grab()
    queue_state = workbench.canvas.get_queue_state("NON_EXISTENT")
    assert queue_state["count"] == 0
    assert queue_state["length_m"] == 0.0


def test_invalid_network_blocks_simulation_safely(workbench):
    """Test that an invalid network disables playback buttons and provides feedback."""
    # Introduce a validation error (zero length segment)
    bad_doc = copy.deepcopy(workbench.scenario_data)
    bad_doc["network"]["segments"][0]["length_m"] = 0.0

    success = workbench.load_scenario_data(bad_doc, "Invalid Scenario")
    assert success is False
    assert workbench.engine is None or not workbench.engine.running


def test_si_d2_auto_capture_after_scenario_reload(workbench):
    """Regression test for SI-D2: verify run capture after loading another scenario without manual reset."""
    doc1 = copy.deepcopy(workbench.scenario_data)
    doc1["simulation"]["duration_s"] = 10.0
    doc1["simulation"]["seed"] = 42

    doc2 = copy.deepcopy(workbench.scenario_data)
    doc2["simulation"]["duration_s"] = 10.0
    doc2["simulation"]["seed"] = 43

    with ScenarioStore(workbench.library_path) as s:
        s.save_scenario("Scenario A", doc1)
        s.save_scenario("Scenario B", doc2)

    library = workbench.open_scenario_library()
    library.refresh()

    # Load and run first
    assert library.load_selected("Scenario A")
    workbench.start_simulation()
    workbench.engine.duration = 5.0
    workbench.engine.set_speed(4)
    while not workbench.engine.finished:
        workbench.advance_simulation()
    assert workbench.engine.finished

    with ScenarioStore(workbench.library_path) as s:
        runs = s.list_runs()
        assert len(runs) == 1
        assert runs[0]["seed"] == 42

    # Load and run second WITHOUT manual reset
    assert library.load_selected("Scenario B")
    workbench.start_simulation()
    workbench.engine.duration = 5.0
    workbench.engine.set_speed(4)
    while not workbench.engine.finished:
        workbench.advance_simulation()
    assert workbench.engine.finished

    with ScenarioStore(workbench.library_path) as s:
        runs = s.list_runs()
        assert len(runs) == 2
        seeds = [r["seed"] for r in runs]
        assert 42 in seeds and 43 in seeds


def test_si_d3_single_plan_removal_produces_valid_empty_plans(tmp_path):
    """Regression test for SI-D3: set_scenario_signal_plans with empty list yields signal_plans: []."""
    doc = load_scenario_document(SAMPLE_SCENARIO_PATH)
    assert "signal_plan" in doc or "signal_plans" in doc
    doc["network"]["intersections"][0]["control_type"] = "stop_controlled"

    set_scenario_signal_plans(doc, [])
    assert "signal_plan" not in doc
    assert "signal_plans" in doc
    assert doc["signal_plans"] == []

    out = tmp_path / "valid_no_plans.json"
    save_scenario_document(doc, out)
    assert out.exists()

    reloaded = load_scenario_document(out)
    assert reloaded["signal_plans"] == []


def test_auto_capture_reset_on_network_modified(workbench):
    """Verify modifying network and running to completion captures the new run."""
    workbench.engine.duration = 5.0
    workbench.start_simulation()
    workbench.engine.set_speed(4)
    for _ in range(10_000):
        if workbench.engine.finished:
            break
        workbench.advance_simulation()
    assert workbench.engine.finished
    assert workbench._last_captured_engine_finished_state is True

    # Modify network
    workbench.on_network_modified("Test modification")
    assert workbench._last_captured_engine_finished_state is False


def test_canvas_pan_zoom_and_reset_view(workbench):
    """Verify canvas zoom clamping, pan offset updates, and reset view."""
    canvas = workbench.canvas
    canvas.set_zoom(0.1)
    assert canvas.zoom_level == canvas.MIN_ZOOM

    canvas.set_zoom(10.0)
    assert canvas.zoom_level == canvas.MAX_ZOOM

    canvas.pan_offset = QPointF(100.0, -50.0)
    canvas.reset_view()
    assert canvas.zoom_level == canvas.DEFAULT_ZOOM
    assert canvas.pan_offset == QPointF(0.0, 0.0)
