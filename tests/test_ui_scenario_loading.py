"""Tests for scenario loading, error handling, and UI refresh in TMS-Sim workbench."""

import copy
import json
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

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
    win = Workbench()
    yield win
    win.timer.stop()
    win.close()


def test_workbench_title_and_initial_state(workbench):
    """Verify workbench opens with expected title and bundled default scenario."""
    assert workbench.windowTitle() == "TMS-Sim"
    assert workbench.scenario_path == SAMPLE_SCENARIO_PATH
    assert workbench.scenario_file_label.text() == "small_valid_scenario.json"
    assert "small" in workbench.scenario_name_label.text().lower()
    assert workbench.intersections_label.text() == "Intersections: 2"
    assert workbench.segments_label.text() == "Road segments: 2"
    assert workbench.control_label.text() == "Signalized intersections: 1"
    assert workbench.vehicle_count_label.text() == "0"
    assert workbench.metric_time.text() == "0.0 s"


def test_load_valid_scenario_from_different_directory(workbench, tmp_path):
    """Verify loading a valid scenario updates canvas, metrics, labels, and engine."""
    original_data = json.loads(SAMPLE_SCENARIO_PATH.read_text(encoding="utf-8"))
    custom_scenario = copy.deepcopy(original_data)
    custom_scenario["name"] = "Custom Multi-node Scenario"
    custom_scenario["network"]["intersections"].append({
        "id": "I3",
        "position": [200, 0],
        "control_type": "uncontrolled",
    })
    custom_scenario["network"]["segments"].append({
        "id": "R3",
        "from": "I2",
        "to": "I3",
        "length_m": 150,
        "lane_count": 2,
        "speed_limit_mps": 13.9,
    })

    # Save outside the project repository structure (in tmp_path)
    external_file = tmp_path / "custom_scenario.json"
    external_file.write_text(json.dumps(custom_scenario), encoding="utf-8")

    success = workbench.load_scenario_file(external_file)
    assert success is True

    # Check path and labels
    assert workbench.scenario_path == external_file
    assert workbench.scenario_file_label.text() == "custom_scenario.json"
    assert workbench.scenario_name_label.text() == "Custom Multi-node Scenario"
    assert workbench.intersections_label.text() == "Intersections: 3"
    assert workbench.segments_label.text() == "Road segments: 3"
    assert workbench.control_label.text() == "Signalized intersections: 1"

    # Check canvas updated
    assert workbench.canvas.scenario_data == custom_scenario
    assert workbench.canvas.engine is workbench.engine

    # Check status label
    assert "custom_scenario.json" in workbench.status_label.text()
    assert "loaded successfully" in workbench.status_label.text().lower()


def test_malformed_json_handled_without_crashing(workbench, tmp_path, monkeypatch):
    """Verify malformed JSON file does not crash and shows user-friendly message."""
    malformed_file = tmp_path / "bad.json"
    malformed_file.write_text("{this is not valid json:", encoding="utf-8")

    critical_messages = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: critical_messages.append((title, text)),
    )

    old_engine = workbench.engine
    old_path = workbench.scenario_path
    old_file_label = workbench.scenario_file_label.text()

    success = workbench.load_scenario_file(malformed_file)
    assert success is False

    # Check error message presented to user
    assert len(critical_messages) == 1
    title, msg = critical_messages[0]
    assert "Unable to Load Scenario" in title
    assert "invalid" in msg.lower() or "json" in msg.lower()

    # Ensure previous scenario remains active and intact
    assert workbench.engine is old_engine
    assert workbench.scenario_path == old_path
    assert workbench.scenario_file_label.text() == old_file_label
    assert "failed" in workbench.status_label.text().lower()


def test_invalid_network_preserves_running_simulation_state(workbench, tmp_path, monkeypatch):
    """Verify invalid network does not overwrite active simulation state."""
    # Run a step on the current simulation
    workbench.step_simulation()
    assert workbench.engine.time > 0.0
    sim_time = workbench.engine.time
    old_engine = workbench.engine

    # Create scenario with invalid network (zero length segment)
    doc = json.loads(SAMPLE_SCENARIO_PATH.read_text(encoding="utf-8"))
    doc["network"]["segments"][0]["length_m"] = 0
    invalid_file = tmp_path / "zero_length.json"
    invalid_file.write_text(json.dumps(doc), encoding="utf-8")

    critical_messages = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: critical_messages.append((title, text)),
    )

    success = workbench.load_scenario_file(invalid_file)
    assert success is False

    # Check error dialog was triggered with validation error details
    assert len(critical_messages) == 1
    _, text = critical_messages[0]
    assert "ZERO_LENGTH" in text

    # State preserved
    assert workbench.engine is old_engine
    assert workbench.engine.time == sim_time
    assert workbench.scenario_path == SAMPLE_SCENARIO_PATH


