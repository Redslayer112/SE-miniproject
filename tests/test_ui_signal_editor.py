"""Automated tests for TMS-Sim Step 4B: Signal Plan Editor in PySide6 Workbench.

Covers:
1. Displaying existing signal plans and phases.
2. Selecting a signal plan and synchronizing with canvas selection.
3. Adding and editing a phase.
4. Updating phase durations (green, yellow, all-red) and computed cycle duration.
5. Assigning valid turning movements to phases.
6. Reordering phases (Up/Down) with sequential renumbering.
7. Removing a phase with sequential renumbering.
8. Rejecting invalid durations (negative, zero green, non-numeric).
9. Rejecting empty movement assignments.
10. Rejecting unknown movement IDs.
11. Rejecting conflicting turning movements in a single phase.
12. Preserving the previous valid plan when validation fails.
13. Refreshing the editor after loading another scenario file.
14. Refreshing live signal indicators and engine after applying a valid plan.
15. Empty-state messaging when no signal plans or signalized intersections exist.
"""

import copy
import json
from pathlib import Path
import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from tms_sim.network import ControlType
from tms_sim.signal.model import SignalPhase, SignalPlan
from tms_sim.signal.validation import validate_signal_plan
from tms_sim.ui.app import Workbench, get_scenario_signal_plans

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
def workbench(qapp, monkeypatch):
    """Provide a fresh Workbench instance for each test, mocking modal message boxes."""
    # Prevent blocking modal dialogs during automated tests
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    win = Workbench()
    win.canvas.resize(800, 600)
    yield win
    win.timer.stop()
    win.close()


def test_display_existing_signal_plans_and_phases(workbench):
    """Verify Signal Plan Editor loads and displays existing signal plan from scenario."""
    # small_valid_scenario has 1 signalized intersection I1 with 1 phase (TM1, green=20, yellow=3, all_red=1)
    assert workbench.combo_signal_plan.isEnabled()
    assert workbench.combo_signal_plan.currentData() == "I1"

    # Cycle duration should be 20 + 3 + 1 = 24.0 s
    assert "24.0 s" in workbench.lbl_plan_cycle.text()

    # Phase table should have 1 row
    assert workbench.phase_table.rowCount() == 1
    assert workbench.phase_table.item(0, 0).text() == "1"
    assert workbench.phase_table.item(0, 1).text() == "20.0"
    assert workbench.phase_table.item(0, 2).text() == "3.0"
    assert workbench.phase_table.item(0, 3).text() == "1.0"
    assert "TM1" in workbench.phase_table.item(0, 4).text()

    # Movement checklist has TM1 checked
    assert workbench.list_phase_movements.count() == 1
    item = workbench.list_phase_movements.item(0)
    assert "TM1" in item.text()
    assert item.checkState() == Qt.CheckState.Checked

    # Empty label should be hidden
    assert workbench.lbl_plan_empty.isHidden()


def test_select_signal_plan_and_canvas_sync(workbench):
    """Verify selecting intersection on canvas updates signal plan combo."""
    # Select I1 on canvas
    workbench.canvas.set_selection("intersection", "I1")
    assert workbench.combo_signal_plan.currentData() == "I1"

    # Verify form inputs are populated for Phase 1
    assert workbench.spin_phase_order.value() == 1
    assert workbench.edit_phase_green.text() == "20.0"
    assert workbench.edit_phase_yellow.text() == "3.0"
    assert workbench.edit_phase_all_red.text() == "1.0"


def test_update_phase_durations_and_cycle_time(workbench):
    """Verify updating phase timings validates, updates scenario, and recalculates cycle duration."""
    workbench.phase_table.selectRow(0)
    workbench.edit_phase_green.setText("35.0")
    workbench.edit_phase_yellow.setText("4.0")
    workbench.edit_phase_all_red.setText("2.0")

    success = workbench.apply_phase_edits()
    assert success is True

    # Scenario data updated
    plans = get_scenario_signal_plans(workbench.scenario_data)
    plan_i1 = next(p for p in plans if p["intersection_id"] == "I1")
    p0 = plan_i1["phases"][0]
    assert p0["green_s"] == 35.0
    assert p0["yellow_s"] == 4.0
    assert p0["all_red_s"] == 2.0

    # Computed cycle duration: 35 + 4 + 2 = 41.0 s
    assert "41.0 s" in workbench.lbl_plan_cycle.text()
    assert workbench.phase_table.item(0, 1).text() == "35.0"

    # Canvas signal plan synchronized
    assert workbench.canvas.signal_plans["I1"].cycle_time_s == 41.0


