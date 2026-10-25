"""TMS-Sim desktop workbench with interactive network editing and simulation engine."""

import copy
import json
import logging
import math
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QKeySequence
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
from tms_sim.signal import SignalPlan, SignalPlanBlockedError
from tms_sim.signal.serialization import plan_from_dict
from tms_sim.sim.demand import DemandError
from tms_sim.sim.scenario import build_engine, load_scenario
from tms_sim.sim.serialization import ScenarioFormatError, load_scenario_document

logger = logging.getLogger(__name__)


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
            raw_plans = self.scenario_data.get("signal_plans") or (
                [self.scenario_data["signal_plan"]] if self.scenario_data.get("signal_plan") else []
            )
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
            if self.scenario_data.get("signal_plan", {}).get("intersection_id") == iid:
                self.scenario_data.pop("signal_plan", None)
            if self.scenario_data.get("signal_plans"):
                self.scenario_data["signal_plans"] = [
                    p for p in self.scenario_data["signal_plans"] if p.get("intersection_id") != iid
                ]
            self.set_selection(None, None)
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
            raw_plans = self.scenario_data.get("signal_plans") or (
                [self.scenario_data["signal_plan"]] if self.scenario_data.get("signal_plan") else []
            )
            for plan_dict in raw_plans:
                for ph in plan_dict.get("phases", []):
                    ph["movement_ids"] = [mid for mid in ph.get("movement_ids", []) if mid not in removed_moves]

            self.set_selection(None, None)
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

        self.setFont(safe_font("Segoe UI", 10))
        self.build_ui()
        self.update_metrics()
        self.validate_current_network()

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
        file_menu.addSeparator()
        exit_action = file_menu.addAction("E&xit")
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
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

        self.reset_view_button = QPushButton("⟲ Reset View")
        self.reset_view_button.setToolTip("Reset canvas zoom and pan (Ctrl+R or double-click canvas)")
        self.reset_view_button.clicked.connect(self.canvas.reset_view)

        self.open_button = QPushButton("Open Scenario…")
        self.open_button.setToolTip("Open a JSON scenario file (Ctrl+O)")
        self.open_button.clicked.connect(self.open_scenario_dialog)

        header.addWidget(title)
        header.addSpacing(8)
        header.addWidget(subtitle)
        header.addStretch()
        header.addWidget(self.reset_view_button)
        header.addWidget(self.open_button)
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

        # LIVE METRICS panel
        metrics = self.panel("LIVE METRICS")
        ml = metrics.layout()
        self.metric_time = QLabel("0.0 s")
        self.metric_time.setObjectName("heading")
        self.vehicle_count_label = QLabel("0")
        self.completed_label = QLabel("0")
        self.generated_label = QLabel("0")
        self.remaining_label = QLabel("0")
        ml.addWidget(QLabel("Simulation time"))
        ml.addWidget(self.metric_time)
        ml.addWidget(QLabel("Vehicles currently in network"))
        ml.addWidget(self.vehicle_count_label)
        ml.addWidget(QLabel("Vehicles completed"))
        ml.addWidget(self.completed_label)
        ml.addWidget(QLabel("Vehicles generated"))
        ml.addWidget(self.generated_label)
        ml.addWidget(QLabel("Vehicles waiting to enter"))
        ml.addWidget(self.remaining_label)
        right_layout.addWidget(metrics)
        right_layout.addStretch()
        right.setMinimumWidth(260)
        splitter.addWidget(right)
        splitter.setSizes([180, 780, 280])
        outer.addWidget(splitter, 1)

        # Simulation controls
        controls = self.panel("SIMULATION CONTROLS")
        control_layout = QHBoxLayout()
        controls.layout().addLayout(control_layout)

        start = QPushButton("▶  Start")
        start.setObjectName("primary")
        pause = QPushButton("Ⅱ  Pause")
        step = QPushButton("Step")
        reset = QPushButton("Reset")

        start.clicked.connect(self.start_simulation)
        pause.clicked.connect(self.pause_simulation)
        step.clicked.connect(self.step_simulation)
        reset.clicked.connect(self.reset_simulation)
        self.speed_box.currentTextChanged.connect(self.change_speed)

        for widget in (start, pause, step, reset):
            control_layout.addWidget(widget)

        control_layout.addSpacing(16)
        control_layout.addWidget(QLabel("Speed"))
        control_layout.addWidget(self.speed_box)
        control_layout.addStretch()
        control_layout.addWidget(self.clock_label)
        outer.addWidget(controls)

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

        self.on_network_modified()
        self.status_label.setText(f"Applied properties to road segment '{sid}'.")

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

    def on_network_modified(self):
        """Synchronize engine, metrics, canvas, and validation whenever network changes."""
        self.timer.stop()
        self.update_metrics()
        self.canvas.reparse_signal_plans()
        val_result = self.validate_current_network()

        # Re-initialize engine if network is valid
        if val_result.is_valid:
            try:
                raw_plans = self.scenario_data.get("signal_plans") or (
                    [self.scenario_data["signal_plan"]] if self.scenario_data.get("signal_plan") else []
                )
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
            except Exception as exc:
                self.status_label.setText(f"Simulation engine paused: {exc}")
        else:
            self.status_label.setText(f"Network has {len(val_result.errors)} validation error(s). Simulation paused.")

        self.canvas.update()

    def start_simulation(self):
        if self.engine is None or self.engine.finished:
            self.status_label.setText("Simulation finished or not ready — press Reset to run again")
            return
        self.engine.start()
        self.timer.start()
        self.status_label.setText("Simulation running")

    def pause_simulation(self):
        if self.engine is not None:
            self.engine.pause()
        self.status_label.setText("Simulation paused")

    def step_simulation(self):
        if self.engine is not None:
            self.engine.pause()
            self.engine.step()
            self.canvas.update()
            self.update_metrics()
            self.status_label.setText(
                "Simulation completed" if self.engine.finished
                else "Advanced one simulation step"
            )

    def reset_simulation(self):
        self.timer.stop()
        if self.engine is not None:
            self.engine.reset()
        self.canvas.update()
        self.update_metrics()
        self.status_label.setText("Simulation reset")

    def change_speed(self, value):
        if self.engine is not None:
            self.engine.set_speed(float(value.replace("x", "")))

    def advance_simulation(self):
        if self.engine is not None:
            self.engine.advance(self.timer.interval() / 1000.0)
            self.canvas.update()
            self.update_metrics()
            if self.engine.finished:
                self.timer.stop()
                self.status_label.setText("Simulation completed")

    def update_metrics(self):
        if self.engine is None:
            return
        value = self.engine.time
        self.clock_label.setText(f"Simulation time: {value:.1f} s")
        self.metric_time.setText(f"{value:.1f} s")
        self.vehicle_count_label.setText(str(len(self.engine.cars)))
        self.completed_label.setText(str(len(self.engine.exited)))
        entered = sum(1 for event in self.engine.events if event[2] == "spawn")
        self.generated_label.setText(str(entered))
        waiting = max(0, len(self.engine.vehicles) - entered)
        self.remaining_label.setText(str(waiting))

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

    def open_scenario_dialog(self):
        """Prompt user with file dialog to open and load a scenario JSON file."""
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
        self.update_metrics()
        self.validate_current_network()

        self.status_label.setText(f"Scenario '{self.scenario_path.name}' loaded successfully")
        return True

    def _handle_load_error(self, message: str, status_msg: str):
        self.status_label.setText(f"Failed to load scenario: {status_msg}")
        QMessageBox.critical(self, "Unable to Load Scenario", message)


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
