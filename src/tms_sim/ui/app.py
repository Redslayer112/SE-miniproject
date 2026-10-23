"""TMS-Sim desktop workbench with the scenario-driven simulation engine."""

import json
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
)

from tms_sim.sim.scenario import load_scenario


class RoadCanvas(QWidget):
    """Draw the loaded scenario network and the actual cars in its engine."""

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

    def __init__(self):
        super().__init__()
        self.setMinimumSize(500, 350)
        self.engine = None
        self.scenario_data = {}
        self.setStyleSheet("background: #e9eee9;")

    def set_scenario(self, engine, scenario_data):
        self.engine = engine
        self.scenario_data = scenario_data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.BACKGROUND)

        network = self.scenario_data.get("network", {})
        intersections = network.get("intersections", [])
        segments = network.get("segments", [])
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

        # Preserve relative network layout while centering networks that are
        # effectively one-dimensional (such as the supplied two-node scenario).
        def screen_point(point):
            x, y = point
            sx = margin + ((x - min_x) / span_x) * draw_w
            sy = height / 2 - ((y - min_y) / span_y) * min(draw_h, 120)
            return QPointF(sx, sy)

        screen_positions = {
            node_id: screen_point(pos) for node_id, pos in positions.items()
        }

        # Draw roads first, then lane centre-lines and endpoint labels.
        for segment in segments:
            start = screen_positions.get(segment.get("from"))
            end = screen_positions.get(segment.get("to"))
            if start is None or end is None:
                continue
            lanes = max(1, int(segment.get("lane_count", 1)))
            road_width = max(22, min(48, lanes * 18))
            painter.setPen(QPen(self.ROAD_EDGE, road_width + 3,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)
            painter.setPen(QPen(self.ROAD_COLOR, road_width,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)
            painter.setPen(QPen(QColor("#f8fafc"), 2, Qt.PenStyle.DashLine))
            painter.drawLine(start, end)

            midpoint = QPointF((start.x() + end.x()) / 2,
                               (start.y() + end.y()) / 2)
            painter.setPen(QColor("#344054"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            painter.drawText(midpoint + QPointF(6, -road_width / 2 - 8),
                             f'{segment.get("id", "Road")}')

        # Draw intersection nodes and their control type.
        for intersection in intersections:
            point = screen_positions.get(intersection["id"])
            if point is None:
                continue
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor("#64748b"))
            painter.drawEllipse(point, 12, 12)
            painter.setPen(QColor("#1f2937"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(point + QPointF(15, -12), intersection["id"])

            control = str(intersection.get("control_type", "uncontrolled")).lower()
            signal_color = QColor("#22c55e") if control == "signalized" else QColor("#94a3b8")
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.setBrush(signal_color)
            painter.drawEllipse(point + QPointF(0, 18), 6, 6)

        # Draw current engine cars using each car's actual route/leg/position.
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

                painter.setPen(QPen(QColor("#ffffff"), 1))
                painter.setBrush(self.VEHICLE_COLORS[index % len(self.VEHICLE_COLORS)])
                painter.drawRoundedRect(int(x - 8), int(y - 6), 16, 12, 3, 3)

        painter.setPen(QColor("#344054"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.drawText(14, 24, "SCENARIO NETWORK  /  LIVE VEHICLES")
        painter.end()


class Workbench(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TMS-Sim | Traffic Management System")
        self.resize(1366, 768)

        self.scenario_path = (
            Path(__file__).resolve().parents[3]
            / "tests"
            / "data"
            / "scenario"
            / "small_valid_scenario.json"
        )

        self.scenario_data = {}
        self.engine = None
        try:
            self.scenario_data = json.loads(
                self.scenario_path.read_text(encoding="utf-8")
            )
            self.engine = load_scenario(self.scenario_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Unable to load scenario",
                f"Could not load the sample scenario:\n{self.scenario_path}\n\n{exc}",
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

        header = QHBoxLayout()
        title = QLabel("Traffic Management System")
        title.setObjectName("heading")
        subtitle = QLabel("TMS-Sim  /  Desktop Workbench")
        subtitle.setObjectName("muted")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(subtitle)
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
        self.scenario_name_label = QLabel(self.scenario_data.get("name", "Scenario"))
        self.intersections_label = QLabel()
        self.segments_label = QLabel()
        self.control_label = QLabel()
        for label in (
            QLabel("Loaded scenario"),
            self.scenario_name_label,
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


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = Workbench()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