def test_add_and_reorder_phases(workbench):
    """Verify adding a second phase, reordering (Up/Down), and sequential renumbering."""
    # Add a second phase with green=15.0, yellow=3.0, all_red=1.0, movement=TM1
    workbench.edit_phase_green.setText("15.0")
    workbench.edit_phase_yellow.setText("3.0")
    workbench.edit_phase_all_red.setText("1.0")

    success = workbench.add_new_phase()
    assert success is True

    # Phase table now has 2 rows
    assert workbench.phase_table.rowCount() == 2
    assert workbench.phase_table.item(0, 0).text() == "1"
    assert workbench.phase_table.item(1, 0).text() == "2"

    # Cycle duration = 20 + 3 + 1 + 15 + 3 + 1 = 43.0 s
    assert "43.0 s" in workbench.lbl_plan_cycle.text()

    # Reorder: Move Phase 2 Up (-1)
    workbench.phase_table.selectRow(1)
    assert workbench.btn_phase_up.isEnabled()
    reorder_success = workbench.reorder_phase(-1)
    assert reorder_success is True

    # First row is now the 15.0s phase, second row is the 20.0s phase
    assert workbench.phase_table.item(0, 0).text() == "1"
    assert workbench.phase_table.item(0, 1).text() == "15.0"
    assert workbench.phase_table.item(1, 0).text() == "2"
    assert workbench.phase_table.item(1, 1).text() == "20.0"

    # Canvas plan reflects the reordered phases
    canvas_phases = workbench.canvas.signal_plans["I1"].phases
    assert canvas_phases[0].order == 1
    assert canvas_phases[0].green_s == 15.0
    assert canvas_phases[1].order == 2
    assert canvas_phases[1].green_s == 20.0


def test_remove_phase_and_prevent_empty_plan(workbench):
    """Verify removing a phase updates the plan, and removing the last phase is rejected."""
    # Add a second phase first
    workbench.edit_phase_green.setText("10.0")
    workbench.add_new_phase()
    assert workbench.phase_table.rowCount() == 2

    # Remove second phase
    workbench.phase_table.selectRow(1)
    remove_success = workbench.remove_selected_phase()
    assert remove_success is True
    assert workbench.phase_table.rowCount() == 1

    # Attempt to remove the only remaining phase: should be rejected by validate_signal_plan (NO_PHASES)
    workbench.phase_table.selectRow(0)
    remove_last = workbench.remove_selected_phase()
    assert remove_last is False

    # Previous valid phase preserved
    assert workbench.phase_table.rowCount() == 1
    plans = get_scenario_signal_plans(workbench.scenario_data)
    assert len(plans[0]["phases"]) == 1


def test_reject_invalid_durations_and_preserve_state(workbench):
    """Verify invalid durations (negative, zero green, non-numeric) are rejected and state preserved."""
    workbench.phase_table.selectRow(0)
    orig_green = workbench.edit_phase_green.text()

    # 1. Reject non-positive green (0.0)
    workbench.edit_phase_green.setText("0.0")
    assert workbench.apply_phase_edits() is False

    # 2. Reject negative green (-5.0)
    workbench.edit_phase_green.setText("-5.0")
    assert workbench.apply_phase_edits() is False

    # 3. Reject negative yellow (-1.0)
    workbench.edit_phase_green.setText("20.0")
    workbench.edit_phase_yellow.setText("-1.0")
    assert workbench.apply_phase_edits() is False

    # 4. Reject negative all-red (-2.0)
    workbench.edit_phase_yellow.setText("3.0")
    workbench.edit_phase_all_red.setText("-2.0")
    assert workbench.apply_phase_edits() is False

    # 5. Reject non-numeric duration
    workbench.edit_phase_all_red.setText("xyz")
    assert workbench.apply_phase_edits() is False

    # Verify scenario data was NOT modified
    plans = get_scenario_signal_plans(workbench.scenario_data)
    assert plans[0]["phases"][0]["green_s"] == 20.0
    assert plans[0]["phases"][0]["yellow_s"] == 3.0
    assert plans[0]["phases"][0]["all_red_s"] == 1.0


