"""Tests for live traffic signal visualization, mouse-wheel zoom, and panning in RoadCanvas."""

import copy
import json
from pathlib import Path
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent, QMouseEvent, QPaintEvent, QPixmap, QPainter
from PySide6.QtWidgets import QApplication

from tms_sim.signal import SignalPhase, SignalPlan
from tms_sim.ui.app import Workbench, RoadCanvas

SAMPLE_SCENARIO_PATH = (
    Path(__file__).resolve().parent / "data" / "scenario" / "small_valid_scenario.json"
)


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QApplication instance exists."""
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


def test_signal_plan_movement_state_timing_semantics():
    """Verify SignalPlan.movement_state calculates Green, Yellow, and Red windows correctly."""
    # Single-phase plan from small_valid_scenario: green=20, yellow=3, all_red=1 (cycle=24s)
    plan = SignalPlan("I1", (SignalPhase(1, ("TM1",), green_s=20.0, yellow_s=3.0, all_red_s=1.0),))
    assert plan.cycle_time_s == 24.0

    # Green window: [0.0, 20.0)
    assert plan.movement_state("TM1", 0.0) == "GREEN"
    assert plan.movement_state("TM1", 10.0) == "GREEN"
    assert plan.movement_state("TM1", 19.9) == "GREEN"

    # Yellow window: [20.0, 23.0)
    assert plan.movement_state("TM1", 20.0) == "YELLOW"
    assert plan.movement_state("TM1", 21.5) == "YELLOW"
    assert plan.movement_state("TM1", 22.99) == "YELLOW"

    # All-red clearance window: [23.0, 24.0)
    assert plan.movement_state("TM1", 23.0) == "RED"
    assert plan.movement_state("TM1", 23.9) == "RED"

    # Wraparound to next cycle: [24.0, 44.0) -> Green
    assert plan.movement_state("TM1", 24.0) == "GREEN"
    assert plan.movement_state("TM1", 43.9) == "GREEN"
    assert plan.movement_state("TM1", 44.0) == "YELLOW"

    # Unknown movement should be RED
    assert plan.movement_state("UNKNOWN", 10.0) == "RED"


def test_multi_phase_conflicting_movements_never_green_together():
    """Verify that under a two-phase plan, conflicting movements never show green simultaneously."""
    # Phase 1: SN gets 20s green, 3s yellow, 1s red (duration 24s)
    # Phase 2: WE gets 10s green, 3s yellow, 1s red (duration 14s)
    # Total cycle = 38s
    plan = SignalPlan(
        "I_Cross",
        (
            SignalPhase(1, ("SN",), green_s=20.0, yellow_s=3.0, all_red_s=1.0),
            SignalPhase(2, ("WE",), green_s=10.0, yellow_s=3.0, all_red_s=1.0),
        ),
    )
    assert plan.cycle_time_s == 38.0

    # At t=10: Phase 1 green
    assert plan.movement_state("SN", 10.0) == "GREEN"
    assert plan.movement_state("WE", 10.0) == "RED"
    assert plan.intersection_state(10.0) == "GREEN"

    # At t=21: Phase 1 yellow
    assert plan.movement_state("SN", 21.0) == "YELLOW"
    assert plan.movement_state("WE", 21.0) == "RED"
    assert plan.intersection_state(21.0) == "YELLOW"

    # At t=23.5: Phase 1 all-red clearance
    assert plan.movement_state("SN", 23.5) == "RED"
    assert plan.movement_state("WE", 23.5) == "RED"
    assert plan.intersection_state(23.5) == "RED"

    # At t=25: Phase 2 green (starts at 24.0, runs to 34.0)
    assert plan.movement_state("SN", 25.0) == "RED"
    assert plan.movement_state("WE", 25.0) == "GREEN"
    assert plan.intersection_state(25.0) == "GREEN"

    # At t=35: Phase 2 yellow (runs to 37.0)
    assert plan.movement_state("SN", 35.0) == "RED"
    assert plan.movement_state("WE", 35.0) == "YELLOW"
    assert plan.intersection_state(35.0) == "YELLOW"

    # At t=37.5: Phase 2 all-red clearance (runs to 38.0)
    assert plan.movement_state("SN", 37.5) == "RED"
    assert plan.movement_state("WE", 37.5) == "RED"
    assert plan.intersection_state(37.5) == "RED"

    # At t=38: cycle restarts, SN green again
    assert plan.movement_state("SN", 38.0) == "GREEN"
    assert plan.movement_state("WE", 38.0) == "RED"


def test_canvas_signal_state_updates_with_simulation_clock(workbench):
    """Verify that canvas signal state advances dynamically with the simulation engine clock."""
    canvas = workbench.canvas
    assert "I1" in canvas.signal_plans
    plan = canvas.signal_plans["I1"]

    # Initial time is 0.0 -> GREEN
    assert workbench.engine.time == 0.0
    assert plan.movement_state("TM1", workbench.engine.time) == "GREEN"

    # Advance engine to yellow phase (t >= 20.0s)
    # The default time step is 0.1s, 201 steps = 20.1s
    for _ in range(201):
        workbench.engine.step()

    assert workbench.engine.time == pytest.approx(20.1, abs=0.01)
    assert plan.movement_state("TM1", workbench.engine.time) == "YELLOW"

    # Advance to all-red clearance interval (t >= 23.0s)
    for _ in range(30):
        workbench.engine.step()

    assert workbench.engine.time == pytest.approx(23.1, abs=0.01)
    assert plan.movement_state("TM1", workbench.engine.time) == "RED"


def test_canvas_signal_state_preserved_when_paused(workbench):
    """Verify signal state remains stable while the simulation is paused."""
    canvas = workbench.canvas
    plan = canvas.signal_plans["I1"]

    # Advance into yellow phase
    for _ in range(205):
        workbench.engine.step()

    frozen_time = workbench.engine.time
    workbench.pause_simulation()
    assert workbench.engine.running is False

    # Check signal state
    state_before = plan.movement_state("TM1", workbench.engine.time)
    assert state_before == "YELLOW"

    # Advance timer multiple times while paused (engine should not advance)
    for _ in range(5):
        workbench.advance_simulation()

    assert workbench.engine.time == frozen_time
    assert plan.movement_state("TM1", workbench.engine.time) == "YELLOW"


def test_canvas_signal_state_restored_on_reset(workbench):
    """Verify reset restores the signal state to the initial simulation clock time."""
    canvas = workbench.canvas
    plan = canvas.signal_plans["I1"]

    # Advance to yellow phase
    for _ in range(205):
        workbench.engine.step()
    assert plan.movement_state("TM1", workbench.engine.time) == "YELLOW"

    # Reset simulation
    workbench.reset_simulation()
    assert workbench.engine.time == 0.0
    assert plan.movement_state("TM1", workbench.engine.time) == "GREEN"


def test_zoom_limits_and_clamping(qapp):
    """Verify zoom levels are strictly clamped within [MIN_ZOOM, MAX_ZOOM]."""
    canvas = RoadCanvas()

    # Default is 1.0
    assert canvas.zoom_level == 1.0

    # Set below minimum
    canvas.set_zoom(0.05)
    assert canvas.zoom_level == canvas.MIN_ZOOM
    assert canvas.zoom_level == 0.2

    # Set above maximum
    canvas.set_zoom(20.0)
    assert canvas.zoom_level == canvas.MAX_ZOOM
    assert canvas.zoom_level == 5.0

    # Set intermediate
    canvas.set_zoom(1.8)
    assert canvas.zoom_level == 1.8

    # Reset view
    canvas.reset_view()
    assert canvas.zoom_level == 1.0
    assert canvas.pan_offset == QPointF(0.0, 0.0)


def test_mouse_wheel_zoom_invariant(qapp):
    """Verify wheel zoom around a cursor preserves the cursor's focus point."""
    canvas = RoadCanvas()
    canvas.resize(800, 600)
    canvas.show()

    # Simulate wheel zoom in at cursor (300, 250)
    cursor_pos = QPointF(300.0, 250.0)
    center = QPointF(400.0, 300.0)

    # Wheel event: angleDelta y = 120 (one tick in)
    event = QWheelEvent(
        cursor_pos,
        cursor_pos,
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    old_zoom = canvas.zoom_level
    old_pan = canvas.pan_offset

    canvas.wheelEvent(event)

    assert canvas.zoom_level > old_zoom
    # Verify the invariant mathematically:
    # (cursor_pos - center) - (new_zoom / old_zoom) * (cursor_pos - center - old_pan) == new_pan
    ratio = canvas.zoom_level / old_zoom
    expected_pan = (cursor_pos - center) - ratio * (cursor_pos - center - old_pan)
    assert canvas.pan_offset.x() == pytest.approx(expected_pan.x(), abs=1e-3)
    assert canvas.pan_offset.y() == pytest.approx(expected_pan.y(), abs=1e-3)

    canvas.close()


def test_mouse_drag_panning_updates_offset_without_mutating_scenario(workbench):
    """Verify panning updates pan_offset and preserves underlying scenario coordinates."""
    canvas = workbench.canvas
    canvas.resize(800, 600)

    initial_pan = QPointF(canvas.pan_offset)
    original_positions = copy.deepcopy(
        canvas.scenario_data["network"]["intersections"]
    )

    # Simulate mouse press at (150, 150)
    pos1 = QPointF(150.0, 150.0)
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        pos1,
        pos1,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mousePressEvent(press_event)
    assert canvas._is_panning is True

    # Drag to (220, 190) -> delta = (+70, +40)
    pos2 = QPointF(220.0, 190.0)
    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        pos2,
        pos2,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mouseMoveEvent(move_event)
    assert canvas.pan_offset == initial_pan + QPointF(70.0, 40.0)

    # Release
    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        pos2,
        pos2,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mouseReleaseEvent(release_event)
    assert canvas._is_panning is False

    # Ensure original scenario data remains completely untouched
    assert canvas.scenario_data["network"]["intersections"] == original_positions


def test_reset_view_button_resets_zoom_and_pan(workbench):
    """Verify clicking the Reset View button restores zoom=1.0 and pan=(0,0)."""
    canvas = workbench.canvas
    canvas.set_zoom(2.5)
    canvas.pan_offset = QPointF(120.0, -80.0)

    workbench.reset_view_button.click()

    assert canvas.zoom_level == 1.0
    assert canvas.pan_offset == QPointF(0.0, 0.0)


def test_canvas_rendering_empty_and_degenerate_networks(qapp):
    """Verify RoadCanvas handles empty or single-node networks without crashing or division by zero."""
    canvas = RoadCanvas()
    canvas.resize(600, 400)

    # 1. Empty network
    canvas.set_scenario(None, {})
    pixmap = QPixmap(600, 400)
    canvas.render(pixmap)
    assert not pixmap.isNull()

    # 2. Single node (span_x = 0, span_y = 0)
    degenerate_scenario = {
        "network": {
            "intersections": [{"id": "SOLO", "position": [50, 50]}],
            "segments": [],
        }
    }
    canvas.set_scenario(None, degenerate_scenario)
    canvas.render(pixmap)
    assert not pixmap.isNull()

    # 3. Two nodes with no segments
    two_nodes_no_segs = {
        "network": {
            "intersections": [
                {"id": "A", "position": [0, 0]},
                {"id": "B", "position": [10, 10]},
            ],
            "segments": [],
        }
    }
    canvas.set_scenario(None, two_nodes_no_segs)
    canvas.render(pixmap)
    assert not pixmap.isNull()
