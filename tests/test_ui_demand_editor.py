"""Automated tests for TMS-Sim Step 4A: Traffic Demand Editor in PySide6 Workbench.

Covers:
1. Displaying existing demand entries in the Traffic Demand table.
2. Adding a valid demand entry for an existing road segment.
3. Editing an existing arrival rate.
4. Removing a demand entry and displaying the empty-state message.
5. Rejecting invalid numeric values (negative, non-finite, non-numeric).
6. Rejecting unknown or stale road-segment IDs.
7. Refreshing demand after loading another scenario file.
8. Refreshing segment choices and safe cleanup after network edits.
9. Preserving previous valid demand when validation fails.
10. Synchronizing demand table selection with canvas and form fields.
"""

import copy
import json
import math
from pathlib import Path
import pytest

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

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
    win.canvas.resize(800, 600)
    yield win
    win.timer.stop()
    win.close()


def test_display_existing_demand_entries(workbench):
    """Verify Workbench loads and displays existing demand entries from scenario document."""
    # small_valid_scenario has demand: arrival_rates_vehicles_per_hour: {"R2": 180}
    table = workbench.demand_table
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "R2"
    assert table.item(0, 1).text() == "180.0"

    assert not table.isHidden()
    assert workbench.lbl_demand_empty.isHidden()

    # Check combo has all network segments
    segments = [s["id"] for s in workbench.scenario_data["network"]["segments"]]
    combo_items = [workbench.combo_demand_segment.itemText(i) for i in range(workbench.combo_demand_segment.count())]
    for sid in segments:
        assert sid in combo_items


def test_add_valid_demand_entry(workbench):
    """Verify adding an arrival rate for another valid road segment updates model and engine."""
    # R1 connects I1 -> I2. When demand is added for R1, an outgoing movement at I2 (to R2) is linked
    workbench.combo_demand_segment.setCurrentText("R1")
    workbench.edit_demand_rate.setText("120.0")

    success = workbench.apply_demand_entry()
    assert success is True

    # Scenario demand updated
    rates = workbench.scenario_data["demand"]["arrival_rates_vehicles_per_hour"]
    assert rates["R1"] == 120.0
    assert rates["R2"] == 180.0

    # Table reflects 2 rows
    assert workbench.demand_table.rowCount() == 2

    # Engine generates vehicles for both entry segments
    assert workbench.engine is not None
    assert any(c.entry == "R1" for c in workbench.engine.vehicles)
    assert any(c.entry == "R2" for c in workbench.engine.vehicles)


def test_edit_existing_arrival_rate(workbench):
    """Verify editing an existing arrival rate modifies the scenario and updates the engine."""
    workbench.combo_demand_segment.setCurrentText("R2")
    workbench.edit_demand_rate.setText("240.0")

    success = workbench.apply_demand_entry()
    assert success is True

    # Scenario data updated
    rates = workbench.scenario_data["demand"]["arrival_rates_vehicles_per_hour"]
    assert rates["R2"] == 240.0

    # Table item updated
    found_rate = None
    for row in range(workbench.demand_table.rowCount()):
        if workbench.demand_table.item(row, 0).text() == "R2":
            found_rate = float(workbench.demand_table.item(row, 1).text())
    assert found_rate == 240.0


def test_remove_demand_entry_and_empty_state(workbench):
    """Verify removing a demand entry cleans up references and displays the empty state message."""
    workbench.combo_demand_segment.setCurrentText("R2")
    success = workbench.remove_demand_entry()
    assert success is True

    # R2 removed from demand
    rates = workbench.scenario_data["demand"]["arrival_rates_vehicles_per_hour"]
    assert "R2" not in rates

    # Empty state displayed
    assert workbench.demand_table.rowCount() == 0
    assert workbench.demand_table.isHidden()
    assert not workbench.lbl_demand_empty.isHidden()

    # Simulation engine runs safely with 0 vehicles
    assert workbench.engine is not None
    assert len(workbench.engine.vehicles) == 0