def test_reject_empty_movements_and_preserve_state(workbench):
    """Verify unchecking all movements is rejected by validate_signal_plan (EMPTY_PHASE)."""
    workbench.phase_table.selectRow(0)

    # Uncheck all movements
    for i in range(workbench.list_phase_movements.count()):
        workbench.list_phase_movements.item(i).setCheckState(Qt.CheckState.Unchecked)

    assert workbench.apply_phase_edits() is False

    # Scenario data preserved
    plans = get_scenario_signal_plans(workbench.scenario_data)
    assert len(plans[0]["phases"][0]["movement_ids"]) > 0


def test_reject_conflicting_movements(workbench):
    """Verify assigning conflicting turning movements to the same phase is rejected."""
    # Add crossing roads and movements at I1:
    # Existing: R2 -> R1 (from [100, 0] to [0, 0], then [0, 0] to [100, 0])
    # Add a perpendicular road I3 [0, -100] -> I1 [0, 0] and I1 [0, 0] -> I4 [0, 100]
    network = workbench.scenario_data["network"]
    network["intersections"].extend([
        {"id": "I3", "position": [0, -100], "control_type": "uncontrolled"},
        {"id": "I4", "position": [0, 100], "control_type": "uncontrolled"},
    ])
    network["segments"].extend([
        {"id": "R3", "from": "I3", "to": "I1", "length_m": 100, "lane_count": 1, "speed_limit_mps": 13.9},
        {"id": "R4", "from": "I1", "to": "I4", "length_m": 100, "lane_count": 1, "speed_limit_mps": 13.9},
    ])
    # TM2 merges into R1, conflicting with TM1
    network["turning_movements"].append({
        "id": "TM2", "intersection": "I1", "from_segment": "R3", "to_segment": "R1"
    })

    # Trigger UI refresh
    workbench.on_network_modified()

    # Now checklist has TM1 and TM2
    checklist_ids = [
        workbench.list_phase_movements.item(i).data(Qt.ItemDataRole.UserRole)
        for i in range(workbench.list_phase_movements.count())
    ]
    assert "TM1" in checklist_ids
    assert "TM2" in checklist_ids

    # Check both TM1 and TM2 for Phase 1
    for i in range(workbench.list_phase_movements.count()):
        workbench.list_phase_movements.item(i).setCheckState(Qt.CheckState.Checked)

    # Applying must fail due to CONFLICTING_MOVEMENTS
    assert workbench.apply_phase_edits() is False

    # Previous valid plan preserved (only TM1)
    plans = get_scenario_signal_plans(workbench.scenario_data)
    assert plans[0]["phases"][0]["movement_ids"] == ["TM1"]


def test_refresh_editor_after_scenario_loading(workbench, tmp_path):
    """Verify editor UI refreshes properly when a new scenario file is loaded."""
    # Create a test scenario file with 2 phases at I1
    scen = copy.deepcopy(workbench.scenario_data)
    scen["scenario_id"] = "test-refresh-001"
    scen["signal_plan"]["phases"].append({
        "order": 2,
        "movement_ids": ["TM1"],
        "green_s": 12.0,
        "yellow_s": 2.0,
        "all_red_s": 1.0,
    })
    test_file = tmp_path / "scenario_two_phases.json"
    test_file.write_text(json.dumps(scen, indent=2), encoding="utf-8")

    success = workbench.load_scenario_file(test_file)
    assert success is True

    # Verify editor loaded 2 phases and updated cycle duration (24 + 15 = 39.0 s)
    assert workbench.phase_table.rowCount() == 2
    assert "39.0 s" in workbench.lbl_plan_cycle.text()


