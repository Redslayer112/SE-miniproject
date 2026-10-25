"""TMS-Sim desktop workbench with interactive network editing and simulation engine."""

import copy
import json
import logging
import math
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QComboBox,
    QSplitter,
    QMessageBox,
    QFileDialog,
    QStackedWidget,
    QLineEdit,
    QSpinBox,
    QFormLayout,
    QButtonGroup,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QScrollArea,
    QGridLayout,
    QProgressBar,
    QTextEdit,
    QPlainTextEdit,
    QAbstractSpinBox,
)

from tms_sim.network import (
    ControlType,
    NetworkBlockedError,
    NetworkFormatError,
    validate,
    ValidationIssue,
    ValidationResult,
)
from tms_sim.network.serialization import network_from_dict
from tms_sim.reporting.history import SimulationHistoryTracker
from tms_sim.reporting.metrics import compute_metrics
from tms_sim.signal import SignalPlan, SignalPhase, SignalPlanBlockedError
from tms_sim.signal.validation import validate_signal_plan
from tms_sim.signal.serialization import plan_from_dict, plan_to_dict
from tms_sim.sim.demand import DemandError, validate_demand
from tms_sim.sim.scenario import build_engine, load_scenario
from tms_sim.sim.serialization import (
    ScenarioFormatError,
    load_scenario_document,
    save_scenario_document,
)
from tms_sim.ui.charts import LivePerformancePanel
from tms_sim.ui.history import ScenarioHistoryManager

logger = logging.getLogger(__name__)


def get_scenario_signal_plans(scenario_data: dict) -> list[dict]:
    """Retrieve raw signal plan dictionaries from scenario data."""
    if "signal_plans" in scenario_data and isinstance(scenario_data["signal_plans"], list):
        return scenario_data["signal_plans"]
    elif "signal_plan" in scenario_data and isinstance(scenario_data["signal_plan"], dict):
        return [scenario_data["signal_plan"]]
    return []


def set_scenario_signal_plans(scenario_data: dict, plans_list: list[dict]) -> None:
    """Store raw signal plan dictionaries preserving single/multi plan schema constraints."""
    if len(plans_list) > 1:
        scenario_data["signal_plans"] = plans_list
        scenario_data.pop("signal_plan", None)
    elif len(plans_list) == 1:
        if "signal_plans" in scenario_data:
            scenario_data["signal_plans"] = plans_list
            scenario_data.pop("signal_plan", None)
        else:
            scenario_data["signal_plan"] = plans_list[0]
            scenario_data.pop("signal_plans", None)
    else:
        if "signal_plans" in scenario_data:
            scenario_data["signal_plans"] = []
        elif "signal_plan" in scenario_data:
            scenario_data["signal_plan"] = {}


def generate_unique_id(prefix: str, existing_ids: list[str]) -> str:
    """Generate the next unique identifier following the project's standard prefix convention (e.g. I1 -> I2, R1 -> R2)."""
    nums = []
    for eid in existing_ids:
        if eid.startswith(prefix) and eid[len(prefix):].isdigit():
            nums.append(int(eid[len(prefix):]))
    next_num = (max(nums) + 1) if nums else 1
    candidate = f"{prefix}{next_num}"
    while candidate in existing_ids:
        next_num += 1
        candidate = f"{prefix}{next_num}"
    return candidate


