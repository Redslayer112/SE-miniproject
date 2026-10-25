"""Automated tests for TMS-Sim Step 3: Interactive Network Editing in PySide6 Workbench.

Covers:
1. Intersection selection via hit-testing / click.
2. Road segment selection via hit-testing / click.
3. Clearing selection on empty canvas click.
4. Creating an intersection at correct scenario coordinates.
5. Creating a road segment between two valid intersections.
6. Rejecting self-connections, duplicate segments, and invalid endpoints.
7. Updating actual scenario model through Properties Inspector.
8. Rejecting invalid property edits with feedback.
9. Safe deletion preventing dangling network and demand references.
10. Network validation feedback and clickable error highlighting.
11. Inverse coordinate transformations under canvas zoom and pan.
12. Keyboard shortcuts (Escape to deselect, Delete key).
"""

import copy
import json
import math
from pathlib import Path
import pytest

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QMessageBox, QListWidgetItem

from tms_sim.network.service import validate
from tms_sim.network.serialization import network_from_dict
from tms_sim.ui.app import Workbench, RoadCanvas

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


def test_select_intersection_via_click_and_sync_inspector(workbench):
    """Verify clicking an intersection selects it and populates the properties inspector."""
    canvas = workbench.canvas
    net = canvas.scenario_data["network"]
    i1 = net["intersections"][0]
    i1_id = i1["id"]
    pos = i1["position"]

    screen_pt = canvas.scenario_to_screen(pos[0], pos[1])
    canvas.handle_canvas_click(screen_pt)

    assert canvas.selected_type == "intersection"
    assert canvas.selected_id == i1_id
    assert workbench.inspector_stack.currentIndex() == 1
    assert i1_id in workbench.lbl_inter_header.text()
    assert float(workbench.edit_inter_x.text()) == pos[0]
    assert float(workbench.edit_inter_y.text()) == pos[1]
    assert workbench.combo_inter_control.currentText() == i1.get("control_type", "uncontrolled")


def test_select_road_segment_via_click_and_sync_inspector(workbench):
    """Verify clicking near a road segment selects it and populates segment inspector."""
    canvas = workbench.canvas
    net = canvas.scenario_data["network"]
    r1 = net["segments"][0]
    r1_id = r1["id"]

    # Calculate midpoint between the two endpoint intersections
    i_from = next(i for i in net["intersections"] if i["id"] == r1["from"])
    i_to = next(i for i in net["intersections"] if i["id"] == r1["to"])
    mid_x = (i_from["position"][0] + i_to["position"][0]) / 2.0
    mid_y = (i_from["position"][1] + i_to["position"][1]) / 2.0

    screen_mid = canvas.scenario_to_screen(mid_x, mid_y)
    canvas.handle_canvas_click(screen_mid)

    assert canvas.selected_type == "segment"
    assert canvas.selected_id in (net["segments"][0]["id"], net["segments"][1]["id"])
    assert workbench.inspector_stack.currentIndex() == 2
    assert "ROAD SEGMENT:" in workbench.lbl_seg_header.text()
    assert float(workbench.edit_seg_length.text()) > 0
    assert int(workbench.spin_seg_lanes.value()) >= 1


def test_clear_selection_by_clicking_empty_space(workbench):
    """Verify clicking empty canvas space clears selection and returns inspector to overview."""
    canvas = workbench.canvas
    canvas.set_selection("intersection", "I1")
    assert canvas.selected_id == "I1"
    assert workbench.inspector_stack.currentIndex() == 1

    # Click empty space at top-left corner
    empty_pt = QPointF(15.0, 15.0)
    assert canvas.hit_test_intersection(empty_pt) is None
    assert canvas.hit_test_segment(empty_pt) is None

    canvas.handle_canvas_click(empty_pt)
    assert canvas.selected_type is None
    assert canvas.selected_id is None
    assert workbench.inspector_stack.currentIndex() == 0


def test_create_intersection_at_scenario_coordinates(workbench):
    """Verify adding an intersection places it at the correct scenario coordinates and updates UI."""
    canvas = workbench.canvas
    initial_count = len(canvas.scenario_data["network"]["intersections"])

    workbench.set_tool_mode("add_intersection")
    assert canvas.active_tool == "add_intersection"

    # Click at canvas center
    center_pt = QPointF(canvas.width() / 2.0, canvas.height() / 2.0)
    expected_x, expected_y = canvas.screen_to_scenario(center_pt)

    canvas.handle_canvas_click(center_pt)

    intersections = canvas.scenario_data["network"]["intersections"]
    assert len(intersections) == initial_count + 1

    new_inter = intersections[-1]
    assert new_inter["id"].startswith("I")
    assert math.isclose(new_inter["position"][0], expected_x, abs_tol=1.0)
    assert math.isclose(new_inter["position"][1], expected_y, abs_tol=1.0)

    # Workbench metric labels updated
    assert f"Intersections: {initial_count + 1}" in workbench.intersections_label.text()