def test_live_signal_lamp_refresh_and_transitions(workbench):
    """Verify canvas signal lamp states reflect phase timings and advance through cycle."""
    # Initial state at t=0: Phase 1 is GREEN
    assert workbench.canvas.signal_plans["I1"].movement_state("TM1", 0.0) == "GREEN"

    # At t=21.0 s: Phase 1 green ends at 20.0 s, yellow is 20..23 -> YELLOW
    assert workbench.canvas.signal_plans["I1"].movement_state("TM1", 21.0) == "YELLOW"

    # At t=23.5 s: all-red clearance 23..24 -> RED
    assert workbench.canvas.signal_plans["I1"].movement_state("TM1", 23.5) == "RED"

    # At t=24.1 s: cycle wraparound (cycle=24s) -> GREEN
    assert workbench.canvas.signal_plans["I1"].movement_state("TM1", 24.1) == "GREEN"

    # Now edit green to 10s via UI
    workbench.phase_table.selectRow(0)
    workbench.edit_phase_green.setText("10.0")
    workbench.apply_phase_edits()

    # Now at t=11.0 s it should already be YELLOW (since green ended at 10.0 s)
    assert workbench.canvas.signal_plans["I1"].movement_state("TM1", 11.0) == "YELLOW"


def test_empty_state_when_no_signalized_intersections(workbench):
    """Verify clear empty-state messaging when no signalized intersections exist."""
    # Convert I1 to uncontrolled
    network = workbench.scenario_data["network"]
    for inter in network["intersections"]:
        inter["control_type"] = "uncontrolled"

    # Clear signal plans
    workbench.scenario_data.pop("signal_plan", None)
    workbench.scenario_data.pop("signal_plans", None)

    workbench.on_network_modified()

    # Editor should show empty-state message and hide table
    assert workbench.phase_table.isHidden()
    assert not workbench.lbl_plan_empty.isHidden()
    assert "No signalized intersections" in workbench.lbl_plan_empty.text()


def test_reject_unknown_movement_ids(workbench):
    """Verify phases referencing unknown turning movements are rejected."""
    workbench.phase_table.selectRow(0)

    # Inject an unknown movement item into the checklist and check it
    from PySide6.QtWidgets import QListWidgetItem
    bad_item = QListWidgetItem("TM_GHOST")
    bad_item.setData(Qt.ItemDataRole.UserRole, "TM_GHOST")
    bad_item.setFlags(bad_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
    bad_item.setCheckState(Qt.CheckState.Checked)
    workbench.list_phase_movements.addItem(bad_item)

    # Applying must fail with UNKNOWN_MOVEMENT
    assert workbench.apply_phase_edits() is False

    # Previous valid plan preserved
    plans = get_scenario_signal_plans(workbench.scenario_data)
    assert "TM_GHOST" not in plans[0]["phases"][0]["movement_ids"]


def test_create_signal_plan_for_intersection(workbench):
    """Verify creating a signal plan for a signalized intersection with turning movements."""
    # Add a signalized intersection I3 with road segment R3 and turning movement TM_I3
    network = workbench.scenario_data["network"]
    network["intersections"].append({
        "id": "I3", "position": [200, 0], "control_type": "signalized"
    })
    network["segments"].append({
        "id": "R3", "from": "I2", "to": "I3", "length_m": 100, "lane_count": 1, "speed_limit_mps": 13.9
    })
    network["segments"].append({
        "id": "R4", "from": "I3", "to": "I2", "length_m": 100, "lane_count": 1, "speed_limit_mps": 13.9
    })
    network["turning_movements"].append({
        "id": "TM_I3", "intersection": "I3", "from_segment": "R3", "to_segment": "R4"
    })

    workbench.on_network_modified()

    # Select I3 in combo
    idx = workbench.combo_signal_plan.findData("I3")
    assert idx >= 0
    workbench.combo_signal_plan.setCurrentIndex(idx)

    # Currently I3 has no plan; create button is visible
    assert not workbench.btn_create_plan.isHidden()

    # Click create plan
    workbench.create_signal_plan_for_selected()

    # Now plan exists with 1 phase
    assert workbench.phase_table.rowCount() == 1
    assert "TM_I3" in workbench.phase_table.item(0, 4).text()
    assert workbench.canvas.signal_plans["I3"] is not None