def test_invalid_signal_plan_rejected(workbench, tmp_path, monkeypatch):
    """Verify invalid signal plan (green_s = 0) is rejected safely."""
    doc = json.loads(SAMPLE_SCENARIO_PATH.read_text(encoding="utf-8"))
    doc["signal_plan"]["phases"][0]["green_s"] = 0
    invalid_plan_file = tmp_path / "bad_plan.json"
    invalid_plan_file.write_text(json.dumps(doc), encoding="utf-8")

    critical_messages = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: critical_messages.append((title, text)),
    )

    success = workbench.load_scenario_file(invalid_plan_file)
    assert success is False
    assert len(critical_messages) == 1
    assert "INVALID_GREEN" in critical_messages[0][1]


def test_invalid_demand_rejected(workbench, tmp_path, monkeypatch):
    """Verify invalid demand (unknown movement) is rejected safely."""
    doc = json.loads(SAMPLE_SCENARIO_PATH.read_text(encoding="utf-8"))
    doc["demand"]["turning_ratios"] = {"UNKNOWN_MOVE": 1.0}
    invalid_demand_file = tmp_path / "bad_demand.json"
    invalid_demand_file.write_text(json.dumps(doc), encoding="utf-8")

    critical_messages = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: critical_messages.append((title, text)),
    )

    success = workbench.load_scenario_file(invalid_demand_file)
    assert success is False
    assert len(critical_messages) == 1
    assert "UNKNOWN_MOVE" in critical_messages[0][1]


def test_file_dialog_cancellation_does_not_change_active_scenario(workbench, monkeypatch):
    """Verify cancelling file dialog preserves active scenario and shows cancellation message."""
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: ("", ""),
    )

    old_path = workbench.scenario_path
    old_engine = workbench.engine

    workbench.open_scenario_dialog()

    assert workbench.scenario_path == old_path
    assert workbench.engine is old_engine
    assert "cancelled" in workbench.status_label.text().lower()


def test_file_dialog_selection_loads_scenario(workbench, tmp_path, monkeypatch):
    """Verify selecting a file in the file dialog successfully loads it."""
    new_file = tmp_path / "dialog_selected.json"
    new_file.write_text(SAMPLE_SCENARIO_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(new_file), "JSON Files (*.json)"),
    )

    workbench.open_scenario_dialog()

    assert workbench.scenario_path == new_file
    assert workbench.scenario_file_label.text() == "dialog_selected.json"
    assert "loaded successfully" in workbench.status_label.text().lower()


def test_simulation_controls_work_after_loading_scenario(workbench, tmp_path):
    """Verify Start, Step, Pause, Speed, and Reset controls work after scenario load."""
    new_file = tmp_path / "sim_test.json"
    new_file.write_text(SAMPLE_SCENARIO_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    success = workbench.load_scenario_file(new_file)
    assert success is True

    # 1. Start
    workbench.start_simulation()
    assert workbench.engine.running is True
    assert workbench.timer.isActive() is True
    assert workbench.status_label.text() == "Simulation running"

    # 2. Pause
    workbench.pause_simulation()
    assert workbench.engine.running is False
    assert workbench.status_label.text() == "Simulation paused"

    # 3. Step
    workbench.step_simulation()
    assert workbench.engine.time > 0.0
    assert float(workbench.metric_time.text().replace(" s", "")) > 0.0

    # 4. Speed
    workbench.speed_box.setCurrentText("2x")
    assert workbench.engine.speed == 2.0

    # 5. Reset
    workbench.reset_simulation()
    assert workbench.engine.time == 0.0
    assert workbench.engine.running is False
    assert workbench.metric_time.text() == "0.0 s"
    assert workbench.vehicle_count_label.text() == "0"
    assert workbench.status_label.text() == "Simulation reset"


def test_vehicles_from_prior_run_are_removed_on_scenario_load(workbench, tmp_path):
    """Ensure cars and run metrics from a prior running simulation do not persist."""
    # Run until vehicles spawn
    workbench.start_simulation()
    for _ in range(50):
        workbench.advance_simulation()
        if workbench.engine.cars or workbench.engine.exited:
            break
    workbench.pause_simulation()

    # Load a new scenario
    new_file = tmp_path / "fresh_scenario.json"
    new_file.write_text(SAMPLE_SCENARIO_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    workbench.load_scenario_file(new_file)

    # Cars in new engine must be empty
    assert len(workbench.engine.cars) == 0
    assert workbench.vehicle_count_label.text() == "0"
    assert workbench.metric_time.text() == "0.0 s"
    assert workbench.completed_label.text() == "0"
    assert workbench.generated_label.text() == "0"
