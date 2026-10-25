"""Live performance charts and timeline widgets for TMS-Sim workbench (Step 5B).

Provides:
- VehicleCountsChart: Cumulative vehicle counts over simulated time (Generated, Entered, Completed, In Network).
- TravelTimeChart: Completed-trip travel time observations and running mean over simulated time.
- SimulationTimelineWidget: Progress bar and timeline summary.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QFrame, QLabel, QTabWidget, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from tms_sim.reporting.history import SimulationHistoryTracker


def safe_font(family: str = "Segoe UI", point_size: int = 9, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Return a QFont with a guaranteed positive integer point size, avoiding Qt warnings."""
    valid_size = int(point_size) if point_size and int(point_size) > 0 else 9
    font = QFont(family, valid_size, weight)
    if font.pointSize() <= 0:
        font.setPointSize(valid_size)
    return font


class VehicleCountsChart(QWidget):
    """Chart A: Plots vehicle count series against simulation time using QPainter."""

    def __init__(self, history_tracker: SimulationHistoryTracker, duration: float = 600.0, parent: QWidget | None = None):
        super().__init__(parent)
        self.history_tracker = history_tracker
        self.duration = max(float(duration), 1.0)
        self.setMinimumSize(240, 180)
        self.setFont(safe_font("Segoe UI", 8))

    def set_duration(self, duration: float) -> None:
        self.duration = max(float(duration), 1.0)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        w, h = rect.width(), rect.height()

        # Background card
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 6, 6)

        # Plot margins
        pad_left, pad_right = 38, 14
        pad_top, pad_bottom = 28, 26
        plot_w = w - pad_left - pad_right
        plot_h = h - pad_top - pad_bottom

        if plot_w <= 20 or plot_h <= 20:
            return

        samples = self.history_tracker.samples

        # Determine axes bounds
        max_time = self.duration
        if samples and samples[-1].simulated_time > max_time:
            max_time = samples[-1].simulated_time
        max_time = max(max_time, 1.0)

        max_count = 5
        for s in samples:
            max_count = max(max_count, s.vehicles_generated, s.vehicles_entered, s.vehicles_completed, s.vehicles_in_network)
        # Round max_count up to next multiple of 5 or 10
        y_max = math.ceil((max_count * 1.1) / 5.0) * 5

        # Draw grid lines & Y labels
        painter.setFont(safe_font("Segoe UI", 7))
        y_ticks = 4
        for i in range(y_ticks + 1):
            val = int(i * y_max / y_ticks)
            py = pad_top + plot_h - (i * plot_h / y_ticks)
            # Grid line
            painter.setPen(QPen(QColor("#f1f5f9"), 1, Qt.PenStyle.SolidLine))
            painter.drawLine(QPointF(pad_left, py), QPointF(pad_left + plot_w, py))
            # Label
            painter.setPen(QPen(QColor("#64748b")))
            painter.drawText(QRectF(2, py - 7, pad_left - 6, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(val))

        # Draw X grid lines & labels
        x_ticks = 4
        for i in range(x_ticks + 1):
            t_val = i * max_time / x_ticks
            px = pad_left + (i * plot_w / x_ticks)
            painter.setPen(QPen(QColor("#f1f5f9"), 1, Qt.PenStyle.SolidLine))
            painter.drawLine(QPointF(px, pad_top), QPointF(px, pad_top + plot_h))
            painter.setPen(QPen(QColor("#64748b")))
            t_str = f"{int(t_val)}s" if t_val >= 10 else f"{t_val:.0f}s"
            painter.drawText(QRectF(px - 18, pad_top + plot_h + 4, 36, 16), Qt.AlignmentFlag.AlignCenter, t_str)

        # Draw Axes
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawLine(QPointF(pad_left, pad_top), QPointF(pad_left, pad_top + plot_h))
        painter.drawLine(QPointF(pad_left, pad_top + plot_h), QPointF(pad_left + plot_w, pad_top + plot_h))

        # Draw Legend at top
        legend_items = [
            ("Generated", QColor("#2563eb")),
            ("Entered", QColor("#059669")),
            ("In Net", QColor("#d97706")),
            ("Done", QColor("#7c3aed")),
        ]
        leg_x = pad_left
        painter.setFont(safe_font("Segoe UI", 7, QFont.Weight.Bold))
        for name, color in legend_items:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(QRectF(leg_x, 8, 8, 8), 2, 2)
            painter.setPen(QPen(QColor("#475467")))
            painter.drawText(QRectF(leg_x + 12, 5, 54, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
            leg_x += 58

        if not samples:
            painter.setFont(safe_font("Segoe UI", 8))
            painter.setPen(QPen(QColor("#94a3b8")))
            painter.drawText(QRectF(pad_left, pad_top, plot_w, plot_h), Qt.AlignmentFlag.AlignCenter, "Awaiting simulation run...")
            return

        # Helper to map (t, val) to canvas point
        def to_point(t: float, val: int) -> QPointF:
            px = pad_left + (t / max_time) * plot_w
            py = pad_top + plot_h - (val / y_max) * plot_h
            return QPointF(px, py)

        # Plot 4 series
        series_data = [
            ([to_point(s.simulated_time, s.vehicles_generated) for s in samples], QColor("#2563eb")),
            ([to_point(s.simulated_time, s.vehicles_entered) for s in samples], QColor("#059669")),
            ([to_point(s.simulated_time, s.vehicles_in_network) for s in samples], QColor("#d97706")),
            ([to_point(s.simulated_time, s.vehicles_completed) for s in samples], QColor("#7c3aed")),
        ]

        for points, color in series_data:
            if len(points) == 1:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(color))
                painter.drawEllipse(points[0], 3, 3)
            elif len(points) > 1:
                poly = QPolygonF(points)
                painter.setPen(QPen(color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolyline(poly)
                # Draw small endpoint dot
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(color))
                painter.drawEllipse(points[-1], 3, 3)


class TravelTimeChart(QWidget):
    """Chart B: Plots completed-trip travel time observations against completion time."""

    def __init__(self, history_tracker: SimulationHistoryTracker, duration: float = 600.0, parent: QWidget | None = None):
        super().__init__(parent)
        self.history_tracker = history_tracker
        self.duration = max(float(duration), 1.0)
        self.setMinimumSize(240, 180)
        self.setFont(safe_font("Segoe UI", 8))

    def set_duration(self, duration: float) -> None:
        self.duration = max(float(duration), 1.0)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        w, h = rect.width(), rect.height()

        # Background card
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 6, 6)

        pad_left, pad_right = 38, 14
        pad_top, pad_bottom = 28, 26
        plot_w = w - pad_left - pad_right
        plot_h = h - pad_top - pad_bottom

        if plot_w <= 20 or plot_h <= 20:
            return

        trips = self.history_tracker.completed_trips

        # Empty state check
        if not trips:
            painter.setPen(QPen(QColor("#cbd5e1"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor("#fafafa")))
            painter.drawRoundedRect(QRectF(pad_left, pad_top, plot_w, plot_h), 4, 4)

            painter.setFont(safe_font("Segoe UI", 8, QFont.Weight.Bold))
            painter.setPen(QPen(QColor("#64748b")))
            painter.drawText(QRectF(pad_left + 10, pad_top + 20, plot_w - 20, 20), Qt.AlignmentFlag.AlignCenter, "No completed trips yet")
            painter.setFont(safe_font("Segoe UI", 7.5))
            painter.setPen(QPen(QColor("#94a3b8")))
            painter.drawText(QRectF(pad_left + 10, pad_top + 42, plot_w - 20, 36), Qt.AlignmentFlag.AlignCenter, "Travel times will be plotted as vehicles\ncomplete their routes")
            return

        # Determine axes ranges
        max_time = self.duration
        if trips[-1].completion_time > max_time:
            max_time = trips[-1].completion_time
        max_time = max(max_time, 1.0)

        max_tt = max(t.travel_time for t in trips)
        y_max = math.ceil((max_tt * 1.25) / 5.0) * 5.0
        y_max = max(y_max, 10.0)

        # Y Grid & Labels
        painter.setFont(safe_font("Segoe UI", 7))
        y_ticks = 4
        for i in range(y_ticks + 1):
            val = i * y_max / y_ticks
            py = pad_top + plot_h - (i * plot_h / y_ticks)
            painter.setPen(QPen(QColor("#f1f5f9"), 1, Qt.PenStyle.SolidLine))
            painter.drawLine(QPointF(pad_left, py), QPointF(pad_left + plot_w, py))
            painter.setPen(QPen(QColor("#64748b")))
            painter.drawText(QRectF(2, py - 7, pad_left - 6, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{val:.0f}s")

        # X Grid & Labels
        x_ticks = 4
        for i in range(x_ticks + 1):
            t_val = i * max_time / x_ticks
            px = pad_left + (i * plot_w / x_ticks)
            painter.setPen(QPen(QColor("#f1f5f9"), 1, Qt.PenStyle.SolidLine))
            painter.drawLine(QPointF(px, pad_top), QPointF(px, pad_top + plot_h))
            painter.setPen(QPen(QColor("#64748b")))
            t_str = f"{int(t_val)}s" if t_val >= 10 else f"{t_val:.0f}s"
            painter.drawText(QRectF(px - 18, pad_top + plot_h + 4, 36, 16), Qt.AlignmentFlag.AlignCenter, t_str)

        # Axes
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawLine(QPointF(pad_left, pad_top), QPointF(pad_left, pad_top + plot_h))
        painter.drawLine(QPointF(pad_left, pad_top + plot_h), QPointF(pad_left + plot_w, pad_top + plot_h))

        # Legend at top
        painter.setFont(safe_font("Segoe UI", 7, QFont.Weight.Bold))
        # Trip dot legend
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#0284c7")))
        painter.drawEllipse(QPointF(pad_left + 4, 11), 3.5, 3.5)
        painter.setPen(QPen(QColor("#475467")))
        painter.drawText(QRectF(pad_left + 12, 5, 80, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Completed Trip")

        # Running mean line legend
        painter.setPen(QPen(QColor("#0369a1"), 2, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(pad_left + 98, 11), QPointF(pad_left + 114, 11))
        painter.setPen(QPen(QColor("#475467")))
        painter.drawText(QRectF(pad_left + 118, 5, 90, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Running Mean")

        # Plot individual completed trips as points and compute running mean
        running_sum = 0.0
        mean_points = []

        for idx, tr in enumerate(trips, start=1):
            px = pad_left + (tr.completion_time / max_time) * plot_w
            py = pad_top + plot_h - (tr.travel_time / y_max) * plot_h

            running_sum += tr.travel_time
            mean_val = running_sum / idx
            mean_py = pad_top + plot_h - (mean_val / y_max) * plot_h
            mean_points.append(QPointF(px, mean_py))

            # Point observation
            painter.setPen(QPen(QColor("#0284c7"), 1.2))
            painter.setBrush(QBrush(QColor("#e0f2fe")))
            painter.drawEllipse(QPointF(px, py), 3.5, 3.5)

        # Draw running mean curve
        if len(mean_points) > 1:
            poly = QPolygonF(mean_points)
            painter.setPen(QPen(QColor("#0369a1"), 2, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(poly)


class SimulationTimelineWidget(QWidget):
    """Chart C: Compact visual timeline and progress indicator toward configured duration."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.simulated_time = 0.0
        self.duration = 600.0
        self.status = "Ready"
        self.setMinimumHeight(44)
        self.setMaximumHeight(54)
        self.setFont(safe_font("Segoe UI", 8))

    def update_state(self, simulated_time: float, duration: float, status: str) -> None:
        self.simulated_time = max(0.0, float(simulated_time))
        self.duration = max(1.0, float(duration))
        self.status = str(status)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        w, h = rect.width(), rect.height()

        # Background card
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        painter.setBrush(QBrush(QColor("#f8fafc")))
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 6, 6)

        # Progress calculation
        pct = min(1.0, self.simulated_time / self.duration) if self.duration > 0 else 0.0

        # Header Text
        painter.setFont(safe_font("Segoe UI", 7.5, QFont.Weight.Bold))
        painter.setPen(QPen(QColor("#475467")))
        painter.drawText(QRectF(8, 4, 120, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Timeline Progress")

        progress_str = f"{self.simulated_time:.1f} s / {self.duration:.1f} s ({pct * 100:.1f}%)"
        painter.setFont(safe_font("Segoe UI", 7.5))
        painter.setPen(QPen(QColor("#64748b")))
        painter.drawText(QRectF(w - 150, 4, 142, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, progress_str)

        # Progress bar track
        bar_x, bar_y = 8, 20
        bar_w = w - 16
        bar_h = 8

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#e2e8f0")))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 4, 4)

        # Filled progress portion
        if pct > 0:
            fill_w = max(6.0, bar_w * pct)
            fill_color = QColor("#10b981") if self.status == "Completed" else QColor("#2563eb")
            painter.setBrush(QBrush(fill_color))
            painter.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 4, 4)

        # Tick labels below bar
        painter.setFont(safe_font("Segoe UI", 6.5))
        painter.setPen(QPen(QColor("#94a3b8")))
        painter.drawText(QRectF(bar_x, bar_y + bar_h + 1, 30, 12), Qt.AlignmentFlag.AlignLeft, "0s")
        painter.drawText(QRectF(bar_x + bar_w / 2 - 20, bar_y + bar_h + 1, 40, 12), Qt.AlignmentFlag.AlignCenter, f"{self.duration / 2:.0f}s")
        painter.drawText(QRectF(bar_x + bar_w - 40, bar_y + bar_h + 1, 40, 12), Qt.AlignmentFlag.AlignRight, f"{self.duration:.0f}s")


class LivePerformancePanel(QFrame):
    """Container widget housing Timeline (Chart C) and Tabbed Charts (Chart A & Chart B)."""

    def __init__(self, history_tracker: SimulationHistoryTracker, duration: float = 600.0, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Section Heading
        heading = QLabel("LIVE PERFORMANCE")
        heading.setStyleSheet("font-weight: 700; color: #475467; letter-spacing: 1px;")
        layout.addWidget(heading)

        # Chart C: Timeline and progress summary
        self.timeline_widget = SimulationTimelineWidget(self)
        layout.addWidget(self.timeline_widget)

        # Tab widget for Chart A & Chart B
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e2e8f0;
                background: white;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #f1f5f9;
                color: #475467;
                padding: 4px 10px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 8pt;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #2563eb;
                font-weight: 700;
                border-bottom: 2px solid #2563eb;
            }
        """)

        # Chart A: Vehicle counts
        self.counts_chart = VehicleCountsChart(history_tracker, duration, self)
        self.tab_widget.addTab(self.counts_chart, "📈 Counts Over Time")

        # Chart B: Travel times
        self.travel_time_chart = TravelTimeChart(history_tracker, duration, self)
        self.tab_widget.addTab(self.travel_time_chart, "⏱ Travel Time")

        layout.addWidget(self.tab_widget)