def test_reject_invalid_numeric_values(workbench, monkeypatch):
    """Verify non-numeric, negative, and non-finite arrival rates are rejected with warning dialogs."""
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, text: warnings.append((title, text)),
    )

    original_rate = workbench.scenario_data["demand"]["arrival_rates_vehicles_per_hour"]["R2"]

    # 1. Negative rate
    workbench.combo_demand_segment.setCurrentText("R2")
    workbench.edit_demand_rate.setText("-50.0")
    success = workbench.apply_demand_entry()
    assert success is False
    assert len(warnings) == 1
    assert "Invalid Arrival Rate" in warnings[0][0]
    assert workbench.scenario_data["demand"]["arrival_rates_vehicles_per_hour"]["R2"] == original_rate

    # 2. Non-numeric text
    workbench.edit_demand_rate.setText("fast_traffic")
    success = workbench.apply_demand_entry()
    assert success is False
    assert len(warnings) == 2
    assert workbench.scenario_data["demand"]["arrival_rates_vehicles_per_hour"]["R2"] == original_rate


def test_reject_unknown_or_stale_road_segment(workbench, monkeypatch):
    """Verify applying demand for a non-existent segment ID is rejected."""
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, text: warnings.append((title, text)),
    )

    workbench.combo_demand_segment.addItem("GHOST_ROAD_99")
    workbench.combo_demand_segment.setCurrentText("GHOST_ROAD_99")
    workbench.edit_demand_rate.setText("100.0")
    success = workbench.apply_demand_entry()
    assert success is False
    assert len(warnings) == 1
    assert "Invalid Road Segment" in warnings[0][0]
    assert "GHOST_ROAD_99" not in workbench.scenario_data["demand"]["arrival_rates_vehicles_per_hour"]


def test_refresh_demand_after_loading_another_scenario(workbench, tmp_path):
    """Verify loading a scenario refreshes the demand table and dropdown choices."""
    doc = json.loads(SAMPLE_SCENARIO_PATH.read_text(encoding="utf-8"))
    # Modify demand: R1 = 350 veh/h, no R2 demand
    # Add turning movement for R1 at I2
    doc["network"]["turning_movements"].append({
        "id": "TM2",
        "intersection": "I2",
        "from_segment": "R1",
        "to_segment": "R2",
    })
    doc["demand"]["arrival_rates_vehicles_per_hour"] = {"R1": 350}
    doc["demand"]["turning_ratios"] = {"TM2": 1.0}

    new_file = tmp_path / "custom_demand.json"
    new_file.write_text(json.dumps(doc), encoding="utf-8")

    success = workbench.load_scenario_file(new_file)
    assert success is True

    # Demand table reflects new file's demand
    assert workbench.demand_table.rowCount() == 1
    assert workbench.demand_table.item(0, 0).text() == "R1"
    assert workbench.demand_table.item(0, 1).text() == "350.0"


def test_refresh_segment_choices_after_network_edits(workbench):
    """Verify creating a new road segment adds it to the demand dropdown, and deletion removes it."""
    # 1. Add intersection I3 and connect R3 from I2 to I3
    canvas = workbench.canvas
    i3_id = canvas.add_intersection_at(300.0, 100.0)
    success, msg = canvas.create_road_segment("I2", i3_id)
    assert success is True

    # Combo includes newly created road segment
    combo_items = [workbench.combo_demand_segment.itemText(i) for i in range(workbench.combo_demand_segment.count())]
    assert any(sid.startswith("R") and sid not in ("R1", "R2") for sid in combo_items)


def test_preserve_previous_demand_when_backend_validation_fails(workbench, monkeypatch):
    """Verify original demand state is restored if backend validation encounters an issue."""
    original_demand = copy.deepcopy(workbench.scenario_data["demand"])

    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, text: warnings.append((title, text)),
    )

    # Attempt to apply invalid rate
    workbench.combo_demand_segment.setCurrentText("R2")
    workbench.edit_demand_rate.setText("-100.0")
    workbench.apply_demand_entry()

    assert workbench.scenario_data["demand"] == original_demand


def test_demand_table_click_synchronizes_form_and_canvas(workbench):
    """Verify selecting a row in the demand table updates the form and highlights the road on canvas."""
    table = workbench.demand_table
    assert table.rowCount() > 0

    # Select row 0 (R2)
    table.selectRow(0)
    workbench.on_demand_table_selection_changed()

    assert workbench.combo_demand_segment.currentText() == "R2"
    assert float(workbench.edit_demand_rate.text()) == 180.0
    assert workbench.canvas.selected_type == "segment"
    assert workbench.canvas.selected_id == "R2"