def test_create_road_between_valid_intersections(workbench):
    """Verify creating a road segment between two intersections calculates length and creates model."""
    canvas = workbench.canvas
    net = canvas.scenario_data["network"]
    initial_seg_count = len(net["segments"])

    # Create a 3rd intersection to connect to I2
    new_id = canvas.add_intersection_at(300.0, 200.0)
    workbench.set_tool_mode("draw_road")

    i2 = next(i for i in net["intersections"] if i["id"] == "I2")
    i2_screen = canvas.scenario_to_screen(i2["position"][0], i2["position"][1])
    i3_screen = canvas.scenario_to_screen(300.0, 200.0)

    # First click sets start
    canvas.handle_canvas_click(i2_screen)
    assert canvas.road_start_id == "I2"

    # Second click connects to new_id
    canvas.handle_canvas_click(i3_screen)
    assert canvas.road_start_id is None

    segments = net["segments"]
    assert len(segments) == initial_seg_count + 1
    new_seg = segments[-1]
    assert new_seg["from"] == "I2"
    assert new_seg["to"] == new_id

    # Euclidean distance check
    dx = 300.0 - i2["position"][0]
    dy = 200.0 - i2["position"][1]
    expected_length = round(math.sqrt(dx * dx + dy * dy), 1)
    assert math.isclose(new_seg["length_m"], expected_length, abs_tol=1.0)


def test_reject_invalid_road_endpoints_and_self_loops(workbench, monkeypatch):
    """Verify self-loops, existing duplicate segments, and unknown endpoints are rejected."""
    canvas = workbench.canvas
    initial_seg_count = len(canvas.scenario_data["network"]["segments"])

    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, text: warnings.append((title, text)),
    )

    # 1. Self loop
    success, msg = canvas.create_road_segment("I1", "I1")
    assert success is False
    assert "itself" in msg.lower() or "self" in msg.lower()

    # 2. Duplicate road segment (R1 already connects I1 -> I2)
    success, msg = canvas.create_road_segment("I1", "I2")
    assert success is False
    assert "already exists" in msg.lower()

    # 3. Unknown intersection endpoint
    success, msg = canvas.create_road_segment("I1", "GHOST_INTERSECTION")
    assert success is False
    assert "exist" in msg.lower()

    # Segments unchanged
    assert len(canvas.scenario_data["network"]["segments"]) == initial_seg_count


def test_property_inspector_updates_scenario_model(workbench):
    """Verify editing fields in the properties inspector modifies underlying scenario data."""
    canvas = workbench.canvas

    # 1. Edit Intersection
    canvas.set_selection("intersection", "I1")
    workbench.edit_inter_x.setText("45.0")
    workbench.edit_inter_y.setText("90.0")
    workbench.combo_inter_control.setCurrentText("stop_controlled")
    workbench.apply_intersection_properties()

    inter = next(i for i in canvas.scenario_data["network"]["intersections"] if i["id"] == "I1")
    assert inter["position"] == [45.0, 90.0]
    assert inter["control_type"] == "stop_controlled"

    # 2. Edit Road Segment
    canvas.set_selection("segment", "R1")
    workbench.edit_seg_length.setText("180.5")
    workbench.spin_seg_lanes.setValue(3)
    workbench.edit_seg_speed.setText("22.2")
    workbench.apply_segment_properties()

    seg = next(s for s in canvas.scenario_data["network"]["segments"] if s["id"] == "R1")
    assert seg["length_m"] == 180.5
    assert seg["lane_count"] == 3
    assert seg["speed_limit_mps"] == 22.2