def safe_font(family: str = "Segoe UI", point_size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Return a QFont with a guaranteed positive integer point size, safely handling unspecified (-1) sizes."""
    valid_size = int(point_size) if point_size and int(point_size) > 0 else 10
    font = QFont(family, valid_size, weight)
    if font.pointSize() <= 0:
        font.setPointSize(valid_size)
    return font


class RoadCanvas(QWidget):
    """Draw the loaded scenario network, live traffic signals, and moving vehicles.

    Supports interactive mouse-wheel zooming around the cursor, click-and-drag panning,
    and interactive network editing (selection, intersection placement, road segment drawing).
    """

    ROAD_COLOR = QColor("#a8b0bb")
    ROAD_EDGE = QColor("#8792a1")
    BACKGROUND = QColor("#e9eee9")
    VEHICLE_COLORS = [
        QColor("#2563eb"),
        QColor("#f97316"),
        QColor("#7c3aed"),
        QColor("#0f766e"),
        QColor("#db2777"),
        QColor("#0891b2"),
    ]
    COLOR_GREEN = QColor("#22c55e")
    COLOR_YELLOW = QColor("#eab308")
    COLOR_RED = QColor("#ef4444")
    COLOR_UNSIGNALIZED = QColor("#94a3b8")
    COLOR_SELECTION = QColor("#2563eb")

    MIN_ZOOM = 0.2
    MAX_ZOOM = 5.0
    DEFAULT_ZOOM = 1.0

    # Signals to communicate user actions with Workbench
    selection_changed = Signal(str, str)  # (element_type, element_id) or ("", "")
    network_modified = Signal()
    tool_status_message = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(500, 350)
        self.engine = None
        self.scenario_data = {}
        self.signal_plans: dict[str, SignalPlan] = {}
        self.zoom_level: float = self.DEFAULT_ZOOM
        self.pan_offset: QPointF = QPointF(0.0, 0.0)

        # Tools & Selection state
        self.active_tool: str = "select"
        self.selected_type: str | None = None
        self.selected_id: str | None = None
        self.road_start_id: str | None = None
        self.road_hover_pos: QPointF | None = None

        # Panning state
        self._is_panning: bool = False
        self._pan_start: QPointF = QPointF()
        self._mouse_press_pos: QPointF | None = None
        self._has_dragged: bool = False
        self._press_pan_offset: QPointF = QPointF()

        self.setStyleSheet("background: #e9eee9;")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_scenario(self, engine, scenario_data):
        """Bind a simulation engine and scenario document, re-parsing signal plans and resetting view."""
        self.engine = engine
        self.scenario_data = scenario_data or {}
        self.reparse_signal_plans()
        self.set_selection(None, None)
        self.road_start_id = None
        self.road_hover_pos = None
        self.reset_view()
        self.update()

    def reparse_signal_plans(self):
        """Parse signal plans from scenario_data for visualization."""
        self.signal_plans = {}
        if self.scenario_data:
            raw_plans = get_scenario_signal_plans(self.scenario_data)
            for p in raw_plans:
                try:
                    plan_obj = plan_from_dict({"signal_plan": p})
                    self.signal_plans[plan_obj.intersection_id] = plan_obj
                except Exception as exc:
                    logger.debug("Could not parse signal plan for visualization: %s", exc)

    def reset_view(self):
        """Reset canvas zoom level and pan offset to default centered view."""
        self.zoom_level = self.DEFAULT_ZOOM
        self.pan_offset = QPointF(0.0, 0.0)
        self.update()

    def set_zoom(self, zoom: float):
        """Directly set zoom level clamped to allowed range."""
        self.zoom_level = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(zoom)))
        self.update()

    def set_active_tool(self, tool: str):
        """Switch current interaction tool ('select', 'add_intersection', 'draw_road')."""
        self.active_tool = tool
        self.road_start_id = None
        self.road_hover_pos = None
        self.update()

    def set_selection(self, element_type: str | None, element_id: str | None):
        """Select an intersection or road segment, emitting selection_changed."""
        if self.selected_type != element_type or self.selected_id != element_id:
            self.selected_type = element_type
            self.selected_id = element_id
            self.selection_changed.emit(element_type or "", element_id or "")
            self.update()

    def get_coordinate_bounds(self):
        """Compute the bounding box of intersection coordinates in scenario space."""
        network = self.scenario_data.get("network", {})
        intersections = network.get("intersections", [])
        raw_positions = []
        for intersection in intersections:
            pos = intersection.get("position")
            if isinstance(pos, list) and len(pos) >= 2:
                raw_positions.append((float(pos[0]), float(pos[1])))

        if not raw_positions:
            return 0.0, 100.0, 0.0, 100.0

        xs = [p[0] for p in raw_positions]
        ys = [p[1] for p in raw_positions]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 100.0 if max_x == min_x else 1.0)
        span_y = max(max_y - min_y, 100.0 if max_y == min_y else 1.0)
        return min_x, span_x, min_y, span_y

    def scenario_to_screen(self, pos_or_x, y=None) -> QPointF:
        """Forward coordinate transformation: scenario (x, y) -> canvas QPointF."""
        if y is None:
            x, y = pos_or_x
        else:
            x = pos_or_x
        min_x, span_x, min_y, span_y = self.get_coordinate_bounds()
        margin = 55
        width = max(1, self.width())
        height = max(1, self.height())
        draw_w = max(1, width - 2 * margin)
        draw_h = max(1, height - 2 * margin)
        center = QPointF(width / 2.0, height / 2.0)

        base_sx = margin + ((x - min_x) / span_x) * draw_w
        base_sy = height / 2.0 - ((y - min_y) / span_y) * min(draw_h, 120.0)
        base_pt = QPointF(base_sx, base_sy)
        return center + self.pan_offset + (base_pt - center) * self.zoom_level

    def screen_to_scenario(self, screen_pt: QPointF) -> tuple[float, float]:
        """Inverse coordinate transformation: canvas QPointF -> scenario (x, y)."""
        min_x, span_x, min_y, span_y = self.get_coordinate_bounds()
        margin = 55
        width = max(1, self.width())
        height = max(1, self.height())
        draw_w = max(1, width - 2 * margin)
        draw_h = max(1, height - 2 * margin)
        center = QPointF(width / 2.0, height / 2.0)

        # 1. Invert zoom and pan
        base_pt = center + (screen_pt - center - self.pan_offset) / self.zoom_level
        # 2. Invert base coordinate mapping
        x = min_x + ((base_pt.x() - margin) / draw_w) * span_x
        scale_h = min(draw_h, 120.0)
        y = min_y + ((height / 2.0 - base_pt.y()) / scale_h) * span_y
        return x, y

    def hit_test_intersection(self, screen_pt: QPointF, tolerance: float = 14.0) -> dict | None:
        """Find the closest intersection within hit tolerance distance of a screen point."""
        network = self.scenario_data.get("network", {})
        intersections = network.get("intersections", [])
        closest_item = None
        closest_dist = float("inf")
        for item in intersections:
            pos = item.get("position")
            if not isinstance(pos, list) or len(pos) < 2:
                continue
            pt = self.scenario_to_screen((float(pos[0]), float(pos[1])))
            dx = screen_pt.x() - pt.x()
            dy = screen_pt.y() - pt.y()
            dist = (dx * dx + dy * dy) ** 0.5
            radius = max(9.0, min(20.0, 12.0 * min(1.8, max(0.7, self.zoom_level))))
            if dist <= radius + tolerance and dist < closest_dist:
                closest_dist = dist
                closest_item = item
        return closest_item

    def hit_test_segment(self, screen_pt: QPointF, tolerance: float = 10.0) -> dict | None:
        """Find the closest road segment within hit tolerance distance of a screen point."""
        network = self.scenario_data.get("network", {})
        segments = network.get("segments", [])
        intersections = {i["id"]: i for i in network.get("intersections", [])}
        closest_item = None
        closest_dist = float("inf")

        for segment in segments:
            from_inter = intersections.get(segment.get("from"))
            to_inter = intersections.get(segment.get("to"))
            if not from_inter or not to_inter:
                continue
            pos_a = from_inter.get("position")
            pos_b = to_inter.get("position")
            if not isinstance(pos_a, list) or len(pos_a) < 2 or not isinstance(pos_b, list) or len(pos_b) < 2:
                continue

            p1 = self.scenario_to_screen((float(pos_a[0]), float(pos_a[1])))
            p2 = self.scenario_to_screen((float(pos_b[0]), float(pos_b[1])))

            vx = p2.x() - p1.x()
            vy = p2.y() - p1.y()
            len_sq = vx * vx + vy * vy
            if len_sq == 0:
                dist = ((screen_pt.x() - p1.x()) ** 2 + (screen_pt.y() - p1.y()) ** 2) ** 0.5
            else:
                t = max(0.0, min(1.0, ((screen_pt.x() - p1.x()) * vx + (screen_pt.y() - p1.y()) * vy) / len_sq))
                proj_x = p1.x() + t * vx
                proj_y = p1.y() + t * vy
                dist = ((screen_pt.x() - proj_x) ** 2 + (screen_pt.y() - proj_y) ** 2) ** 0.5

            lanes = max(1, int(segment.get("lane_count", 1)))
            road_w = max(18, min(64, int((lanes * 18) * min(2.5, max(0.6, self.zoom_level)))))
            if dist <= road_w / 2.0 + tolerance and dist < closest_dist:
                closest_dist = dist
                closest_item = segment

        return closest_item

    def add_intersection_at(self, scen_x: float, scen_y: float) -> str:
        """Create a new intersection at scenario coordinates, returning its unique identifier."""
        network = self.scenario_data.setdefault("network", {})
        intersections = network.setdefault("intersections", [])
        existing_ids = [i["id"] for i in intersections]
        new_id = generate_unique_id("I", existing_ids)

        new_intersection = {
            "id": new_id,
            "position": [round(scen_x, 1), round(scen_y, 1)],
            "control_type": "uncontrolled",
        }
        intersections.append(new_intersection)
        self._pending_edit_description = "Add Intersection"
        self.network_modified.emit()
        return new_id

    def create_road_segment(self, start_id: str, dest_id: str) -> tuple[bool, str]:
        """Create a directed road segment connecting start_id to dest_id, validating against self-loops and duplicates."""
        if start_id == dest_id:
            return False, "Self-connection prohibited: a road segment cannot connect an intersection to itself."

        network = self.scenario_data.setdefault("network", {})
        segments = network.setdefault("segments", [])

        # Check duplicate segment in the same direction
        for s in segments:
            if s.get("from") == start_id and s.get("to") == dest_id:
                return False, f"A road segment from '{start_id}' to '{dest_id}' already exists ({s.get('id')})."

        intersections = {i["id"]: i for i in network.get("intersections", [])}
        start_inter = intersections.get(start_id)
        dest_inter = intersections.get(dest_id)
        if not start_inter or not dest_inter:
            return False, "Referenced intersection does not exist."

        # Compute Euclidean distance in scenario coordinates
        pos_a = start_inter.get("position", [0.0, 0.0])
        pos_b = dest_inter.get("position", [0.0, 0.0])
        dx = float(pos_b[0]) - float(pos_a[0])
        dy = float(pos_b[1]) - float(pos_a[1])
        length_m = max(10.0, round((dx * dx + dy * dy) ** 0.5, 1))

        # Generate unique ID
        existing_ids = [s["id"] for s in segments]
        new_id = generate_unique_id("R", existing_ids)

        new_segment = {
            "id": new_id,
            "from": start_id,
            "to": dest_id,
            "length_m": length_m,
            "lane_count": 1,
            "speed_limit_mps": 13.9,
        }
        segments.append(new_segment)
        self.set_selection("segment", new_id)
        self._pending_edit_description = "Add Road Segment"
        self.network_modified.emit()
        return True, f"Created road segment '{new_id}' ({start_id} → {dest_id})."

    def delete_selected(self) -> tuple[bool, str]:
        """Delete currently selected intersection or segment, safely handling dependent objects."""
        if not self.selected_type or not self.selected_id:
            return False, "No object selected."

        network = self.scenario_data.get("network", {})
        if self.selected_type == "intersection":
            iid = self.selected_id
            segments = network.get("segments", [])
            connected = [s["id"] for s in segments if s.get("from") == iid or s.get("to") == iid]
            if connected:
                return False, f"Cannot delete intersection '{iid}': it is referenced by {len(connected)} road segment(s) ({', '.join(connected)}). Delete connected road segments first."

            network["intersections"] = [i for i in network.get("intersections", []) if i.get("id") != iid]
            # Clean up signal plan if any
            plans = get_scenario_signal_plans(self.scenario_data)
            updated_plans = [p for p in plans if p.get("intersection_id") != iid]
            set_scenario_signal_plans(self.scenario_data, updated_plans)
            self.set_selection(None, None)
            self._pending_edit_description = "Delete Intersection"
            self.network_modified.emit()
            return True, f"Deleted intersection '{iid}'."

        elif self.selected_type == "segment":
            sid = self.selected_id
            network["segments"] = [s for s in network.get("segments", []) if s.get("id") != sid]

            # Clean up turning movements that reference this segment
            moves = network.get("turning_movements", [])
            removed_moves = [m["id"] for m in moves if m.get("from_segment") == sid or m.get("to_segment") == sid]
            network["turning_movements"] = [m for m in moves if m["id"] not in removed_moves]

            # Clean up demand references
            demand = self.scenario_data.get("demand", {})
            if "arrival_rates_vehicles_per_hour" in demand:
                demand["arrival_rates_vehicles_per_hour"].pop(sid, None)
            if "turning_ratios" in demand:
                for mid in removed_moves:
                    demand["turning_ratios"].pop(mid, None)

            # Clean up signal plan phases referencing removed movements
            raw_plans = get_scenario_signal_plans(self.scenario_data)
            for plan_dict in raw_plans:
                for ph in plan_dict.get("phases", []):
                    ph["movement_ids"] = [mid for mid in ph.get("movement_ids", []) if mid not in removed_moves]
            set_scenario_signal_plans(self.scenario_data, raw_plans)

            self.set_selection(None, None)
            self._pending_edit_description = "Delete Road Segment"
            self.network_modified.emit()
            return True, f"Deleted road segment '{sid}'."

        return False, "Unknown selection type."

    def handle_canvas_click(self, screen_pt: QPointF):
        """Handle canvas clicks according to active editing tool."""
        if self.active_tool == "select":
            hit_inter = self.hit_test_intersection(screen_pt)
            if hit_inter:
                self.set_selection("intersection", hit_inter["id"])
                return
            hit_seg = self.hit_test_segment(screen_pt)
            if hit_seg:
                self.set_selection("segment", hit_seg["id"])
                return
            # Clicked empty space: clear selection
            self.set_selection(None, None)

        elif self.active_tool == "add_intersection":
            hit_inter = self.hit_test_intersection(screen_pt)
            if hit_inter:
                # Clicked existing intersection: select it rather than duplicating
                self.set_selection("intersection", hit_inter["id"])
                return
            scen_x, scen_y = self.screen_to_scenario(screen_pt)
            new_id = self.add_intersection_at(scen_x, scen_y)
            self.set_selection("intersection", new_id)
            self.tool_status_message.emit(f"Created intersection '{new_id}' at ({scen_x:.1f}, {scen_y:.1f}).")

        elif self.active_tool == "draw_road":
            hit_inter = self.hit_test_intersection(screen_pt)
            if not self.road_start_id:
                if hit_inter:
                    self.road_start_id = hit_inter["id"]
                    self.road_hover_pos = screen_pt
                    self.update()
                    self.tool_status_message.emit(f"Start: '{hit_inter['id']}'. Click destination intersection (Esc to cancel).")
                else:
                    self.tool_status_message.emit("Please click an intersection to start the road.")
            else:
                if hit_inter:
                    dest_id = hit_inter["id"]
                    success, msg = self.create_road_segment(self.road_start_id, dest_id)
                    self.road_start_id = None
                    self.road_hover_pos = None
                    self.update()
                    self.tool_status_message.emit(msg)
                    if not success:
                        QMessageBox.warning(self, "Invalid Road Segment", msg)
                else:
                    self.tool_status_message.emit("Please click destination intersection (or Esc to cancel).")

    def wheelEvent(self, event):
        """Zoom in/out around the mouse pointer so the scene point under the cursor stays fixed."""
        angle = event.angleDelta().y()
        if angle == 0:
            return

        zoom_factor = 1.15 if angle > 0 else (1.0 / 1.15)
        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self.zoom_level * zoom_factor))
        if new_zoom == self.zoom_level:
            return

        mouse_pos = event.position()
        center = QPointF(self.width() / 2.0, self.height() / 2.0)

        # Invariant: mouse_pos maps to the exact same scene point before and after zoom
        ratio = new_zoom / self.zoom_level
        self.pan_offset = (mouse_pos - center) - ratio * (mouse_pos - center - self.pan_offset)
        self.zoom_level = new_zoom
        self.update()

    def mousePressEvent(self, event):
        """Begin tracking clicks vs drag gestures."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = True
            self._pan_start = event.position()
            self._mouse_press_pos = event.position()
            self._press_pan_offset = QPointF(self.pan_offset)
            self._has_dragged = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.RightButton:
            if self.active_tool == "draw_road" and self.road_start_id:
                self.road_start_id = None
                self.road_hover_pos = None
                self.tool_status_message.emit("Road creation cancelled.")
                self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle panning displacement while dragging and update road preview."""
        if self._is_panning and self._mouse_press_pos is not None:
            delta = event.position() - self._mouse_press_pos
            if not self._has_dragged and (delta.x() ** 2 + delta.y() ** 2) > 16:
                self._has_dragged = True

            pan_delta = event.position() - self._pan_start
            self.pan_offset += pan_delta
            self._pan_start = event.position()
            self.update()

        if self.active_tool == "draw_road" and self.road_start_id:
            self.road_hover_pos = event.position()
            self.update()

        if not self._is_panning:
            if self.active_tool in ("select", "draw_road"):
                hit_node = self.hit_test_intersection(event.position())
                hit_edge = self.hit_test_segment(event.position()) if self.active_tool == "select" else None
                if hit_node or hit_edge:
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            elif self.active_tool == "add_intersection":
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Differentiate click from drag on mouse release."""
        if event.button() == Qt.MouseButton.LeftButton:
            was_drag = self._has_dragged
            self._is_panning = False
            self._has_dragged = False
            self._mouse_press_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)

            if not was_drag:
                # Revert any micro-displacement so click doesn't cause drift
                self.pan_offset = self._press_pan_offset
                self.handle_canvas_click(event.position())

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click resets zoom and pan to 100% centered view."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_view()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        """Handle Delete and Escape shortcuts."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            success, msg = self.delete_selected()
            self.tool_status_message.emit(msg)
            if not success and self.selected_type:
                QMessageBox.warning(self, "Cannot Delete", msg)
        elif event.key() == Qt.Key.Key_Escape:
            if self.active_tool == "draw_road" and self.road_start_id:
                self.road_start_id = None
                self.road_hover_pos = None
                self.tool_status_message.emit("Road drawing cancelled.")
                self.update()
            elif self.selected_type:
                self.set_selection(None, None)
                self.tool_status_message.emit("Selection cleared.")
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.BACKGROUND)

        network = self.scenario_data.get("network", {})
        intersections = network.get("intersections", [])
        segments = network.get("segments", [])
        turning_movements = network.get("turning_movements", [])
        if not intersections and not segments:
            painter.setPen(QColor("#344054"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Empty Network — Click 'Add intersection' to start editing.")
            painter.end()
            return

        width = max(1, self.width())
        height = max(1, self.height())

        # Calculate screen positions for all intersections using consistent transform
        screen_positions = {}
        for intersection in intersections:
            pos = intersection.get("position")
            if isinstance(pos, list) and len(pos) >= 2:
                screen_positions[intersection["id"]] = self.scenario_to_screen((float(pos[0]), float(pos[1])))

        sim_time = self.engine.time if self.engine is not None else 0.0

        # 1. Draw road segments
        for segment in segments:
            start = screen_positions.get(segment.get("from"))
            end = screen_positions.get(segment.get("to"))
            if start is None or end is None:
                continue
            lanes = max(1, int(segment.get("lane_count", 1)))
            road_width = max(18, min(64, int((lanes * 18) * min(2.5, max(0.6, self.zoom_level)))))

            # Selection highlight under the road segment
            if self.selected_type == "segment" and segment.get("id") == self.selected_id:
                painter.setPen(QPen(self.COLOR_SELECTION, road_width + 8,
                                    Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(start, end)

            # Road edge and surface
            painter.setPen(QPen(self.ROAD_EDGE, road_width + 3,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)
            painter.setPen(QPen(self.ROAD_COLOR, road_width,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)
            painter.setPen(QPen(QColor("#f8fafc"), 2, Qt.PenStyle.DashLine))
            painter.drawLine(start, end)

            # Road name label
            if self.zoom_level >= 0.4:
                midpoint = QPointF((start.x() + end.x()) / 2.0,
                                   (start.y() + end.y()) / 2.0)
                painter.setPen(QColor("#344054"))
                painter.setFont(safe_font("Segoe UI", 9, QFont.Weight.DemiBold))
                painter.drawText(midpoint + QPointF(6, -road_width / 2.0 - 8),
                                 f'{segment.get("id", "Road")}')

        # 2. Draw rubber-band road preview when in Draw Road tool
        if self.active_tool == "draw_road" and self.road_start_id:
            start_pt = screen_positions.get(self.road_start_id)
            if start_pt and self.road_hover_pos:
                painter.setPen(QPen(self.COLOR_SELECTION, 2.5, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(start_pt, self.road_hover_pos)
                painter.setPen(QPen(self.COLOR_SELECTION, 1))
                painter.setBrush(QColor(37, 99, 235, 120))
                painter.drawEllipse(self.road_hover_pos, 6, 6)

        # 3. Draw approach stop lines and signal indicators
        for segment in segments:
            to_node = segment.get("to")
            plan = self.signal_plans.get(to_node)
            if not plan:
                continue
            start = screen_positions.get(segment.get("from"))
            end = screen_positions.get(segment.get("to"))
            if start is None or end is None:
                continue

            dx = start.x() - end.x()
            dy = start.y() - end.y()
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < 20:
                continue
            ux = dx / dist
            uy = dy / dist
            px = -uy
            py = ux

            lanes = max(1, int(segment.get("lane_count", 1)))
            road_width = max(18, min(64, int((lanes * 18) * min(2.5, max(0.6, self.zoom_level)))))
            stop_dist = max(16.0, 24.0 * min(2.0, self.zoom_level))
            stop_pt = QPointF(end.x() + ux * stop_dist, end.y() + uy * stop_dist)

            moves = [
                m["id"] for m in turning_movements
                if m.get("intersection") == to_node and m.get("from_segment") == segment.get("id")
            ]

            approach_state = "RED"
            if moves:
                states = [plan.movement_state(mid, sim_time) for mid in moves]
                if "GREEN" in states:
                    approach_state = "GREEN"
                elif "YELLOW" in states:
                    approach_state = "YELLOW"

            half_w = road_width / 2.0
            p1 = QPointF(stop_pt.x() - px * half_w, stop_pt.y() - py * half_w)
            p2 = QPointF(stop_pt.x() + px * half_w, stop_pt.y() + py * half_w)
            painter.setPen(QPen(QColor("#ffffff"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap))
            painter.drawLine(p1, p2)

            ind_pt = QPointF(stop_pt.x() + px * (half_w + 9.0), stop_pt.y() + py * (half_w + 9.0))
            ind_color = self.COLOR_GREEN if approach_state == "GREEN" else (
                self.COLOR_YELLOW if approach_state == "YELLOW" else self.COLOR_RED
            )
            ind_radius = max(5.0, min(9.0, 6.0 * min(1.8, max(0.8, self.zoom_level))))
            painter.setPen(QPen(QColor("#ffffff"), 1.5))
            painter.setBrush(QColor("#1e293b"))
            painter.drawEllipse(ind_pt, ind_radius + 2, ind_radius + 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ind_color)
            painter.drawEllipse(ind_pt, ind_radius, ind_radius)

        # 4. Draw intersection nodes, selection halos, and controls
        for intersection in intersections:
            point = screen_positions.get(intersection["id"])
            if point is None:
                continue
            node_r = max(9.0, min(20.0, 12.0 * min(1.8, max(0.7, self.zoom_level))))

            # Selection highlight for intersection
            if self.selected_type == "intersection" and intersection.get("id") == self.selected_id:
                painter.setPen(QPen(self.COLOR_SELECTION, 3.5, Qt.PenStyle.SolidLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(point, node_r + 6, node_r + 6)

            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor("#64748b"))
            painter.drawEllipse(point, node_r, node_r)

            if self.zoom_level >= 0.4:
                painter.setPen(QColor("#1f2937"))
                painter.setFont(safe_font("Segoe UI", 9, QFont.Weight.Bold))
                painter.drawText(point + QPointF(node_r + 4, -node_r), intersection["id"])

            control = str(intersection.get("control_type", "uncontrolled")).lower()
            if control == "signalized":
                plan = self.signal_plans.get(intersection["id"])
                int_state = plan.intersection_state(sim_time) if plan else "RED"
                signal_color = self.COLOR_GREEN if int_state == "GREEN" else (
                    self.COLOR_YELLOW if int_state == "YELLOW" else self.COLOR_RED
                )
                sig_r = max(5.0, min(10.0, 6.0 * min(1.8, max(0.8, self.zoom_level))))
                badge_center = point + QPointF(0, node_r + sig_r + 4)
                painter.setPen(QPen(QColor("#ffffff"), 1.5))
                painter.setBrush(QColor("#1e293b"))
                painter.drawEllipse(badge_center, sig_r + 2, sig_r + 2)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(signal_color)
                painter.drawEllipse(badge_center, sig_r, sig_r)
            else:
                badge_center = point + QPointF(0, node_r + 8)
                painter.setPen(QPen(QColor("#ffffff"), 1))
                painter.setBrush(self.COLOR_UNSIGNALIZED)
                painter.drawEllipse(badge_center, 5, 5)

        # 5. Draw live simulation vehicles
        if self.engine is not None:
            segment_by_id = {s["id"]: s for s in segments}
            for index, car in enumerate(self.engine.cars):
                if not car.route or car.leg >= len(car.route):
                    continue
                segment = segment_by_id.get(car.route[car.leg])
                if segment is None:
                    continue
                start = screen_positions.get(segment.get("from"))
                end = screen_positions.get(segment.get("to"))
                if start is None or end is None:
                    continue

                length = float(segment.get("length_m", 1.0))
                fraction = max(0.0, min(1.0, car.x / max(length, 0.001)))
                x = start.x() + (end.x() - start.x()) * fraction
                y = start.y() + (end.y() - start.y()) * fraction

                vw = max(10, min(32, int(16 * min(2.0, max(0.7, self.zoom_level)))))
                vh = max(8, min(24, int(12 * min(2.0, max(0.7, self.zoom_level)))))

                painter.setPen(QPen(QColor("#ffffff"), 1))
                painter.setBrush(self.VEHICLE_COLORS[index % len(self.VEHICLE_COLORS)])
                painter.drawRoundedRect(int(x - vw / 2.0), int(y - vh / 2.0), vw, vh, 3, 3)

        # Top HUD labels
        painter.setPen(QColor("#344054"))
        painter.setFont(safe_font("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.drawText(14, 24, "SCENARIO NETWORK  /  LIVE VEHICLES & SIGNALS")

        zoom_text = f"Zoom: {int(self.zoom_level * 100)}%"
        tool_text = f"Tool: {self.active_tool.replace('_', ' ').title()}"
        painter.setFont(safe_font("Segoe UI", 9, QFont.Weight.Normal))
        painter.setPen(QColor("#64748b"))
        hint_text = f"{tool_text}  •  {zoom_text}  •  Scroll: Zoom  •  Drag: Pan"
        painter.drawText(width - 320, 24, hint_text)

        # Bottom-left Signal Status Legend
        legend_w, legend_h = 285, 26
        lx = 14
        ly = height - legend_h - 12
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.drawRoundedRect(lx, ly, legend_w, legend_h, 5, 5)

        painter.setFont(safe_font("Segoe UI", 8, QFont.Weight.Medium))
        items = [
            (self.COLOR_GREEN, "Green (Go)", 12),
            (self.COLOR_YELLOW, "Yellow (Caution)", 92),
            (self.COLOR_RED, "Red (Stop)", 192),
        ]
        for color, text, offset_x in items:
            cx = lx + offset_x
            cy = ly + 13
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.setBrush(color)
            painter.drawEllipse(QPointF(cx, cy), 4.5, 4.5)
            painter.setPen(QColor("#334155"))
            painter.drawText(int(cx + 8), int(cy + 4), text)

        painter.end()


class Workbench(QMainWindow):
    def __init__(self, scenario_path: str | Path | None = None):
        super().__init__()
        self.setWindowTitle("TMS-Sim")
        self.resize(1366, 768)

        default_path = (
            Path(__file__).resolve().parents[3]
            / "tests"
            / "data"
            / "scenario"
            / "small_valid_scenario.json"
        )
        self.scenario_path = Path(scenario_path) if scenario_path else default_path

        self.is_dirty: bool = False
        self.dirty: bool = False
        self.save_prompt_handler = None
        self._is_restoring_history: bool = False
        self._pending_edit_description: str = ""

        self.scenario_data = {}
        self.engine = None
        self.validation_issues: list[ValidationIssue] = []

        try:
            self.scenario_data = load_scenario_document(self.scenario_path)
            self.engine = load_scenario(self.scenario_path)
        except Exception as exc:
            logger.exception("Could not load initial scenario from %s: %s", self.scenario_path, exc)
            QMessageBox.critical(
                self,
                "Unable to load scenario",
                f"Could not load the scenario:\n{self.scenario_path}\n\n{exc}",
            )
            raise

        self.canvas = RoadCanvas()
        self.canvas.set_scenario(self.engine, self.scenario_data)
        self.canvas.selection_changed.connect(self.on_canvas_selection_changed)
        self.canvas.network_modified.connect(self.on_network_modified)
        self.canvas.tool_status_message.connect(self.set_status_message)

        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.advance_simulation)

        self.status_label = QLabel("Ready")
        self.clock_label = QLabel("Simulation time: 0.0 s")
        self.speed_box = QComboBox()
        self.speed_box.setFont(safe_font("Segoe UI", 10))
        self.speed_box.addItems(["0.5x", "1x", "2x", "4x"])
        self.speed_box.setCurrentText("1x")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0.0% (0.0 / 0.0 s)")
        self.progress_bar.setToolTip("Simulation progress (synchronized with engine clock)")
        self.playback_progress_bar = self.progress_bar

        self.setFont(safe_font("Segoe UI", 10))
        self.history_tracker = SimulationHistoryTracker(min_sample_interval=1.0)
        if self.engine is not None:
            self.history_tracker.record_state(self.engine)
        self.build_ui()
        self.update_metrics()
        self.validate_current_network()
        self.refresh_demand_ui()
        self.refresh_signal_plans_ui()
        self.set_dirty(False)
        self.history_manager = ScenarioHistoryManager(self.scenario_data, max_history=50)
        self.update_undo_redo_actions()

    def build_ui(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #f6f8fb;
                color: #1f2937;
                font-family: 'Segoe UI';
                font-size: 10pt;
            }
            QFrame#panel {
                background: white;
                border: 1px solid #e0e5ec;
                border-radius: 8px;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #d0d5dd;
                border-radius: 5px;
                padding: 8px 12px;
            }
            QPushButton:hover { background: #edf4ff; }
            QPushButton:checked {
                background: #2563eb;
                color: white;
                border-color: #1d4ed8;
                font-weight: 600;
            }
            QPushButton#primary {
                background: #2563eb;
                color: white;
                border: none;
                font-weight: 600;
            }
            QPushButton#primary:hover { background: #1d4ed8; }
            QPushButton:disabled {
                background: #f8fafc;
                color: #94a3b8;
                border-color: #e2e8f0;
            }
            QProgressBar {
                border: 1px solid #d0d5dd;
                border-radius: 4px;
                text-align: center;
                background-color: #f1f5f9;
                color: #1e293b;
                font-size: 8.5pt;
                font-weight: 600;
                min-height: 22px;
                max-height: 24px;
                min-width: 150px;
            }
            QProgressBar::chunk {
                background-color: #2563eb;
                border-radius: 3px;
            }
            QPushButton#danger {
                background: #fee2e2;
                color: #dc2626;
                border: 1px solid #fca5a5;
            }
            QPushButton#danger:hover { background: #fecaca; }
            QLabel#heading {
                font-size: 14pt;
                font-weight: 700;
            }
            QLabel#muted { color: #667085; }
            QListWidget {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 4px;
                font-size: 9pt;
            }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 4px;
                gridline-color: #f1f5f9;
                font-size: 9pt;
            }
            QHeaderView::section {
                background: #f8fafc;
                color: #475467;
                font-weight: 600;
                padding: 4px;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                font-size: 9pt;
            }
        """)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(12)

        # Menu bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        self.open_action = file_menu.addAction("&Open Scenario...")
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.setStatusTip("Open and load a scenario JSON file")
        self.open_action.triggered.connect(self.open_scenario_dialog)

        self.save_action = file_menu.addAction("&Save Scenario")
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.setStatusTip("Save changes to the current scenario file")
        self.save_action.triggered.connect(self.save_scenario)

        self.save_as_action = file_menu.addAction("Save Scenario &As...")
        self.save_as_action.setShortcut("Ctrl+Shift+S")
        self.save_as_action.setStatusTip("Save current scenario to a new JSON file")
        self.save_as_action.triggered.connect(self.save_scenario_as)

        file_menu.addSeparator()
        exit_action = file_menu.addAction("E&xit")
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        self.undo_action = edit_menu.addAction("&Undo")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setStatusTip("Undo the last configuration change (Ctrl+Z)")
        self.undo_action.triggered.connect(self.undo)

        self.redo_action = edit_menu.addAction("&Redo")
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        self.redo_action.setStatusTip("Redo the last undone configuration change (Ctrl+Y or Ctrl+Shift+Z)")
        self.redo_action.triggered.connect(self.redo)

        edit_menu.addSeparator()
        del_action = edit_menu.addAction("&Delete Selected")
        del_action.setShortcut(QKeySequence.StandardKey.Delete)
        del_action.setStatusTip("Delete selected intersection or road segment")
        del_action.triggered.connect(self.delete_selected_object)
        deselect_action = edit_menu.addAction("Deselect &All")
        deselect_action.setShortcut(Qt.Key.Key_Escape)
        deselect_action.setStatusTip("Clear selection and cancel current tool action")
        deselect_action.triggered.connect(self.clear_selection)

        # View menu
        view_menu = menubar.addMenu("&View")
        reset_view_action = view_menu.addAction("&Reset Canvas View")
        reset_view_action.setShortcut("Ctrl+R")
        reset_view_action.setStatusTip("Reset canvas zoom and pan to 100%")
        reset_view_action.triggered.connect(self.canvas.reset_view)

        # Header toolbar
        header = QHBoxLayout()
        title = QLabel("Traffic Management System")
        title.setObjectName("heading")
        subtitle = QLabel("TMS-Sim  /  Desktop Workbench")
        subtitle.setObjectName("muted")

        self.btn_undo = QPushButton("↶ Undo")
        self.btn_undo.setToolTip("Undo last change (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.undo)

        self.btn_redo = QPushButton("↷ Redo")
        self.btn_redo.setToolTip("Redo last undone change (Ctrl+Y)")
        self.btn_redo.clicked.connect(self.redo)

        self.reset_view_button = QPushButton("⟲ Reset View")
        self.reset_view_button.setToolTip("Reset canvas zoom and pan (Ctrl+R or double-click canvas)")
        self.reset_view_button.clicked.connect(self.canvas.reset_view)

        self.open_button = QPushButton("Open Scenario…")
        self.open_button.setToolTip("Open a JSON scenario file (Ctrl+O)")
        self.open_button.clicked.connect(self.open_scenario_dialog)

        self.save_button = QPushButton("💾 Save")
        self.save_button.setToolTip("Save scenario to current file (Ctrl+S)")
        self.save_button.clicked.connect(self.save_scenario)

        self.save_as_button = QPushButton("Save As…")
        self.save_as_button.setToolTip("Save scenario as a new file (Ctrl+Shift+S)")
        self.save_as_button.clicked.connect(self.save_scenario_as)

        header.addWidget(title)
        header.addSpacing(8)
        header.addWidget(subtitle)
        header.addStretch()
        header.addWidget(self.btn_undo)
        header.addWidget(self.btn_redo)
        header.addWidget(self.reset_view_button)
        header.addWidget(self.open_button)
        header.addWidget(self.save_button)
        header.addWidget(self.save_as_button)
        outer.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # TOOLBOX
        toolbox = self.panel("TOOLBOX")
        tools = toolbox.layout()

        self.btn_tool_select = QPushButton("🔍  Select tool")
        self.btn_tool_select.setCheckable(True)
        self.btn_tool_select.setChecked(True)
        self.btn_tool_select.setToolTip("Click to select intersections and road segments")

        self.btn_tool_add_intersection = QPushButton("➕  Add intersection")
        self.btn_tool_add_intersection.setCheckable(True)
        self.btn_tool_add_intersection.setToolTip("Click empty canvas space to create an intersection")

        self.btn_tool_draw_road = QPushButton("🛣  Draw road")
        self.btn_tool_draw_road.setCheckable(True)
        self.btn_tool_draw_road.setToolTip("Click start intersection, then destination intersection")

        self.btn_tool_delete = QPushButton("🗑  Delete selected")
        self.btn_tool_delete.setObjectName("danger")
        self.btn_tool_delete.setToolTip("Delete selected object (Delete key)")

        self.tool_group = QButtonGroup(self)
        self.tool_group.addButton(self.btn_tool_select)
        self.tool_group.addButton(self.btn_tool_add_intersection)
        self.tool_group.addButton(self.btn_tool_draw_road)
        self.tool_group.setExclusive(True)

        self.btn_tool_select.clicked.connect(lambda: self.set_tool_mode("select"))
        self.btn_tool_add_intersection.clicked.connect(lambda: self.set_tool_mode("add_intersection"))
        self.btn_tool_draw_road.clicked.connect(lambda: self.set_tool_mode("draw_road"))
        self.btn_tool_delete.clicked.connect(self.delete_selected_object)

        tools.addWidget(self.btn_tool_select)
        tools.addWidget(self.btn_tool_add_intersection)
        tools.addWidget(self.btn_tool_draw_road)
        tools.addSpacing(10)
        tools.addWidget(self.btn_tool_delete)
        tools.addStretch()
        toolbox.setMinimumWidth(180)
        splitter.addWidget(toolbox)

        # 2D ROAD NETWORK canvas panel
        network_panel = self.panel("2D ROAD NETWORK")
        network_panel.layout().addWidget(self.canvas)
        splitter.addWidget(network_panel)

        # Right sidebar: PROPERTIES, VALIDATION, LIVE METRICS
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # PROPERTIES INSPECTOR (Stacked Widget)
        props_frame = self.panel("PROPERTIES")
        pl = props_frame.layout()

        self.inspector_stack = QStackedWidget()

        # Page 0: Scenario properties
        page_scen = QWidget()
        scen_layout = QVBoxLayout(page_scen)
        scen_layout.setContentsMargins(0, 0, 0, 0)
        scen_layout.setSpacing(6)

        lbl_scen_heading = QLabel("Loaded scenario")
        lbl_scen_heading.setObjectName("muted")
        self.scenario_name_label = QLabel(self.scenario_data.get("name", "Scenario"))
        self.scenario_name_label.setStyleSheet("font-weight: 700; color: #1f2937;")
        self.scenario_name_label.setWordWrap(True)

        lbl_file = QLabel("Scenario file")
        lbl_file.setObjectName("muted")
        self.scenario_file_label = QLabel(self.scenario_path.name if self.scenario_path else "None")
        self.scenario_file_label.setStyleSheet("color: #2563eb; font-weight: 600;")
        if self.scenario_path:
            self.scenario_file_label.setToolTip(str(self.scenario_path))
        self.scenario_file_label.setWordWrap(True)

        self.intersections_label = QLabel()
        self.segments_label = QLabel()
        self.control_label = QLabel()

        scen_hint = QLabel("Select an intersection or road segment to inspect and edit.")
        scen_hint.setObjectName("muted")
        scen_hint.setWordWrap(True)

        for w in (lbl_scen_heading, self.scenario_name_label, lbl_file, self.scenario_file_label,
                  self.intersections_label, self.segments_label, self.control_label, scen_hint):
            scen_layout.addWidget(w)
        scen_layout.addStretch()
        self.inspector_stack.addWidget(page_scen)

        # Page 1: Intersection Inspector
        page_inter = QWidget()
        inter_layout = QVBoxLayout(page_inter)
        inter_layout.setContentsMargins(0, 0, 0, 0)
        inter_layout.setSpacing(6)

        self.lbl_inter_header = QLabel("INTERSECTION: ")
        self.lbl_inter_header.setStyleSheet("font-weight: 700; color: #2563eb;")
        inter_form = QFormLayout()
        inter_form.setSpacing(6)

        self.combo_inter_control = QComboBox()
        self.combo_inter_control.setFont(safe_font("Segoe UI", 10))
        self.combo_inter_control.addItems(["uncontrolled", "signalized", "stop_controlled", "yield_controlled"])
        self.edit_inter_x = QLineEdit()
        self.edit_inter_y = QLineEdit()

        inter_form.addRow("Control type:", self.combo_inter_control)
        inter_form.addRow("Position X (m):", self.edit_inter_x)
        inter_form.addRow("Position Y (m):", self.edit_inter_y)

        btn_row_inter = QHBoxLayout()
        btn_apply_inter = QPushButton("Apply")
        btn_apply_inter.setObjectName("primary")
        btn_apply_inter.clicked.connect(self.apply_intersection_properties)
        btn_cancel_inter = QPushButton("Deselect")
        btn_cancel_inter.clicked.connect(self.clear_selection)
        btn_row_inter.addWidget(btn_apply_inter)
        btn_row_inter.addWidget(btn_cancel_inter)

        inter_layout.addWidget(self.lbl_inter_header)
        inter_layout.addLayout(inter_form)
        inter_layout.addLayout(btn_row_inter)
        inter_layout.addStretch()
        self.inspector_stack.addWidget(page_inter)

        # Page 2: Road Segment Inspector
        page_seg = QWidget()
        seg_layout = QVBoxLayout(page_seg)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(6)

        self.lbl_seg_header = QLabel("ROAD SEGMENT: ")
        self.lbl_seg_header.setStyleSheet("font-weight: 700; color: #2563eb;")
        self.lbl_seg_endpoints = QLabel("Endpoints: ")
        self.lbl_seg_endpoints.setObjectName("muted")

        seg_form = QFormLayout()
        seg_form.setSpacing(6)

        self.edit_seg_length = QLineEdit()
        self.spin_seg_lanes = QSpinBox()
        self.spin_seg_lanes.setRange(1, 10)
        self.edit_seg_speed = QLineEdit()

        seg_form.addRow("Length (m):", self.edit_seg_length)
        seg_form.addRow("Lane count:", self.spin_seg_lanes)
        seg_form.addRow("Speed limit (m/s):", self.edit_seg_speed)

        btn_row_seg = QHBoxLayout()
        btn_apply_seg = QPushButton("Apply")
        btn_apply_seg.setObjectName("primary")
        btn_apply_seg.clicked.connect(self.apply_segment_properties)
        btn_cancel_seg = QPushButton("Deselect")
        btn_cancel_seg.clicked.connect(self.clear_selection)
        btn_row_seg.addWidget(btn_apply_seg)
        btn_row_seg.addWidget(btn_cancel_seg)

        seg_layout.addWidget(self.lbl_seg_header)
        seg_layout.addWidget(self.lbl_seg_endpoints)
        seg_layout.addLayout(seg_form)
        seg_layout.addLayout(btn_row_seg)
        seg_layout.addStretch()
        self.inspector_stack.addWidget(page_seg)

        pl.addWidget(self.inspector_stack)
        right_layout.addWidget(props_frame)

        # TRAFFIC DEMAND panel
        demand_frame = self.panel("TRAFFIC DEMAND")
        dl = demand_frame.layout()

        self.lbl_demand_summary = QLabel("Configured Arrival Rates:")
        self.lbl_demand_summary.setStyleSheet("font-weight: 600; color: #374151;")
        dl.addWidget(self.lbl_demand_summary)

        self.demand_table = QTableWidget()
        self.demand_table.setColumnCount(2)
        self.demand_table.setHorizontalHeaderLabels(["Road Segment", "Rate (veh/h)"])
        self.demand_table.horizontalHeader().setStretchLastSection(True)
        self.demand_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.demand_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.demand_table.setMaximumHeight(115)
        self.demand_table.itemSelectionChanged.connect(self.on_demand_table_selection_changed)
        dl.addWidget(self.demand_table)

        self.lbl_demand_empty = QLabel("No traffic demand configured.\nSelect a road segment below to set arrival rates.")
        self.lbl_demand_empty.setStyleSheet("color: #6b7280; font-style: italic; padding: 6px;")
        self.lbl_demand_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(self.lbl_demand_empty)

        demand_form = QFormLayout()
        demand_form.setSpacing(6)

        self.combo_demand_segment = QComboBox()
        self.combo_demand_segment.setFont(safe_font("Segoe UI", 10))
        self.combo_demand_segment.currentTextChanged.connect(self.on_demand_combo_changed)

        self.edit_demand_rate = QLineEdit()
        self.edit_demand_rate.setPlaceholderText("e.g. 180.0")

        demand_form.addRow("Entry Road:", self.combo_demand_segment)
        demand_form.addRow("Rate (veh/h):", self.edit_demand_rate)
        dl.addLayout(demand_form)

        btn_row_demand = QHBoxLayout()
        self.btn_set_demand = QPushButton("Set Arrival Rate")
        self.btn_set_demand.setObjectName("primary")
        self.btn_set_demand.clicked.connect(self.apply_demand_entry)

        self.btn_remove_demand = QPushButton("Remove Entry")
        self.btn_remove_demand.setObjectName("danger")
        self.btn_remove_demand.clicked.connect(self.remove_demand_entry)

        btn_row_demand.addWidget(self.btn_set_demand)
        btn_row_demand.addWidget(self.btn_remove_demand)
        dl.addLayout(btn_row_demand)

        right_layout.addWidget(demand_frame)

        # SIGNAL PLANS panel
        signal_frame = self.panel("SIGNAL PLANS")
        sl = signal_frame.layout()

        sig_header_layout = QHBoxLayout()
        self.lbl_signal_inter = QLabel("Intersection:")
        self.lbl_signal_inter.setStyleSheet("font-weight: 600; color: #374151;")
        self.combo_signal_plan = QComboBox()
        self.combo_signal_plan.setFont(safe_font("Segoe UI", 10))
        self.combo_signal_plan.currentIndexChanged.connect(self.on_signal_plan_combo_changed)
        sig_header_layout.addWidget(self.lbl_signal_inter)
        sig_header_layout.addWidget(self.combo_signal_plan, 1)
        sl.addLayout(sig_header_layout)

        self.lbl_plan_cycle = QLabel("Cycle duration: 0.0 s")
        self.lbl_plan_cycle.setStyleSheet("color: #2563eb; font-weight: 700; margin-top: 2px; margin-bottom: 4px;")
        sl.addWidget(self.lbl_plan_cycle)

        self.phase_table = QTableWidget()
        self.phase_table.setColumnCount(5)
        self.phase_table.setHorizontalHeaderLabels(["#", "Green (s)", "Yellow (s)", "All-Red (s)", "Movements"])
        self.phase_table.horizontalHeader().setStretchLastSection(True)
        self.phase_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.phase_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.phase_table.setMaximumHeight(115)
        self.phase_table.itemSelectionChanged.connect(self.on_phase_table_selection_changed)
        sl.addWidget(self.phase_table)

        self.lbl_plan_empty = QLabel("No signal plans configured.")
        self.lbl_plan_empty.setStyleSheet("color: #6b7280; font-style: italic; padding: 6px;")
        self.lbl_plan_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(self.lbl_plan_empty)

        self.btn_create_plan = QPushButton("Create Signal Plan")
        self.btn_create_plan.setObjectName("primary")
        self.btn_create_plan.clicked.connect(self.create_signal_plan_for_selected)
        sl.addWidget(self.btn_create_plan)

        # Phase Form details
        self.phase_form_widget = QWidget()
        pf_layout = QVBoxLayout(self.phase_form_widget)
        pf_layout.setContentsMargins(0, 0, 0, 0)
        pf_layout.setSpacing(4)

        phase_grid = QFormLayout()
        phase_grid.setSpacing(4)

        self.spin_phase_order = QSpinBox()
        self.spin_phase_order.setRange(1, 99)
        self.spin_phase_order.setValue(1)

        self.edit_phase_green = QLineEdit()
        self.edit_phase_green.setPlaceholderText("e.g. 20.0")

        self.edit_phase_yellow = QLineEdit()
        self.edit_phase_yellow.setPlaceholderText("e.g. 3.0")

        self.edit_phase_all_red = QLineEdit()
        self.edit_phase_all_red.setPlaceholderText("e.g. 1.0")

        phase_grid.addRow("Phase Order:", self.spin_phase_order)
        phase_grid.addRow("Green (s):", self.edit_phase_green)
        phase_grid.addRow("Yellow (s):", self.edit_phase_yellow)
        phase_grid.addRow("All-Red (s):", self.edit_phase_all_red)
        pf_layout.addLayout(phase_grid)

        lbl_moves = QLabel("Assigned Movements:")
        lbl_moves.setStyleSheet("font-weight: 600; color: #374151; margin-top: 4px;")
        pf_layout.addWidget(lbl_moves)

        self.list_phase_movements = QListWidget()
        self.list_phase_movements.setMaximumHeight(85)
        pf_layout.addWidget(self.list_phase_movements)

        # Phase action buttons: Apply Edits / Add Phase
        btn_phase_actions = QHBoxLayout()
        self.btn_apply_phase = QPushButton("Apply Phase")
        self.btn_apply_phase.setObjectName("primary")
        self.btn_apply_phase.clicked.connect(self.apply_phase_edits)
        self.btn_add_phase = QPushButton("Add Phase")
        self.btn_add_phase.clicked.connect(self.add_new_phase)
        btn_phase_actions.addWidget(self.btn_apply_phase)
        btn_phase_actions.addWidget(self.btn_add_phase)
        pf_layout.addLayout(btn_phase_actions)

        # Reordering & Deletion: Up, Down, Remove
        btn_reorder_layout = QHBoxLayout()
        self.btn_phase_up = QPushButton("▲ Up")
        self.btn_phase_up.clicked.connect(lambda: self.reorder_phase(-1))
        self.btn_phase_down = QPushButton("▼ Down")
        self.btn_phase_down.clicked.connect(lambda: self.reorder_phase(1))
        self.btn_remove_phase = QPushButton("Remove")
        self.btn_remove_phase.setObjectName("danger")
        self.btn_remove_phase.clicked.connect(self.remove_selected_phase)
        btn_reorder_layout.addWidget(self.btn_phase_up)
        btn_reorder_layout.addWidget(self.btn_phase_down)
        btn_reorder_layout.addWidget(self.btn_remove_phase)
        pf_layout.addLayout(btn_reorder_layout)

        sl.addWidget(self.phase_form_widget)
        right_layout.addWidget(signal_frame)

        # NETWORK VALIDATION panel
        val_frame = self.panel("NETWORK VALIDATION")
        vl = val_frame.layout()
        self.validation_status_label = QLabel("✔ Network Valid")
        self.validation_status_label.setStyleSheet("color: #16a34a; font-weight: 700;")
        self.validation_list = QListWidget()
        self.validation_list.setMaximumHeight(105)
        self.validation_list.itemClicked.connect(self.on_validation_item_clicked)
        vl.addWidget(self.validation_status_label)
        vl.addWidget(self.validation_list)
        right_layout.addWidget(val_frame)

        # SIMULATION RESULTS dashboard panel
        results_panel = self.panel("SIMULATION RESULTS")
        rl = results_panel.layout()
        rl.setSpacing(8)

        # Status & Time banner
        banner_frame = QFrame()
        banner_frame.setStyleSheet(
            "background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;"
        )
        banner_layout = QHBoxLayout(banner_frame)
        banner_layout.setContentsMargins(8, 6, 8, 6)
        banner_layout.setSpacing(6)

        lbl_status_prefix = QLabel("Status:")
        lbl_status_prefix.setStyleSheet("color: #64748b; font-size: 8.5pt; font-weight: 600;")
        self.metric_status_label = QLabel("Ready")
        self.metric_status_label.setStyleSheet(
            "background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; font-weight: 700; border-radius: 4px; padding: 2px 8px; font-size: 8.5pt;"
        )
        banner_layout.addWidget(lbl_status_prefix)
        banner_layout.addWidget(self.metric_status_label)
        banner_layout.addStretch()

        time_box = QHBoxLayout()
        time_box.setSpacing(4)
        self.metric_time = QLabel("0.0 s")
        self.metric_time.setStyleSheet("font-size: 11pt; font-weight: 700; color: #0f172a;")
        self.metric_duration_label = QLabel("/ 0.0 s")
        self.metric_duration_label.setStyleSheet("font-size: 8.5pt; color: #94a3b8;")
        time_box.addWidget(self.metric_time)
        time_box.addWidget(self.metric_duration_label)
        banner_layout.addLayout(time_box)
        rl.addWidget(banner_frame)

        # Compact metric cards grid (2 columns)
        grid = QGridLayout()
        grid.setSpacing(6)

        # 1. Vehicles in Network (Active)
        self.vehicle_count_label = QLabel("0")
        self.in_network_label = self.vehicle_count_label
        grid.addWidget(self._create_metric_card("IN NETWORK", self.vehicle_count_label, "active cars"), 0, 0)

        # 2. Vehicles Completed
        self.completed_label = QLabel("0")
        grid.addWidget(self._create_metric_card("COMPLETED", self.completed_label, "trips finished"), 0, 1)

        # 3. Vehicles Entered
        self.entered_label = QLabel("0")
        grid.addWidget(self._create_metric_card("ENTERED", self.entered_label, "entered network"), 1, 0)

        # 4. Vehicles Generated
        self.generated_label = QLabel("0")
        grid.addWidget(self._create_metric_card("GENERATED", self.generated_label, "scheduled demand"), 1, 1)

        # 5. Mean Travel Time
        self.mean_travel_time_label = QLabel("N/A")
        grid.addWidget(self._create_metric_card("MEAN TRAVEL TIME", self.mean_travel_time_label, "completed trips"), 2, 0)

        # 6. Throughput (Not available)
        self.throughput_label = QLabel("Not available")
        self.throughput_label.setStyleSheet("color: #94a3b8; font-size: 8.5pt; font-weight: 600;")
        grid.addWidget(self._create_metric_card("THROUGHPUT", self.throughput_label, "not modeled"), 2, 1)

        rl.addLayout(grid)

        # Additional unmodeled metrics note
        aux_frame = QFrame()
        aux_frame.setStyleSheet(
            "background: #fdfdfe; border: 1px dashed #cbd5e1; border-radius: 4px;"
        )
        aux_layout = QVBoxLayout(aux_frame)
        aux_layout.setContentsMargins(6, 4, 6, 4)
        aux_layout.setSpacing(2)

        self.queue_metric_label = QLabel("Queue length: Not available")
        self.queue_metric_label.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        self.queue_metric_label.setToolTip("Queue length tracking is not modeled in the current simulation engine.")
        self.delay_metric_label = QLabel("Average delay: Not available")
        self.delay_metric_label.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        self.delay_metric_label.setToolTip("Average delay calculation is not modeled in the current simulation engine.")
        aux_layout.addWidget(self.queue_metric_label)
        aux_layout.addWidget(self.delay_metric_label)
        rl.addWidget(aux_frame)

        # Backwards compatibility attributes
        self.remaining_label = QLabel("0")

        right_layout.addWidget(results_panel)

        # LIVE PERFORMANCE panel (Step 5B)
        initial_duration = self.engine.duration if self.engine else 600.0
        self.performance_panel = LivePerformancePanel(self.history_tracker, initial_duration, self)
        self.timeline_widget = self.performance_panel.timeline_widget
        self.counts_chart = self.performance_panel.counts_chart
        self.travel_time_chart = self.performance_panel.travel_time_chart
        right_layout.addWidget(self.performance_panel)
        right_layout.addStretch()

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setWidget(right)
        right_scroll.setMinimumWidth(290)
        splitter.addWidget(right_scroll)
        splitter.setSizes([180, 760, 300])
        outer.addWidget(splitter, 1)

        # Simulation controls
        controls = self.panel("SIMULATION CONTROLS")
        self.controls_panel = controls
        self.playback_toolbar = controls
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(8, 4, 8, 4)
        control_layout.setSpacing(8)
        controls.layout().addLayout(control_layout)

        self.btn_play = QPushButton("▶  Play")
        self.btn_play.setObjectName("primary")
        self.btn_play.setToolTip("Start or resume simulation (Space)")
        self.btn_start = self.btn_play  # Backwards compatibility alias

        self.btn_pause = QPushButton("⏸  Pause")
        self.btn_pause.setToolTip("Pause automatic simulation advancement (Space)")

        self.btn_step = QPushButton("⏭  Step")
        self.btn_step.setToolTip("Advance simulation by one time-step (S)")

        self.btn_reset = QPushButton("↺  Reset")
        self.btn_reset.setToolTip("Reset simulation to initial state (R)")

        self.btn_play.clicked.connect(self.start_simulation)
        self.btn_pause.clicked.connect(self.pause_simulation)
        self.btn_step.clicked.connect(self.step_simulation)
        self.btn_reset.clicked.connect(self.reset_simulation)
        self.speed_box.currentTextChanged.connect(self.change_speed)

        for btn in (self.btn_play, self.btn_pause, self.btn_step, self.btn_reset):
            control_layout.addWidget(btn)

        control_layout.addSpacing(10)
        lbl_speed = QLabel("Speed:")
        lbl_speed.setStyleSheet("color: #475467; font-weight: 600;")
        control_layout.addWidget(lbl_speed)
        control_layout.addWidget(self.speed_box)

        control_layout.addSpacing(10)
        lbl_prog = QLabel("Progress:")
        lbl_prog.setStyleSheet("color: #475467; font-weight: 600;")
        control_layout.addWidget(lbl_prog)
        control_layout.addWidget(self.progress_bar, 1)

        control_layout.addSpacing(10)
        self.clock_label.setStyleSheet("font-weight: 600; color: #0f172a;")
        control_layout.addWidget(self.clock_label)
        outer.addWidget(controls)

        # Keyboard shortcuts
        self.shortcut_space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self.shortcut_space.activated.connect(self._shortcut_toggle_play_pause)

        self.shortcut_step = QShortcut(QKeySequence(Qt.Key.Key_S), self)
        self.shortcut_step.activated.connect(self._shortcut_step)

        self.shortcut_reset = QShortcut(QKeySequence(Qt.Key.Key_R), self)
        self.shortcut_reset.activated.connect(self._shortcut_reset)

        outer.addWidget(self.status_label)
        self.setCentralWidget(root)

    @staticmethod
    def panel(title):
        frame = QFrame()
        frame.setObjectName("panel")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        label = QLabel(title)
        label.setStyleSheet(
            "font-weight: 700; color: #475467; letter-spacing: 1px;"
        )
        layout.addWidget(label)
        return frame

    @staticmethod
    def _create_metric_card(title: str, value_label: QLabel, sub_text: str | None = None) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; }"
            "QFrame:hover { border-color: #cbd5e1; background: #fafafa; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "color: #64748b; font-size: 7.5pt; font-weight: 700; letter-spacing: 0.5px;"
        )
        if not value_label.styleSheet():
            value_label.setStyleSheet("color: #0f172a; font-size: 13pt; font-weight: 700;")
        card_layout.addWidget(title_lbl)
        card_layout.addWidget(value_label)
        if sub_text:
            sub_lbl = QLabel(sub_text)
            sub_lbl.setStyleSheet("color: #94a3b8; font-size: 7.5pt;")
            card_layout.addWidget(sub_lbl)
        return card

    def _update_status_badge(self, status: str):
        styles = {
            "Ready": "background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; font-weight: 700; border-radius: 4px; padding: 2px 8px; font-size: 8.5pt;",
            "Running": "background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; font-weight: 700; border-radius: 4px; padding: 2px 8px; font-size: 8.5pt;",
            "Paused": "background: #fffbeb; color: #b45309; border: 1px solid #fde68a; font-weight: 700; border-radius: 4px; padding: 2px 8px; font-size: 8.5pt;",
            "Completed": "background: #faf5ff; color: #6d28d9; border: 1px solid #e9d5ff; font-weight: 700; border-radius: 4px; padding: 2px 8px; font-size: 8.5pt;",
        }
        self.metric_status_label.setText(status)
        self.metric_status_label.setStyleSheet(styles.get(status, styles["Ready"]))

    def set_tool_mode(self, mode: str):
        """Update active tool mode and set contextual guidance."""
        self.canvas.set_active_tool(mode)
        if mode == "select":
            self.btn_tool_select.setChecked(True)
            self.status_label.setText("Select tool: Click intersections or road segments to inspect and edit.")
        elif mode == "add_intersection":
            self.btn_tool_add_intersection.setChecked(True)
            self.status_label.setText("Add intersection tool: Click empty canvas space to place a new intersection.")
        elif mode == "draw_road":
            self.btn_tool_draw_road.setChecked(True)
            self.status_label.setText("Draw road tool: Click start intersection, then click destination intersection.")

    def set_status_message(self, msg: str):
        """Update the main status bar label."""
        self.status_label.setText(msg)

    def clear_selection(self):
        """Deselect currently selected element and return to scenario inspector."""
        self.canvas.set_selection(None, None)

    def on_canvas_selection_changed(self, element_type: str, element_id: str):
        """Synchronize Properties Inspector with canvas selection."""
        network = self.scenario_data.get("network", {})
        if element_type == "intersection":
            inter = next((i for i in network.get("intersections", []) if i.get("id") == element_id), None)
            if inter:
                self.lbl_inter_header.setText(f"INTERSECTION: {element_id}")
                idx = self.combo_inter_control.findText(inter.get("control_type", "uncontrolled"))
                if idx >= 0:
                    self.combo_inter_control.setCurrentIndex(idx)
                pos = inter.get("position", [0.0, 0.0])
                self.edit_inter_x.setText(str(pos[0]))
                self.edit_inter_y.setText(str(pos[1]))
                self.inspector_stack.setCurrentIndex(1)
                self.status_label.setText(f"Selected intersection '{element_id}'.")
                sig_idx = self.combo_signal_plan.findData(element_id)
                if sig_idx < 0:
                    sig_idx = self.combo_signal_plan.findText(element_id)
                if sig_idx >= 0:
                    self.combo_signal_plan.setCurrentIndex(sig_idx)
                return

        elif element_type == "segment":
            seg = next((s for s in network.get("segments", []) if s.get("id") == element_id), None)
            if seg:
                self.lbl_seg_header.setText(f"ROAD SEGMENT: {element_id}")
                self.lbl_seg_endpoints.setText(f"From: {seg.get('from')}  →  To: {seg.get('to')}")
                self.edit_seg_length.setText(str(seg.get("length_m", 100.0)))
                self.spin_seg_lanes.setValue(int(seg.get("lane_count", 1)))
                self.edit_seg_speed.setText(str(seg.get("speed_limit_mps", 13.9)))
                self.inspector_stack.setCurrentIndex(2)
                self.status_label.setText(f"Selected road segment '{element_id}'.")
                idx = self.combo_demand_segment.findText(element_id)
                if idx >= 0:
                    self.combo_demand_segment.setCurrentIndex(idx)
                return

        # No selection: display scenario overview
        self.inspector_stack.setCurrentIndex(0)

    def apply_intersection_properties(self):
        """Validate and apply property edits to the selected intersection."""
        iid = self.canvas.selected_id
        if not iid:
            return
        network = self.scenario_data.get("network", {})
        inter = next((i for i in network.get("intersections", []) if i.get("id") == iid), None)
        if not inter:
            return

        try:
            x_val = float(self.edit_inter_x.text())
            y_val = float(self.edit_inter_y.text())
            if not math.isfinite(x_val) or not math.isfinite(y_val):
                raise ValueError("Coordinates must be finite numbers.")
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Coordinates", f"Position coordinates must be valid numbers:\n{exc}")
            return

        control_val = self.combo_inter_control.currentText()
        inter["position"] = [round(x_val, 1), round(y_val, 1)]
        inter["control_type"] = control_val

        self._pending_edit_description = "Edit Intersection"
        self.on_network_modified()
        self.status_label.setText(f"Applied properties to intersection '{iid}'.")

    def apply_segment_properties(self):
        """Validate and apply property edits to the selected road segment."""
        sid = self.canvas.selected_id
        if not sid:
            return
        network = self.scenario_data.get("network", {})
        seg = next((s for s in network.get("segments", []) if s.get("id") == sid), None)
        if not seg:
            return

        try:
            length_val = float(self.edit_seg_length.text())
            if not math.isfinite(length_val) or length_val <= 0:
                raise ValueError("Length must be a finite number greater than zero.")
            lane_count = int(self.spin_seg_lanes.value())
            if lane_count < 1:
                raise ValueError("Lane count must be at least 1.")
            speed_val = float(self.edit_seg_speed.text())
            if not math.isfinite(speed_val) or speed_val <= 0:
                raise ValueError("Speed limit must be a finite number greater than zero.")
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Segment Properties", f"Invalid property values:\n{exc}")
            return

        seg["length_m"] = length_val
        seg["lane_count"] = lane_count
        seg["speed_limit_mps"] = speed_val

        self._pending_edit_description = "Edit Road Segment"
        self.on_network_modified()
        self.status_label.setText(f"Applied properties to road segment '{sid}'.")

    def on_demand_combo_changed(self, seg_id: str):
        """Update rate input and button text when the user picks a segment in the combo."""
        demand = self.scenario_data.get("demand", {})
        rates = demand.get("arrival_rates_vehicles_per_hour", {})
        if seg_id in rates:
            self.edit_demand_rate.setText(str(rates[seg_id]))
            self.btn_set_demand.setText("Update Rate")
            self.btn_remove_demand.setEnabled(True)
        else:
            self.edit_demand_rate.clear()
            self.btn_set_demand.setText("Add Demand Entry")
            self.btn_remove_demand.setEnabled(False)

    def on_demand_table_selection_changed(self):
        """Synchronize demand form and canvas selection when a row is selected in the demand table."""
        selected_items = self.demand_table.selectedItems()
        if not selected_items:
            return
        row = self.demand_table.currentRow()
        seg_item = self.demand_table.item(row, 0)
        rate_item = self.demand_table.item(row, 1)
        if seg_item and rate_item:
            seg_id = seg_item.text()
            self.combo_demand_segment.blockSignals(True)
            self.combo_demand_segment.setCurrentText(seg_id)
            self.combo_demand_segment.blockSignals(False)
            self.edit_demand_rate.setText(rate_item.text())
            self.btn_set_demand.setText("Update Rate")
            self.btn_remove_demand.setEnabled(True)
            self.canvas.set_selection("segment", seg_id)

    def refresh_demand_ui(self):
        """Refresh the Traffic Demand table and segment dropdown from active scenario data."""
        network = self.scenario_data.get("network", {})
        segments = network.get("segments", [])
        seg_ids = [s["id"] for s in segments if "id" in s]

        # Update segment combobox choices
        current_choice = self.combo_demand_segment.currentText()
        self.combo_demand_segment.blockSignals(True)
        self.combo_demand_segment.clear()
        self.combo_demand_segment.addItems(seg_ids)
        if current_choice in seg_ids:
            self.combo_demand_segment.setCurrentText(current_choice)
        elif seg_ids:
            self.combo_demand_segment.setCurrentIndex(0)
        self.combo_demand_segment.blockSignals(False)

        # Update demand table
        demand = self.scenario_data.setdefault("demand", {})
        rates = demand.setdefault("arrival_rates_vehicles_per_hour", {})
        self.demand_table.blockSignals(True)
        self.demand_table.setRowCount(len(rates))

        for row, (sid, rate) in enumerate(sorted(rates.items())):
            item_sid = QTableWidgetItem(sid)
            item_sid.setFlags(item_sid.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_rate = QTableWidgetItem(f"{float(rate):.1f}")
            item_rate.setFlags(item_rate.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.demand_table.setItem(row, 0, item_sid)
            self.demand_table.setItem(row, 1, item_rate)

        self.demand_table.blockSignals(False)

        if not rates:
            self.demand_table.hide()
            self.lbl_demand_empty.show()
            self.btn_remove_demand.setEnabled(False)
        else:
            self.demand_table.show()
            self.lbl_demand_empty.hide()
            self.btn_remove_demand.setEnabled(True)

        if self.combo_demand_segment.currentText():
            self.on_demand_combo_changed(self.combo_demand_segment.currentText())

    def apply_demand_entry(self) -> bool:
        """Validate and apply an arrival rate for the chosen road segment."""
        seg_id = self.combo_demand_segment.currentText().strip()
        if not seg_id:
            QMessageBox.warning(self, "No Road Selected", "Please select a road segment from the dropdown.")
            return False

        network = self.scenario_data.get("network", {})
        segments = network.get("segments", [])
        seg_obj = next((s for s in segments if s.get("id") == seg_id), None)
        if not seg_obj:
            QMessageBox.warning(self, "Invalid Road Segment", f"Road segment '{seg_id}' does not exist in the active network.")
            return False

        rate_text = self.edit_demand_rate.text().strip()
        try:
            rate_val = float(rate_text)
            if not math.isfinite(rate_val) or rate_val < 0:
                raise ValueError("Arrival rate must be a non-negative finite number (>= 0 veh/h).")
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Arrival Rate", f"Invalid arrival rate:\n{exc}")
            return False

        # Ensure turning movements and turning ratios are valid for this entry segment
        demand = self.scenario_data.setdefault("demand", {})
        arrival_rates = demand.setdefault("arrival_rates_vehicles_per_hour", {})
        turning_ratios = demand.setdefault("turning_ratios", {})
        moves = network.setdefault("turning_movements", [])

        seg_moves = [m for m in moves if m.get("from_segment") == seg_id]
        if not seg_moves:
            # Check if there is an outgoing segment at the intersection to connect to
            dest_intersection = seg_obj.get("to")
            outgoing_segs = [s for s in segments if s.get("from") == dest_intersection]
            if outgoing_segs:
                existing_tm_ids = [m["id"] for m in moves if "id" in m]
                new_tm_id = generate_unique_id("TM", existing_tm_ids)
                new_move = {
                    "id": new_tm_id,
                    "intersection": dest_intersection,
                    "from_segment": seg_id,
                    "to_segment": outgoing_segs[0]["id"],
                }
                moves.append(new_move)
                turning_ratios[new_tm_id] = 1.0
            else:
                QMessageBox.warning(
                    self,
                    "No Outgoing Route",
                    f"Road segment '{seg_id}' ends at intersection '{dest_intersection}', which has no outgoing road segments. "
                    "Vehicles cannot navigate without an outgoing route. Connect an outgoing road segment before adding traffic demand."
                )
                return False
        else:
            # Seg moves exist; verify turning_ratios has entries for them
            existing_ratios = {m["id"]: turning_ratios.get(m["id"]) for m in seg_moves if m["id"] in turning_ratios}
            if not existing_ratios:
                split = 1.0 / len(seg_moves)
                for m in seg_moves:
                    turning_ratios[m["id"]] = split

        # Backup previous state in case of validation error
        prev_rate = arrival_rates.get(seg_id)
        arrival_rates[seg_id] = rate_val

        # Validate with backend demand validator
        try:
            rates_dict = arrival_rates
            ratios_dict = {}
            moves_map = {m["id"]: m for m in moves}
            for mid, r in turning_ratios.items():
                if mid in moves_map:
                    ratios_dict.setdefault(moves_map[mid].get("from_segment"), {})[mid] = r
            validate_demand(rates_dict, ratios_dict)
        except DemandError as exc:
            if prev_rate is not None:
                arrival_rates[seg_id] = prev_rate
            else:
                arrival_rates.pop(seg_id, None)
            QMessageBox.warning(self, "Demand Validation Error", f"Cannot apply demand rate:\n{exc}")
            return False

        self._pending_edit_description = "Configure Demand"
        self.on_network_modified()
        self.refresh_demand_ui()
        self.status_label.setText(f"Traffic demand configured: '{seg_id}' -> {rate_val:.1f} veh/h.")
        return True

    def remove_demand_entry(self) -> bool:
        """Remove arrival rate entry for the selected segment."""
        seg_id = self.combo_demand_segment.currentText().strip()
        demand = self.scenario_data.get("demand", {})
        rates = demand.get("arrival_rates_vehicles_per_hour", {})
        if seg_id not in rates:
            return False

        rates.pop(seg_id, None)
        # Clean up turning ratios for movements originating from this segment
        moves = self.scenario_data.get("network", {}).get("turning_movements", [])
        from_moves = [m["id"] for m in moves if m.get("from_segment") == seg_id]
        t_ratios = demand.get("turning_ratios", {})
        for mid in from_moves:
            t_ratios.pop(mid, None)

        self._pending_edit_description = "Remove Demand"
        self.on_network_modified()
        self.refresh_demand_ui()
        self.status_label.setText(f"Removed traffic demand for road '{seg_id}'.")
        return True

    def refresh_signal_plans_ui(self):
        """Update Signal Plan Editor to match active scenario and network."""
        network = self.scenario_data.get("network", {})
        intersections = network.get("intersections", [])
        raw_plans = get_scenario_signal_plans(self.scenario_data)
        plan_iids = {p.get("intersection_id") for p in raw_plans if p.get("intersection_id")}
        signalized_iids = [
            i.get("id") for i in intersections
            if str(i.get("control_type", "")).lower() == "signalized" and i.get("id")
        ]
        all_iids = sorted(list(plan_iids.union(signalized_iids)))

        current_iid = self.combo_signal_plan.currentData()
        self.combo_signal_plan.blockSignals(True)
        self.combo_signal_plan.clear()

        if not all_iids:
            self.combo_signal_plan.addItem("No Signalized Intersections", "")
            self.combo_signal_plan.setEnabled(False)
            self.combo_signal_plan.blockSignals(False)
            self.phase_table.hide()
            self.phase_form_widget.hide()
            self.btn_create_plan.hide()
            self.lbl_plan_empty.show()
            self.lbl_plan_empty.setText("No signalized intersections in scenario.\nSet an intersection control type to 'signalized' in the Inspector.")
            self.lbl_plan_cycle.setText("Cycle duration: 0.0 s")
            return

        self.combo_signal_plan.setEnabled(True)
        select_idx = 0
        for idx, iid in enumerate(all_iids):
            label = f"{iid} (Signalized)" if iid in signalized_iids else f"{iid} (Uncontrolled)"
            self.combo_signal_plan.addItem(label, iid)
            if iid == current_iid:
                select_idx = idx

        self.combo_signal_plan.setCurrentIndex(select_idx)
        self.combo_signal_plan.blockSignals(False)

        self._load_selected_plan_to_ui()

    def _load_selected_plan_to_ui(self):
        """Load selected intersection's signal plan details into table and form."""
        iid = self.combo_signal_plan.currentData()
        if not iid:
            self.phase_table.hide()
            self.phase_form_widget.hide()
            self.btn_create_plan.hide()
            self.lbl_plan_empty.show()
            self.lbl_plan_cycle.setText("Cycle duration: 0.0 s")
            return

        raw_plans = get_scenario_signal_plans(self.scenario_data)
        plan_dict = next((p for p in raw_plans if p.get("intersection_id") == iid), None)

        if not plan_dict:
            self.phase_table.hide()
            self.phase_form_widget.hide()
            self.btn_create_plan.show()
            self.lbl_plan_empty.show()
            self.lbl_plan_empty.setText(f"No signal plan configured for '{iid}'.\nClick 'Create Signal Plan' to add one.")
            self.lbl_plan_cycle.setText("Cycle duration: 0.0 s")
            return

        phases = plan_dict.get("phases", [])
        if not phases:
            self.phase_table.hide()
            self.phase_form_widget.show()
            self.btn_create_plan.hide()
            self.lbl_plan_empty.show()
            self.lbl_plan_empty.setText(f"Signal plan for '{iid}' has no phases.\nFill timing fields below and click 'Add Phase'.")
            self.lbl_plan_cycle.setText("Cycle duration: 0.0 s")
            self.refresh_movements_checklist(iid, [])
            return

        self.lbl_plan_empty.hide()
        self.btn_create_plan.hide()
        self.phase_table.show()
        self.phase_form_widget.show()

        sorted_phases = sorted(phases, key=lambda p: p.get("order", 0))

        cycle = sum(
            float(p.get("green_s", 0.0)) + float(p.get("yellow_s", 0.0)) + float(p.get("all_red_s", 0.0))
            for p in sorted_phases
        )
        self.lbl_plan_cycle.setText(f"Cycle duration: {cycle:.1f} s")

        prev_row = self.phase_table.currentRow()
        self.phase_table.blockSignals(True)
        self.phase_table.setRowCount(len(sorted_phases))
        for row, p in enumerate(sorted_phases):
            order_item = QTableWidgetItem(str(p.get("order", row + 1)))
            green_item = QTableWidgetItem(f"{float(p.get('green_s', 0.0)):.1f}")
            yellow_item = QTableWidgetItem(f"{float(p.get('yellow_s', 0.0)):.1f}")
            all_red_item = QTableWidgetItem(f"{float(p.get('all_red_s', 0.0)):.1f}")
            m_list = p.get("movement_ids", [])
            moves_item = QTableWidgetItem(", ".join(m_list))

            for it in (order_item, green_item, yellow_item, all_red_item, moves_item):
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.phase_table.setItem(row, 0, order_item)
            self.phase_table.setItem(row, 1, green_item)
            self.phase_table.setItem(row, 2, yellow_item)
            self.phase_table.setItem(row, 3, all_red_item)
            self.phase_table.setItem(row, 4, moves_item)

        sel_row = prev_row if 0 <= prev_row < len(sorted_phases) else 0
        self.phase_table.selectRow(sel_row)
        self.phase_table.blockSignals(False)
        self.on_phase_table_selection_changed()

    def on_signal_plan_combo_changed(self):
        """Handle intersection selection change in signal plan combo."""
        self._load_selected_plan_to_ui()

    def on_phase_table_selection_changed(self):
        """Update form inputs and movement checklist when phase table selection changes."""
        iid = self.combo_signal_plan.currentData()
        if not iid:
            return
        row = self.phase_table.currentRow()
        raw_plans = get_scenario_signal_plans(self.scenario_data)
        plan_dict = next((p for p in raw_plans if p.get("intersection_id") == iid), None)
        if not plan_dict:
            return
        phases = sorted(plan_dict.get("phases", []), key=lambda p: p.get("order", 0))
        if 0 <= row < len(phases):
            p = phases[row]
            self.spin_phase_order.setValue(int(p.get("order", row + 1)))
            self.edit_phase_green.setText(f"{float(p.get('green_s', 20.0)):.1f}")
            self.edit_phase_yellow.setText(f"{float(p.get('yellow_s', 3.0)):.1f}")
            self.edit_phase_all_red.setText(f"{float(p.get('all_red_s', 1.0)):.1f}")
            self.refresh_movements_checklist(iid, p.get("movement_ids", []))
            self.btn_apply_phase.setEnabled(True)
            self.btn_remove_phase.setEnabled(True)
            self.btn_phase_up.setEnabled(row > 0)
            self.btn_phase_down.setEnabled(row < len(phases) - 1)
        else:
            self.refresh_movements_checklist(iid, [])
            self.btn_apply_phase.setEnabled(False)
            self.btn_remove_phase.setEnabled(False)
            self.btn_phase_up.setEnabled(False)
            self.btn_phase_down.setEnabled(False)

    def refresh_movements_checklist(self, iid: str, selected_moves=None):
        """Populate turning movements checklist for the given intersection."""
        self.list_phase_movements.clear()
        moves = [
            m for m in self.scenario_data.get("network", {}).get("turning_movements", [])
            if m.get("intersection") == iid
        ]
        if not moves:
            item = QListWidgetItem("No turning movements at this intersection")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_phase_movements.addItem(item)
            return

        sel_set = set(selected_moves or [])
        for m in moves:
            mid = m.get("id", "")
            from_seg = m.get("from_segment", "?")
            to_seg = m.get("to_segment", "?")
            item = QListWidgetItem(f"{mid} ({from_seg} → {to_seg})")
            item.setData(Qt.ItemDataRole.UserRole, mid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if mid in sel_set else Qt.CheckState.Unchecked)
            self.list_phase_movements.addItem(item)

    def get_selected_movement_ids(self) -> list[str]:
        """Return list of turning movement IDs currently checked in the checklist."""
        selected = []
        for i in range(self.list_phase_movements.count()):
            item = self.list_phase_movements.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                mid = item.data(Qt.ItemDataRole.UserRole)
                if mid:
                    selected.append(mid)
        return selected

    def create_signal_plan_for_selected(self):
        """Create a default valid signal plan for the selected signalized intersection."""
        iid = self.combo_signal_plan.currentData()
        if not iid:
            return
        moves = [
            m.get("id") for m in self.scenario_data.get("network", {}).get("turning_movements", [])
            if m.get("intersection") == iid and m.get("id")
        ]
        if not moves:
            QMessageBox.warning(
                self,
                "No Turning Movements",
                f"Intersection '{iid}' has no turning movements. Add turning movements connecting roads to this intersection first."
            )
            return

        network = self.scenario_data.get("network", {})
        inter = next((i for i in network.get("intersections", []) if i.get("id") == iid), None)
        if inter and inter.get("control_type") != "signalized":
            inter["control_type"] = "signalized"

        new_plan = {
            "intersection_id": iid,
            "phases": [
                {
                    "order": 1,
                    "movement_ids": [moves[0]],
                    "green_s": 20.0,
                    "yellow_s": 3.0,
                    "all_red_s": 1.0,
                }
            ],
        }

        raw_plans = copy.deepcopy(get_scenario_signal_plans(self.scenario_data))
        raw_plans.append(new_plan)

        try:
            plan_obj = plan_from_dict({"signal_plan": new_plan})
            net_obj = network_from_dict(self.scenario_data)
            res = validate_signal_plan(plan_obj, net_obj)
            if not res.is_valid:
                err_msgs = "\n".join(f"• [{e.code}] {e.message}" for e in res.errors)
                QMessageBox.warning(self, "Invalid Signal Plan", f"Could not create plan:\n{err_msgs}")
                return
        except Exception as exc:
            QMessageBox.warning(self, "Validation Error", f"Could not create plan:\n{exc}")
            return

        set_scenario_signal_plans(self.scenario_data, raw_plans)
        self._pending_edit_description = "Create Signal Plan"
        self.on_network_modified()
        self.status_label.setText(f"Created signal plan for intersection '{iid}'.")

    def apply_phase_edits(self) -> bool:
        """Validate and apply edits to the currently selected signal phase."""
        iid = self.combo_signal_plan.currentData()
        if not iid:
            return False
        row = self.phase_table.currentRow()
        raw_plans = copy.deepcopy(get_scenario_signal_plans(self.scenario_data))
        plan_dict = next((p for p in raw_plans if p.get("intersection_id") == iid), None)
        if not plan_dict:
            return False
        phases = sorted(plan_dict.get("phases", []), key=lambda p: p.get("order", 0))
        if not (0 <= row < len(phases)):
            QMessageBox.warning(self, "No Phase Selected", "Please select a phase from the table to edit.")
            return False

        try:
            green_val = float(self.edit_phase_green.text().strip())
            yellow_val = float(self.edit_phase_yellow.text().strip())
            all_red_val = float(self.edit_phase_all_red.text().strip())
            order_val = int(self.spin_phase_order.value())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Timing Values", f"Durations must be valid numeric values:\n{exc}")
            return False

        checked_moves = self.get_selected_movement_ids()
        if not checked_moves:
            QMessageBox.warning(self, "No Movements Assigned", "A phase must have at least one turning movement assigned.")
            return False

        phases[row] = {
            "order": order_val,
            "movement_ids": checked_moves,
            "green_s": green_val,
            "yellow_s": yellow_val,
            "all_red_s": all_red_val,
        }
        plan_dict["phases"] = phases

        try:
            plan_obj = plan_from_dict({"signal_plan": plan_dict})
            net_obj = network_from_dict(self.scenario_data)
            res = validate_signal_plan(plan_obj, net_obj)
        except Exception as exc:
            QMessageBox.warning(self, "Signal Plan Format Error", f"Invalid signal plan structure:\n{exc}")
            return False

        if not res.is_valid:
            err_msgs = "\n".join(f"• [{e.code}] {e.message}" for e in res.errors)
            QMessageBox.warning(self, "Signal Plan Validation Error", f"Cannot apply phase changes:\n\n{err_msgs}")
            return False

        set_scenario_signal_plans(self.scenario_data, raw_plans)
        self._pending_edit_description = "Edit Signal Phase"
        self.on_network_modified()
        warn_text = f" ({len(res.warnings)} warnings)" if res.warnings else ""
        self.status_label.setText(f"Applied phase {order_val} for '{iid}'{warn_text}.")
        return True

    def add_new_phase(self) -> bool:
        """Add a new phase to the currently selected signal plan."""
        iid = self.combo_signal_plan.currentData()
        if not iid:
            return False
        raw_plans = copy.deepcopy(get_scenario_signal_plans(self.scenario_data))
        plan_dict = next((p for p in raw_plans if p.get("intersection_id") == iid), None)
        if not plan_dict:
            plan_dict = {"intersection_id": iid, "phases": []}
            raw_plans.append(plan_dict)

        phases = plan_dict.get("phases", [])
        next_order = max([p.get("order", 0) for p in phases], default=0) + 1

        try:
            green_text = self.edit_phase_green.text().strip()
            yellow_text = self.edit_phase_yellow.text().strip()
            all_red_text = self.edit_phase_all_red.text().strip()
            green_val = float(green_text) if green_text else 20.0
            yellow_val = float(yellow_text) if yellow_text else 3.0
            all_red_val = float(all_red_text) if all_red_text else 1.0
            order_val = int(self.spin_phase_order.value()) if self.spin_phase_order.value() != 1 or not phases else next_order
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Timing Values", f"Durations must be valid numeric values:\n{exc}")
            return False

        checked_moves = self.get_selected_movement_ids()
        if not checked_moves:
            all_moves = [
                m.get("id") for m in self.scenario_data.get("network", {}).get("turning_movements", [])
                if m.get("intersection") == iid and m.get("id")
            ]
            assigned_moves = {m for p in phases for m in p.get("movement_ids", [])}
            unassigned = [m for m in all_moves if m not in assigned_moves]
            checked_moves = unassigned if unassigned else all_moves[:1]

        new_phase = {
            "order": order_val,
            "movement_ids": checked_moves,
            "green_s": green_val,
            "yellow_s": yellow_val,
            "all_red_s": all_red_val,
        }
        phases.append(new_phase)
        plan_dict["phases"] = phases

        try:
            plan_obj = plan_from_dict({"signal_plan": plan_dict})
            net_obj = network_from_dict(self.scenario_data)
            res = validate_signal_plan(plan_obj, net_obj)
        except Exception as exc:
            QMessageBox.warning(self, "Signal Plan Format Error", f"Invalid signal plan structure:\n{exc}")
            return False

        if not res.is_valid:
            err_msgs = "\n".join(f"• [{e.code}] {e.message}" for e in res.errors)
            QMessageBox.warning(self, "Signal Plan Validation Error", f"Cannot add phase:\n\n{err_msgs}")
            return False

        set_scenario_signal_plans(self.scenario_data, raw_plans)
        self._pending_edit_description = "Add Signal Phase"
        self.on_network_modified()
        self.phase_table.selectRow(self.phase_table.rowCount() - 1)
        warn_text = f" ({len(res.warnings)} warnings)" if res.warnings else ""
        self.status_label.setText(f"Added phase {order_val} to '{iid}'{warn_text}.")
        return True

    def remove_selected_phase(self) -> bool:
        """Remove currently selected phase, renumbering remaining phases sequentially."""
        iid = self.combo_signal_plan.currentData()
        if not iid:
            return False
        row = self.phase_table.currentRow()
        raw_plans = copy.deepcopy(get_scenario_signal_plans(self.scenario_data))
        plan_dict = next((p for p in raw_plans if p.get("intersection_id") == iid), None)
        if not plan_dict:
            return False
        phases = sorted(plan_dict.get("phases", []), key=lambda p: p.get("order", 0))
        if not (0 <= row < len(phases)):
            return False

        phases.pop(row)
        for i, p in enumerate(phases):
            p["order"] = i + 1
        plan_dict["phases"] = phases

        try:
            plan_obj = plan_from_dict({"signal_plan": plan_dict})
            net_obj = network_from_dict(self.scenario_data)
            res = validate_signal_plan(plan_obj, net_obj)
        except Exception as exc:
            QMessageBox.warning(self, "Signal Plan Format Error", f"Invalid signal plan structure:\n{exc}")
            return False

        if not res.is_valid:
            err_msgs = "\n".join(f"• [{e.code}] {e.message}" for e in res.errors)
            QMessageBox.warning(self, "Signal Plan Validation Error", f"Cannot remove phase:\n\n{err_msgs}")
            return False

        set_scenario_signal_plans(self.scenario_data, raw_plans)
        self._pending_edit_description = "Remove Signal Phase"
        self.on_network_modified()
        self.status_label.setText(f"Removed phase from '{iid}'.")
        return True

    def reorder_phase(self, direction: int) -> bool:
        """Move selected phase Up (-1) or Down (+1), renumbering orders sequentially."""
        iid = self.combo_signal_plan.currentData()
        if not iid:
            return False
        row = self.phase_table.currentRow()
        raw_plans = copy.deepcopy(get_scenario_signal_plans(self.scenario_data))
        plan_dict = next((p for p in raw_plans if p.get("intersection_id") == iid), None)
        if not plan_dict:
            return False
        phases = sorted(plan_dict.get("phases", []), key=lambda p: p.get("order", 0))
        target_row = row + direction
        if not (0 <= target_row < len(phases)):
            return False

        phases[row], phases[target_row] = phases[target_row], phases[row]
        for i, p in enumerate(phases):
            p["order"] = i + 1
        plan_dict["phases"] = phases

        try:
            plan_obj = plan_from_dict({"signal_plan": plan_dict})
            net_obj = network_from_dict(self.scenario_data)
            res = validate_signal_plan(plan_obj, net_obj)
        except Exception as exc:
            QMessageBox.warning(self, "Signal Plan Format Error", f"Invalid signal plan structure:\n{exc}")
            return False

        if not res.is_valid:
            err_msgs = "\n".join(f"• [{e.code}] {e.message}" for e in res.errors)
            QMessageBox.warning(self, "Signal Plan Validation Error", f"Cannot reorder phases:\n\n{err_msgs}")
            return False

        set_scenario_signal_plans(self.scenario_data, raw_plans)
        self._pending_edit_description = "Reorder Signal Phase"
        self.on_network_modified()
        self.phase_table.selectRow(target_row)
        self.status_label.setText(f"Reordered phases for '{iid}'.")
        return True

    def delete_selected_object(self):
        """Invoke deletion on the currently selected canvas object with user feedback."""
        success, msg = self.canvas.delete_selected()
        self.status_label.setText(msg)
        if not success:
            QMessageBox.warning(self, "Cannot Delete Object", msg)

    def validate_current_network(self) -> ValidationResult:
        """Run backend network validation and refresh the Network Validation panel."""
        try:
            net_obj = network_from_dict(self.scenario_data)
            result = validate(net_obj)
        except NetworkFormatError as exc:
            result = ValidationResult([
                ValidationIssue("FORMAT_ERROR", str(exc), "network", "")
            ])

        self.validation_issues = result.issues
        self.validation_list.clear()

        if result.is_valid and not result.warnings:
            self.validation_status_label.setText("✔ Network Valid (0 issues)")
            self.validation_status_label.setStyleSheet("color: #16a34a; font-weight: 700;")
            self.validation_list.hide()
        elif result.is_valid and result.warnings:
            self.validation_status_label.setText(f"✔ Network Valid ({len(result.warnings)} warnings)")
            self.validation_status_label.setStyleSheet("color: #d97706; font-weight: 700;")
            self.validation_list.show()
            for w in result.warnings:
                item = QListWidgetItem(f"⚠ [{w.code}] {w.message}")
                item.setForeground(QColor("#d97706"))
                self.validation_list.addItem(item)
        else:
            err_count = len(result.errors)
            warn_count = len(result.warnings)
            self.validation_status_label.setText(f"❌ {err_count} Error(s), {warn_count} Warning(s)")
            self.validation_status_label.setStyleSheet("color: #dc2626; font-weight: 700;")
            self.validation_list.show()
            for e in result.errors:
                item = QListWidgetItem(f"❌ [{e.code}] {e.message}")
                item.setForeground(QColor("#dc2626"))
                self.validation_list.addItem(item)
            for w in result.warnings:
                item = QListWidgetItem(f"⚠ [{w.code}] {w.message}")
                item.setForeground(QColor("#d97706"))
                self.validation_list.addItem(item)

        return result

    def on_validation_item_clicked(self, item: QListWidgetItem):
        """Clicking a validation issue highlights and inspects the affected element."""
        row = self.validation_list.row(item)
        if 0 <= row < len(self.validation_issues):
            issue = self.validation_issues[row]
            if issue.element_type in ("intersection", "segment") and issue.element_id:
                self.canvas.set_selection(issue.element_type, issue.element_id)

    def on_network_modified(self, description: str = ""):
        """Synchronize engine, metrics, canvas, demand, signal plans, and validation whenever network changes."""
        self.set_dirty(True)
        if not getattr(self, "_is_restoring_history", False) and hasattr(self, "history_manager"):
            desc = (
                description
                or getattr(self, "_pending_edit_description", "")
                or getattr(self.canvas, "_pending_edit_description", "")
                or "Edit Network"
            )
            self.history_manager.push(self.scenario_data, desc)
            self._pending_edit_description = ""
            if hasattr(self.canvas, "_pending_edit_description"):
                self.canvas._pending_edit_description = ""
            if hasattr(self, "update_undo_redo_actions"):
                self.update_undo_redo_actions()

        self.timer.stop()
        self.update_metrics()
        self.canvas.reparse_signal_plans()
        self.refresh_demand_ui()
        self.refresh_signal_plans_ui()
        val_result = self.validate_current_network()

        # Re-initialize engine if network is valid
        if val_result.is_valid:
            try:
                raw_plans = get_scenario_signal_plans(self.scenario_data)
                plans = [plan_from_dict({"signal_plan": p}) for p in raw_plans]
                self.engine = build_engine(
                    network_from_dict(self.scenario_data),
                    plans,
                    self.scenario_data.get("demand", {}),
                    self.scenario_data.get("simulation", {}),
                )
                self.canvas.engine = self.engine
                self.change_speed(self.speed_box.currentText())
                self.status_label.setText("Network updated. Simulation ready.")
            except DemandError as exc:
                self.engine = None
                self.canvas.engine = None
                self.status_label.setText(f"Simulation engine paused: demand configuration error ({exc})")
            except SignalPlanBlockedError as exc:
                self.engine = None
                self.canvas.engine = None
                self.status_label.setText(f"Simulation engine paused: signal plan error ({exc})")
            except Exception as exc:
                self.engine = None
                self.canvas.engine = None
                self.status_label.setText(f"Simulation engine paused: {exc}")
        else:
            self.engine = None
            self.canvas.engine = None
            self.status_label.setText(f"Network has {len(val_result.errors)} validation error(s). Simulation paused.")

        if hasattr(self, "history_tracker"):
            self.history_tracker.reset()
            if self.engine is not None:
                self.history_tracker.record_state(self.engine)
        self.update_metrics()
        self.canvas.update()

    def start_simulation(self):
        if self.engine is None or self.engine.finished:
            self.status_label.setText("Simulation finished or not ready — press Reset to run again")
            self.update_playback_controls_state()
            return
        if self.timer.isActive():
            return
        self.engine.start()
        self.timer.start()
        self.status_label.setText("Simulation running")
        self.update_metrics()

    def pause_simulation(self):
        if self.timer.isActive():
            self.timer.stop()
        if self.engine is not None:
            self.engine.pause()
        self.status_label.setText("Simulation paused")
        self.update_metrics()

    def step_simulation(self):
        if self.engine is None or self.engine.finished:
            return
        if self.timer.isActive():
            self.timer.stop()
        self.engine.pause()
        self.engine.step()
        if hasattr(self, "history_tracker"):
            self.history_tracker.record_state(self.engine, force=True)
        self.canvas.update()
        self.update_metrics()
        self.status_label.setText(
            "Simulation completed" if self.engine.finished
            else "Advanced one simulation step"
        )

    def reset_simulation(self):
        if self.timer.isActive():
            self.timer.stop()
        if self.engine is not None:
            self.engine.reset()
            if hasattr(self, "speed_box"):
                self.change_speed(self.speed_box.currentText())
        if hasattr(self, "history_tracker"):
            self.history_tracker.reset()
            if self.engine is not None:
                self.history_tracker.record_state(self.engine)
        self.canvas.update()
        self.update_metrics()
        self.status_label.setText("Simulation reset")

    def change_speed(self, value):
        if self.engine is not None:
            clean_str = str(value).replace("×", "").replace("x", "").strip()
            try:
                multiplier = float(clean_str)
                self.engine.set_speed(multiplier)
            except (ValueError, TypeError) as exc:
                logger.warning("Invalid speed value: %s (%s)", value, exc)

    def advance_simulation(self):
        if self.engine is not None and getattr(self.engine, "running", False):
            self.engine.advance(self.timer.interval() / 1000.0)
            self.canvas.update()
            self.update_metrics()
            if self.engine.finished:
                if self.timer.isActive():
                    self.timer.stop()
                self.status_label.setText("Simulation completed")
                self.update_metrics()

    def _shortcut_toggle_play_pause(self):
        focused = QApplication.focusWidget() or (self.focusWidget() if hasattr(self, "focusWidget") else None)
        if isinstance(focused, (QLineEdit, QSpinBox)):
            return
        if self.engine is not None and getattr(self.engine, "running", False):
            self.pause_simulation()
        elif hasattr(self, "btn_play") and self.btn_play.isEnabled():
            self.start_simulation()

    def _shortcut_step(self):
        focused = QApplication.focusWidget() or (self.focusWidget() if hasattr(self, "focusWidget") else None)
        if isinstance(focused, (QLineEdit, QSpinBox)):
            return
        if hasattr(self, "btn_step") and self.btn_step.isEnabled():
            self.step_simulation()

    def _shortcut_reset(self):
        focused = QApplication.focusWidget() or (self.focusWidget() if hasattr(self, "focusWidget") else None)
        if isinstance(focused, (QLineEdit, QSpinBox)):
            return
        if hasattr(self, "btn_reset") and self.btn_reset.isEnabled():
            self.reset_simulation()

    def update_playback_controls_state(self):
        """Synchronize playback button states, progress bar, and labels with current simulation state."""
        if not hasattr(self, "btn_play"):
            return

        if self.engine is None:
            self.btn_play.setEnabled(False)
            self.btn_play.setText("▶  Play")
            self.btn_pause.setEnabled(False)
            self.btn_step.setEnabled(False)
            self.btn_reset.setEnabled(False)
            if hasattr(self, "progress_bar"):
                self.progress_bar.setValue(0)
                self.progress_bar.setFormat("0.0% (0.0 / 0.0 s)")
            return

        t = self.engine.time
        dur = self.engine.duration if self.engine.duration > 0 else 600.0
        finished = self.engine.finished
        running = getattr(self.engine, "running", False) and not finished

        if finished:
            self.btn_play.setEnabled(False)
            self.btn_play.setText("▶  Play")
            self.btn_pause.setEnabled(False)
            self.btn_step.setEnabled(False)
            self.btn_reset.setEnabled(True)
            pct = 100.0
        elif running:
            self.btn_play.setEnabled(False)
            self.btn_play.setText("▶  Play")
            self.btn_pause.setEnabled(True)
            self.btn_step.setEnabled(False)
            self.btn_reset.setEnabled(True)
            pct = min(100.0, (t / dur) * 100.0) if dur > 0 else 0.0
        elif t > 0:
            self.btn_play.setEnabled(True)
            self.btn_play.setText("▶  Resume")
            self.btn_pause.setEnabled(False)
            self.btn_step.setEnabled(True)
            self.btn_reset.setEnabled(True)
            pct = min(100.0, (t / dur) * 100.0) if dur > 0 else 0.0
        else:
            self.btn_play.setEnabled(True)
            self.btn_play.setText("▶  Play")
            self.btn_pause.setEnabled(False)
            self.btn_step.setEnabled(True)
            self.btn_reset.setEnabled(False)
            pct = 0.0

        if hasattr(self, "progress_bar"):
            bar_val = int(round(pct * 10))
            self.progress_bar.setValue(max(0, min(1000, bar_val)))
            self.progress_bar.setFormat(f"{pct:.1f}% ({t:.1f} / {dur:.1f} s)")

    def update_metrics(self):
        if self.engine is None:
            if hasattr(self, "metric_status_label"):
                self._update_status_badge("Ready")
            if hasattr(self, "metric_time"):
                self.metric_time.setText("0.0 s")
            if hasattr(self, "metric_duration_label"):
                self.metric_duration_label.setText("/ 0.0 s")
            if hasattr(self, "clock_label"):
                self.clock_label.setText("Simulation time: 0.0 s")
            if hasattr(self, "vehicle_count_label"):
                self.vehicle_count_label.setText("0")
            if hasattr(self, "completed_label"):
                self.completed_label.setText("0")
            if hasattr(self, "generated_label"):
                self.generated_label.setText("0")
            if hasattr(self, "entered_label"):
                self.entered_label.setText("0")
            if hasattr(self, "remaining_label"):
                self.remaining_label.setText("0")
            if hasattr(self, "mean_travel_time_label"):
                self.mean_travel_time_label.setText("N/A")
            if hasattr(self, "history_tracker"):
                self.history_tracker.reset()
            if hasattr(self, "timeline_widget"):
                self.timeline_widget.update_state(0.0, 600.0, "Ready")
            if hasattr(self, "counts_chart"):
                self.counts_chart.update()
            if hasattr(self, "travel_time_chart"):
                self.travel_time_chart.update()
            self.update_playback_controls_state()
            return

        m = compute_metrics(self.engine)

        if hasattr(self, "history_tracker"):
            self.history_tracker.record_state(self.engine, force=self.engine.finished)
        if hasattr(self, "timeline_widget"):
            self.timeline_widget.update_state(m.simulated_time, m.duration, m.status)
        if hasattr(self, "counts_chart"):
            self.counts_chart.set_duration(m.duration)
            self.counts_chart.update()
        if hasattr(self, "travel_time_chart"):
            self.travel_time_chart.set_duration(m.duration)
            self.travel_time_chart.update()

        if hasattr(self, "metric_status_label"):
            self._update_status_badge(m.status)
        self.clock_label.setText(f"Simulation time: {m.simulated_time:.1f} s")
        self.metric_time.setText(f"{m.simulated_time:.1f} s")
        if hasattr(self, "metric_duration_label"):
            self.metric_duration_label.setText(f"/ {m.duration:.1f} s")

        self.vehicle_count_label.setText(str(m.vehicles_in_network))
        self.completed_label.setText(str(m.vehicles_completed))
        self.generated_label.setText(str(m.vehicles_generated))
        if hasattr(self, "entered_label"):
            self.entered_label.setText(str(m.vehicles_entered))
        waiting = max(0, m.vehicles_generated - m.vehicles_entered)
        self.remaining_label.setText(str(waiting))

        if hasattr(self, "mean_travel_time_label"):
            if m.mean_travel_time is not None:
                self.mean_travel_time_label.setText(f"{m.mean_travel_time:.1f} s")
            else:
                self.mean_travel_time_label.setText("N/A")

        network = self.scenario_data.get("network", {})
        intersections = network.get("intersections", [])
        segments = network.get("segments", [])
        self.intersections_label.setText(f"Intersections: {len(intersections)}")
        self.segments_label.setText(f"Road segments: {len(segments)}")
        signalized = sum(
            1 for item in intersections
            if str(item.get("control_type", "")).lower() == "signalized"
        )
        self.control_label.setText(f"Signalized intersections: {signalized}")
        if self.scenario_path:
            self.scenario_file_label.setText(self.scenario_path.name)
            self.scenario_file_label.setToolTip(str(self.scenario_path))
        self.scenario_name_label.setText(self.scenario_data.get("name", "Scenario"))
        self.update_playback_controls_state()

    def open_scenario_dialog(self):
        """Prompt user with file dialog to open and load a scenario JSON file."""
        if not self.maybe_save_changes():
            return

        start_dir = str(self.scenario_path.parent) if self.scenario_path else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Scenario",
            start_dir,
            "JSON Files (*.json);;All Files (*)",
        )
        if not file_path:
            self.status_label.setText("Scenario loading cancelled")
            return
        self.load_scenario_file(file_path)

    def load_scenario_file(self, path: str | Path) -> bool:
        """Load and validate a scenario from path, preserving existing state on failure."""
        path = Path(path)
        try:
            new_data = load_scenario_document(path)
            new_engine = load_scenario(path)
        except NetworkBlockedError as exc:
            logger.warning("Network validation failed for %s: %s", path, exc)
            bullet_points = "\n".join(f"• [{err.code}] {err.message}" for err in exc.errors)
            msg = f"The scenario network has validation errors:\n\n{bullet_points}"
            self._handle_load_error(msg, f"Network validation failed ({len(exc.errors)} errors)")
            return False
        except SignalPlanBlockedError as exc:
            logger.warning("Signal plan validation failed for %s: %s", path, exc)
            bullet_points = "\n".join(f"• [{err.code}] {err.message}" for err in exc.errors)
            msg = f"The scenario signal plan has validation errors:\n\n{bullet_points}"
            self._handle_load_error(msg, f"Signal plan validation failed ({len(exc.errors)} errors)")
            return False
        except DemandError as exc:
            logger.warning("Demand validation failed for %s: %s", path, exc)
            errors = getattr(exc, "errors", [str(exc)])
            bullet_points = "\n".join(f"• {err}" for err in errors)
            msg = f"The scenario demand configuration is invalid:\n\n{bullet_points}"
            self._handle_load_error(msg, "Invalid traffic demand configuration")
            return False
        except ScenarioFormatError as exc:
            logger.warning("Scenario format error in %s: %s", path, exc)
            self._handle_load_error(f"The scenario file format is invalid:\n\n{exc}", "Invalid scenario format")
            return False
        except (NetworkFormatError, ValueError, KeyError) as exc:
            logger.warning("Validation error in %s: %s", path, exc)
            self._handle_load_error(f"Invalid scenario data:\n\n{exc}", "Invalid scenario data")
            return False
        except OSError as exc:
            logger.warning("File error reading %s: %s", path, exc)
            self._handle_load_error(f"Unable to read scenario file:\n\n{exc}", "Failed to read file")
            return False
        except Exception as exc:
            logger.exception("Unexpected error loading scenario %s: %s", path, exc)
            self._handle_load_error(f"An unexpected error occurred while loading the scenario:\n\n{exc}", "Error loading scenario")
            return False

        self.timer.stop()
        self.scenario_path = path
        self.scenario_data = new_data
        self.engine = new_engine

        self.change_speed(self.speed_box.currentText())
        self.canvas.set_scenario(self.engine, self.scenario_data)
        if hasattr(self, "history_tracker"):
            self.history_tracker.reset()
            self.history_tracker.record_state(self.engine)
        self.update_metrics()
        self.validate_current_network()
        self.refresh_demand_ui()
        self.refresh_signal_plans_ui()

        self.status_label.setText(f"Scenario '{self.scenario_path.name}' loaded successfully")
        self.set_dirty(False)
        if hasattr(self, "history_manager"):
            self.history_manager.reset(self.scenario_data)
        if hasattr(self, "update_undo_redo_actions"):
            self.update_undo_redo_actions()
        return True

    def _handle_load_error(self, message: str, status_msg: str):
        self.status_label.setText(f"Failed to load scenario: {status_msg}")
        QMessageBox.critical(self, "Unable to Load Scenario", message)

    def set_dirty(self, dirty: bool = True):
        """Set or clear dirty state and update window title."""
        self.is_dirty = bool(dirty)
        self.dirty = self.is_dirty
        if self.is_dirty:
            self.setWindowTitle("TMS-Sim *")
        else:
            self.setWindowTitle("TMS-Sim")

    def prompt_save_changes_dialog(self) -> str:
        """Prompt user with Save, Discard, Cancel dialog. Returns 'save', 'discard', or 'cancel'."""
        if hasattr(self, "save_prompt_handler") and callable(self.save_prompt_handler):
            return self.save_prompt_handler()

        app = QApplication.instance()
        if app is not None and app.platformName() == "offscreen":
            return "discard"

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Unsaved Changes")
        box.setText("The current scenario has unsaved changes.\nDo you want to save them before continuing?")
        btn_save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        btn_discard = box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_save)
        box.exec()

        clicked = box.clickedButton()
        if clicked == btn_save:
            return "save"
        elif clicked == btn_discard:
            return "discard"
        else:
            return "cancel"

    def maybe_save_changes(self) -> bool:
        """Check for unsaved changes before a destructive action.

        Returns:
            True if it is safe to proceed (not dirty, discarded, or saved successfully).
            False if the action should be aborted (cancelled or save failed).
        """
        if not self.is_dirty:
            return True

        decision = self.prompt_save_changes_dialog()
        if decision == "save":
            return self.save_scenario()
        elif decision == "discard":
            return True
        else:  # cancel
            return False

    def confirm_overwrite(self, path: Path) -> bool:
        """Prompt confirmation before overwriting an existing file."""
        app = QApplication.instance()
        if app is not None and app.platformName() == "offscreen":
            return True
        reply = QMessageBox.question(
            self,
            "Confirm Overwrite",
            f"The file '{path.name}' already exists.\nDo you want to replace it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _write_scenario_to_path(self, target_path: str | Path) -> bool:
        """Helper to validate and write scenario data to target path."""
        target = Path(target_path)
        try:
            save_scenario_document(self.scenario_data, target)
        except ScenarioFormatError as exc:
            logger.warning("Scenario serialization error saving to %s: %s", target, exc)
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Cannot save scenario: the configuration is invalid.\n\n{exc}",
            )
            return False
        except OSError as exc:
            logger.warning("File error saving scenario to %s: %s", target, exc)
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Cannot write scenario file to:\n{target}\n\n{exc}",
            )
            return False
        except Exception as exc:
            logger.exception("Unexpected error saving scenario to %s: %s", target, exc)
            QMessageBox.critical(
                self,
                "Save Failed",
                f"An unexpected error occurred while saving:\n\n{exc}",
            )
            return False

        self.scenario_path = target
        self.set_dirty(False)
        self.scenario_file_label.setText(target.name)
        self.scenario_file_label.setToolTip(str(target))
        self.status_label.setText(f"Scenario saved successfully to '{target.name}'")
        return True

    def save_scenario(self) -> bool:
        """Save scenario to current path, or prompt Save As if path is unset."""
        if self.scenario_path is not None:
            return self._write_scenario_to_path(self.scenario_path)
        return self.save_scenario_as()

    def save_scenario_as(self, path: str | Path | None = None) -> bool:
        """Prompt user for a destination path and save the scenario."""
        if path is None:
            start_dir = str(self.scenario_path.parent) if self.scenario_path else ""
            default_name = self.scenario_path.name if self.scenario_path else "scenario.json"
            start_path = str(Path(start_dir) / default_name) if start_dir else default_name

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Scenario As",
                start_path,
                "JSON Files (*.json);;All Files (*)",
                options=QFileDialog.Option.DontConfirmOverwrite,
            )
            if not file_path:
                self.status_label.setText("Save cancelled")
                return False
            path = file_path

        dest = Path(path)
        if dest.suffix.lower() != ".json":
            dest = dest.with_suffix(".json")

        if dest.exists() and not self.confirm_overwrite(dest):
            self.status_label.setText("Save cancelled: existing file not overwritten")
            return False

        return self._write_scenario_to_path(dest)

    def closeEvent(self, event):
        """Handle application close event, prompting to save unsaved changes."""
        if self.maybe_save_changes():
            self.timer.stop()
            event.accept()
        else:
            event.ignore()

    @property
    def can_undo(self) -> bool:
        """True if there is an edit history state available to undo."""
        return self.history_manager.can_undo if hasattr(self, "history_manager") else False

    @property
    def can_redo(self) -> bool:
        """True if there is an undone edit state available to redo."""
        return self.history_manager.can_redo if hasattr(self, "history_manager") else False

    def update_undo_redo_actions(self):
        """Update enabled states and tooltips for Undo and Redo actions and buttons."""
        if not hasattr(self, "history_manager"):
            return

        can_undo = self.history_manager.can_undo
        can_redo = self.history_manager.can_redo

        undo_desc = self.history_manager.undo_description
        redo_desc = self.history_manager.redo_description

        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(can_undo)
            self.undo_action.setText(f"&Undo {undo_desc}" if undo_desc else "&Undo")

        if hasattr(self, "redo_action"):
            self.redo_action.setEnabled(can_redo)
            self.redo_action.setText(f"&Redo {redo_desc}" if redo_desc else "&Redo")

        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(can_undo)
            self.btn_undo.setToolTip(f"Undo {undo_desc} (Ctrl+Z)" if undo_desc else "Undo (Ctrl+Z)")

        if hasattr(self, "btn_redo"):
            self.btn_redo.setEnabled(can_redo)
            self.btn_redo.setToolTip(f"Redo {redo_desc} (Ctrl+Y)" if redo_desc else "Redo (Ctrl+Y)")

    def undo(self) -> bool:
        """Undo the last configuration edit and safely rebuild the simulation."""
        focused = QApplication.focusWidget() or (self.focusWidget() if hasattr(self, "focusWidget") else None)
        if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QSpinBox)):
            return False

        if not hasattr(self, "history_manager") or not self.history_manager.can_undo:
            return False

        self.pause_simulation()
        result = self.history_manager.undo()
        if result is None:
            return False

        restored_scenario, action_desc = result
        backup_scenario = copy.deepcopy(self.scenario_data)
        self._is_restoring_history = True
        try:
            self.scenario_data = restored_scenario
            self.canvas.scenario_data = self.scenario_data
            self.on_network_modified()
            self.set_dirty(True)
            self.status_label.setText(f"Undid: {action_desc}" if action_desc else "Undid last edit")
        except Exception as exc:
            # Revert the history manager stack state
            if self.history_manager.redo_stack:
                self.history_manager.undo_stack.append(self.history_manager.redo_stack.pop())
            self.scenario_data = backup_scenario
            self.canvas.scenario_data = self.scenario_data
            try:
                self.on_network_modified()
            except Exception:
                pass
            QMessageBox.critical(self, "Undo Failed", f"Failed to restore previous state:\n{exc}")
            return False
        finally:
            self._is_restoring_history = False

        self.update_undo_redo_actions()
        return True

    def redo(self) -> bool:
        """Redo the last undone configuration edit and safely rebuild the simulation."""
        focused = QApplication.focusWidget() or (self.focusWidget() if hasattr(self, "focusWidget") else None)
        if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QSpinBox)):
            return False

        if not hasattr(self, "history_manager") or not self.history_manager.can_redo:
            return False

        self.pause_simulation()
        result = self.history_manager.redo()
        if result is None:
            return False

        restored_scenario, action_desc = result
        backup_scenario = copy.deepcopy(self.scenario_data)
        self._is_restoring_history = True
        try:
            self.scenario_data = restored_scenario
            self.canvas.scenario_data = self.scenario_data
            self.on_network_modified()
            self.set_dirty(True)
            self.status_label.setText(f"Redid: {action_desc}" if action_desc else "Redid last edit")
        except Exception as exc:
            # Revert history manager stack: pop from undo_stack and push back to redo_stack
            if self.history_manager.undo_stack:
                self.history_manager.redo_stack.append(self.history_manager.undo_stack.pop())
            self.scenario_data = backup_scenario
            self.canvas.scenario_data = self.scenario_data
            try:
                self.on_network_modified()
            except Exception:
                pass
            QMessageBox.critical(self, "Redo Failed", f"Failed to restore state:\n{exc}")
            return False
        finally:
            self._is_restoring_history = False

        self.update_undo_redo_actions()
        return True


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = Workbench()
    window.show()
    try:
        return app.exec()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
