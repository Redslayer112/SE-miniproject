"""TMS-Sim desktop workbench with the scenario-driven simulation engine."""

import json
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont
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
)

from tms_sim.network import NetworkBlockedError, NetworkFormatError
from tms_sim.signal import SignalPlan, SignalPlanBlockedError
from tms_sim.signal.serialization import plan_from_dict
from tms_sim.sim.demand import DemandError
from tms_sim.sim.scenario import load_scenario
from tms_sim.sim.serialization import ScenarioFormatError, load_scenario_document

logger = logging.getLogger(__name__)


class RoadCanvas(QWidget):
    """Draw the loaded scenario network, live traffic signals, and moving vehicles.

    Supports interactive mouse-wheel zooming around the cursor and click-and-drag panning.
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
    # Signal indication colors
    COLOR_GREEN = QColor("#22c55e")
    COLOR_YELLOW = QColor("#eab308")
    COLOR_RED = QColor("#ef4444")
    COLOR_UNSIGNALIZED = QColor("#94a3b8")

    MIN_ZOOM = 0.2
    MAX_ZOOM = 5.0
    DEFAULT_ZOOM = 1.0

    def __init__(self):
        super().__init__()
        self.setMinimumSize(500, 350)
        self.engine = None
        self.scenario_data = {}
        self.signal_plans: dict[str, SignalPlan] = {}
        self.zoom_level: float = self.DEFAULT_ZOOM
        self.pan_offset: QPointF = QPointF(0.0, 0.0)
        self._is_panning: bool = False
        self._pan_start: QPointF = QPointF()
        self.setStyleSheet("background: #e9eee9;")
        self.setMouseTracking(True)

    def set_scenario(self, engine, scenario_data):
        """Bind a simulation engine and scenario document, re-parsing signal plans and resetting view."""
        self.engine = engine
        self.scenario_data = scenario_data or {}
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
        self.reset_view()
        self.update()

    def reset_view(self):
        """Reset canvas zoom level and pan offset to default centered view."""
        self.zoom_level = self.DEFAULT_ZOOM
        self.pan_offset = QPointF(0.0, 0.0)
        self.update()

    def set_zoom(self, zoom: float):
        """Directly set zoom level clamped to allowed range."""
        self.zoom_level = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(zoom)))
        self.update()

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
        """Begin mouse-drag panning when the left mouse button is pressed."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle panning displacement while dragging."""
        if self._is_panning:
            delta = event.position() - self._pan_start
            self.pan_offset += delta
            self._pan_start = event.position()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """End mouse-drag panning."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click resets zoom and pan to 100% centered view."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_view()
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.BACKGROUND)

        network = self.scenario_data.get("network", {})
        intersections = network.get("intersections", [])
        segments = network.get("segments", [])
        turning_movements = network.get("turning_movements", [])
        if not intersections or not segments:
            painter.setPen(QColor("#344054"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "No network data found in the loaded scenario")
            painter.end()
            return

        width = max(1, self.width())
        height = max(1, self.height())
        margin = 55

        positions = {}
        raw_positions = []
        for intersection in intersections:
            pos = intersection.get("position")
            if isinstance(pos, list) and len(pos) >= 2:
                x, y = float(pos[0]), float(pos[1])
            else:
                x, y = float(len(raw_positions)), 0.0
            positions[intersection["id"]] = (x, y)
            raw_positions.append((x, y))

        xs = [p[0] for p in raw_positions]
        ys = [p[1] for p in raw_positions]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 1.0)
        span_y = max(max_y - min_y, 1.0)
        draw_w = max(1, width - 2 * margin)
        draw_h = max(1, height - 2 * margin)
        center = QPointF(width / 2.0, height / 2.0)

        # Base screen coordinate transformation combined with zoom and pan
        def transform_point(point):
            x, y = point
            base_sx = margin + ((x - min_x) / span_x) * draw_w
            base_sy = height / 2.0 - ((y - min_y) / span_y) * min(draw_h, 120.0)
            base_pt = QPointF(base_sx, base_sy)
            return center + self.pan_offset + (base_pt - center) * self.zoom_level

        screen_positions = {
            node_id: transform_point(pos) for node_id, pos in positions.items()
        }

        sim_time = self.engine.time if self.engine is not None else 0.0

        # Draw road segments
        for segment in segments:
            start = screen_positions.get(segment.get("from"))
            end = screen_positions.get(segment.get("to"))
            if start is None or end is None:
                continue
            lanes = max(1, int(segment.get("lane_count", 1)))
            road_width = max(18, min(64, int((lanes * 18) * min(2.5, max(0.6, self.zoom_level)))))
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
                painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
                painter.drawText(midpoint + QPointF(6, -road_width / 2.0 - 8),
                                 f'{segment.get("id", "Road")}')

        # Draw approach stop lines and approach signal indicators for signalized intersections
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

        # Draw intersection nodes and control status
        for intersection in intersections:
            point = screen_positions.get(intersection["id"])
            if point is None:
                continue
            node_r = max(9.0, min(20.0, 12.0 * min(1.8, max(0.7, self.zoom_level))))
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor("#64748b"))
            painter.drawEllipse(point, node_r, node_r)

            if self.zoom_level >= 0.4:
                painter.setPen(QColor("#1f2937"))
                painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
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

        # Draw live simulation vehicles
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
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.drawText(14, 24, "SCENARIO NETWORK  /  LIVE VEHICLES & SIGNALS")

        zoom_text = f"Zoom: {int(self.zoom_level * 100)}%"
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Normal))
        painter.setPen(QColor("#64748b"))
        hint_text = f"{zoom_text}  •  Scroll: Zoom  •  Drag: Pan"
        painter.drawText(width - 250, 24, hint_text)

        # Bottom-left Signal Status Legend
        legend_w, legend_h = 285, 26
        lx = 14
        ly = height - legend_h - 12
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.drawRoundedRect(lx, ly, legend_w, legend_h, 5, 5)

        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
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

        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.advance_simulation)

        self.status_label = QLabel("Ready")
        self.clock_label = QLabel("Simulation time: 0.0 s")
        self.speed_box = QComboBox()
        self.speed_box.addItems(["0.5x", "1x", "2x", "4x"])
        self.speed_box.setCurrentText("1x")

        self.build_ui()
        self.update_metrics()

    def build_ui(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #f6f8fb;
                color: #1f2937;
                font-family: 'Segoe UI';
                font-size: 13px;
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
            QPushButton#primary {
                background: #2563eb;
                color: white;
                border: none;
            }
            QLabel#heading {
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#muted { color: #667085; }
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

        # View menu
        view_menu = menubar.addMenu("&View")
        reset_view_action = view_menu.addAction("&Reset Canvas View")
        reset_view_action.setShortcut("Ctrl+R")
        reset_view_action.setStatusTip("Reset canvas zoom and pan to 100%")
        reset_view_action.triggered.connect(self.canvas.reset_view)

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

        toolbox = self.panel("TOOLBOX")
        tools = toolbox.layout()
        for tool_name in [
            "Select tool", "Add intersection", "Draw road",
            "Signal settings", "Traffic demand"
        ]:
            button = QPushButton(tool_name)
            # Editing tools remain disabled until their handlers are implemented.
            button.setEnabled(tool_name == "Select tool")
            tools.addWidget(button)
        tools.addStretch()
        toolbox.setMinimumWidth(170)
        splitter.addWidget(toolbox)

        network_panel = self.panel("2D ROAD NETWORK")
        network_panel.layout().addWidget(self.canvas)
        splitter.addWidget(network_panel)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        props = self.panel("PROPERTIES")
        pl = props.layout()
        lbl_scenario = QLabel("Loaded scenario")
        lbl_scenario.setObjectName("muted")
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
        for label in (
            lbl_scenario,
            self.scenario_name_label,
            lbl_file,
            self.scenario_file_label,
            self.intersections_label,
            self.segments_label,
            self.control_label,
        ):
            pl.addWidget(label)
        right_layout.addWidget(props)

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
        right.setMinimumWidth(220)
        splitter.addWidget(right)
        splitter.setSizes([180, 800, 260])
        outer.addWidget(splitter, 1)

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

    def start_simulation(self):
        if self.engine.finished:
            self.status_label.setText("Simulation finished — press Reset to run again")
            return
        self.engine.start()
        self.timer.start()
        self.status_label.setText("Simulation running")

    def pause_simulation(self):
        self.engine.pause()
        self.status_label.setText("Simulation paused")

    def step_simulation(self):
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
        self.engine.reset()
        self.canvas.update()
        self.update_metrics()
        self.status_label.setText("Simulation reset")

    def change_speed(self, value):
        if self.engine is not None:
            self.engine.set_speed(float(value.replace("x", "")))

    def advance_simulation(self):
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
        generated = len(self.engine.events)
        # Each vehicle emits a spawn event once it enters the network.
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
        """Load and validate a scenario from path.

        Preserves previously loaded scenario if loading or validation fails.
        Returns True on success, False on failure.
        """
        path = Path(path)
        try:
            # 1. Structural and schema validation using project's serialization
            new_data = load_scenario_document(path)
            # 2. Simulation engine initialization and domain validation
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

        # Loading and validation succeeded: stop simulation timer
        self.timer.stop()

        self.scenario_path = path
        self.scenario_data = new_data
        self.engine = new_engine

        # Re-apply selected speed to the newly loaded engine
        self.change_speed(self.speed_box.currentText())

        # Update canvas
        self.canvas.set_scenario(self.engine, self.scenario_data)

        # Update metrics and scenario info labels
        self.update_metrics()

        self.status_label.setText(f"Scenario '{self.scenario_path.name}' loaded successfully")
        return True

    def _handle_load_error(self, message: str, status_msg: str):
        self.status_label.setText(f"Failed to load scenario: {status_msg}")
        QMessageBox.critical(self, "Unable to Load Scenario", message)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = Workbench()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