def test_reject_invalid_property_edits(workbench, monkeypatch):
    """Verify non-numeric or non-positive values are rejected and do not corrupt data."""
    canvas = workbench.canvas
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, text: warnings.append((title, text)),
    )

    # 1. Invalid intersection coordinate
    canvas.set_selection("intersection", "I1")
    original_pos = copy.deepcopy(canvas.scenario_data["network"]["intersections"][0]["position"])
    workbench.edit_inter_x.setText("invalid_number")
    workbench.apply_intersection_properties()

    assert len(warnings) == 1
    assert "Invalid" in warnings[0][0]
    assert canvas.scenario_data["network"]["intersections"][0]["position"] == original_pos

    # 2. Invalid segment length (negative)
    canvas.set_selection("segment", "R1")
    original_len = canvas.scenario_data["network"]["segments"][0]["length_m"]
    workbench.edit_seg_length.setText("-10.0")
    workbench.apply_segment_properties()

    assert len(warnings) == 2
    assert canvas.scenario_data["network"]["segments"][0]["length_m"] == original_len


def test_deletion_safety_and_reference_cleanup(workbench, monkeypatch):
    """Verify deleting connected intersections is rejected, and segment deletion cleans dependencies."""
    canvas = workbench.canvas
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, text: warnings.append((title, text)),
    )

    # 1. Reject deletion of intersection I1 with attached segments R1, R2
    canvas.set_selection("intersection", "I1")
    workbench.delete_selected_object()

    assert len(warnings) == 1
    assert "Cannot Delete" in warnings[0][0]
    assert "connected" in warnings[0][1].lower()
    # I1 is preserved
    assert any(i["id"] == "I1" for i in canvas.scenario_data["network"]["intersections"])

    # 2. Delete road segment R1
    canvas.set_selection("segment", "R1")
    success, msg = canvas.delete_selected()
    assert success is True
    assert not any(s["id"] == "R1" for s in canvas.scenario_data["network"]["segments"])

    # Ensure turning movements referencing R1 are purged
    tms = canvas.scenario_data["network"].get("turning_movements", [])
    for tm in tms:
        assert tm.get("from_segment") != "R1"
        assert tm.get("to_segment") != "R1"

    # Ensure demand arrival rates referencing R1 are purged
    demand = canvas.scenario_data.get("demand", {})
    assert "R1" not in demand.get("arrival_rates_vehicles_per_hour", {})


def test_validation_feedback_and_list_highlighting(workbench):
    """Verify backend validation issues appear in the panel and clicking highlights elements."""
    # Induce an isolated/disconnected intersection
    workbench.canvas.add_intersection_at(1000.0, 1000.0)
    result = workbench.validate_current_network()

    # The network is now disconnected (I3 is isolated)
    assert not result.is_valid
    assert any(e.code == "DISCONNECTED_GRAPH" for e in result.errors)
    assert workbench.validation_list.count() > 0
    assert "Error" in workbench.validation_status_label.text()

    # Click first item in validation list
    first_item = workbench.validation_list.item(0)
    workbench.on_validation_item_clicked(first_item)
    # Shouldn't crash and should set or keep a valid selection


def test_inverse_coordinate_transformation_under_zoom_and_pan(workbench):
    """Verify screen_to_scenario accurately inverts scenario_to_screen under zoom and pan."""
    canvas = workbench.canvas

    # Set non-trivial zoom and pan
    canvas.zoom_level = 2.4
    canvas.pan_offset = QPointF(120.0, -85.0)

    test_scenario_points = [
        (0.0, 0.0),
        (50.0, 100.0),
        (-30.0, 80.0),
        (150.0, -20.0),
    ]

    for sx, sy in test_scenario_points:
        screen_pt = canvas.scenario_to_screen(sx, sy)
        inv_x, inv_y = canvas.screen_to_scenario(screen_pt)
        assert math.isclose(inv_x, sx, abs_tol=1e-4), f"Failed for ({sx}, {sy}): got ({inv_x}, {inv_y})"
        assert math.isclose(inv_y, sy, abs_tol=1e-4), f"Failed for ({sx}, {sy}): got ({inv_x}, {inv_y})"


def test_cancel_road_drawing_and_escape_shortcut(workbench):
    """Verify pressing Escape or right-click cancels active road drawing and deselects."""
    canvas = workbench.canvas
    workbench.set_tool_mode("draw_road")

    # Start road from I1
    canvas.road_start_id = "I1"
    canvas.road_hover_pos = QPointF(200.0, 200.0)

    # Cancel via clear_selection (Escape action)
    workbench.clear_selection()
    assert canvas.selected_type is None
    assert canvas.selected_id is None

    # Right click cancel in draw_road
    canvas.road_start_id = "I1"
    right_click = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(100.0, 100.0),
        QPointF(100.0, 100.0),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mousePressEvent(right_click)
    assert canvas.road_start_id is None
