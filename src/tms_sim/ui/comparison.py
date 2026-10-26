"""Scenario comparison UI view and comparison chart (Step 5F).

Provides:
- ComparisonChartView: Visual side-by-side bar chart of key simulation metrics using QPainter.
- ScenarioComparisonDialog: Resizable, accessible PySide6 dialog for comparing completed simulation runs.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tms_sim.reporting.export import export_comparison_csv, export_comparison_html

from tms_sim.reporting.comparison import (
    ComparisonStatus,
    MetricComparison,
    MetricDirection,
    ScenarioComparison,
    SimulationRunRecord,
    compare_runs,
)

if TYPE_CHECKING:
    from tms_sim.ui.app import Workbench


def safe_font(family: str = "Segoe UI", point_size: int = 9, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Return a QFont with a guaranteed positive integer point size, avoiding Qt font warnings."""
    valid_size = int(point_size) if point_size and int(point_size) > 0 else 9
    font = QFont(family, valid_size, weight)
    if font.pointSize() <= 0:
        font.setPointSize(valid_size)
    return font


class ComparisonChartView(QWidget):
    """Side-by-side bar chart comparing key available metrics between baseline and candidate runs."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.comparison: ScenarioComparison | None = None
        self.setMinimumSize(320, 190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setFont(safe_font("Segoe UI", 8))

    def set_comparison(self, comparison: ScenarioComparison | None) -> None:
        """Update chart with new comparison data."""
        self.comparison = comparison
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

        if not self.comparison:
            painter.setPen(QPen(QColor("#94a3b8")))
            painter.setFont(safe_font("Segoe UI", 9))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No comparison data to display")
            return

        # Header with Legend
        painter.setFont(safe_font("Segoe UI", 8, QFont.Weight.Bold))
        painter.setPen(QPen(QColor("#334155")))
        painter.drawText(14, 20, "KEY METRICS COMPARISON")

        # Legend items
        legend_x = w - 230
        if legend_x > 180:
            # Baseline box
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#3b82f6")))
            painter.drawRect(QRectF(legend_x, 11, 10, 10))
            painter.setPen(QPen(QColor("#475569")))
            painter.setFont(safe_font("Segoe UI", 8))
            painter.drawText(legend_x + 14, 20, "Baseline")

            # Candidate box
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#8b5cf6")))
            painter.drawRect(QRectF(legend_x + 80, 11, 10, 10))
            painter.setPen(QPen(QColor("#475569")))
            painter.drawText(legend_x + 94, 20, "Candidate")

        # Pick key available metrics
        items: list[tuple[str, str, float, float]] = []
        m_travel = self.comparison.get_metric("mean_travel_time")
        if m_travel and m_travel.is_available:
            items.append(("Mean Travel Time", "s", float(m_travel.baseline_value or 0), float(m_travel.candidate_value or 0)))

        m_comp = self.comparison.get_metric("vehicles_completed")
        if m_comp and m_comp.is_available:
            items.append(("Vehicles Completed", "veh", float(m_comp.baseline_value or 0), float(m_comp.candidate_value or 0)))

        m_net = self.comparison.get_metric("vehicles_in_network")
        if m_net and m_net.is_available:
            items.append(("In Network", "veh", float(m_net.baseline_value or 0), float(m_net.candidate_value or 0)))

        if not items:
            painter.setPen(QPen(QColor("#94a3b8")))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No numerical metrics available for comparison")
            return

        # Layout parameters
        pad_left = 20
        pad_right = 20
        pad_top = 42
        pad_bottom = 28
        avail_w = w - pad_left - pad_right
        avail_h = h - pad_top - pad_bottom

        num_groups = len(items)
        group_w = avail_w / num_groups
        bar_w = min(36.0, max(14.0, (group_w - 24.0) / 2.0))

        # Baseline horizontal line
        ground_y = pad_top + avail_h
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawLine(QPointF(pad_left, ground_y), QPointF(w - pad_right, ground_y))

        for idx, (label, unit, b_val, c_val) in enumerate(items):
            group_cx = pad_left + idx * group_w + group_w / 2.0
            max_val = max(b_val, c_val, 1.0) * 1.25

            # Heights
            b_h = min(avail_h - 16.0, (b_val / max_val) * (avail_h - 16.0)) if max_val > 0 else 0
            c_h = min(avail_h - 16.0, (c_val / max_val) * (avail_h - 16.0)) if max_val > 0 else 0

            # Baseline bar
            b_x = group_cx - bar_w - 2
            b_y = ground_y - b_h
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#3b82f6")))
            painter.drawRoundedRect(QRectF(b_x, b_y, bar_w, b_h), 3, 3)

            # Candidate bar
            c_x = group_cx + 2
            c_y = ground_y - c_h
            painter.setBrush(QBrush(QColor("#8b5cf6")))
            painter.drawRoundedRect(QRectF(c_x, c_y, bar_w, c_h), 3, 3)

            # Value labels on top of bars
            painter.setFont(safe_font("Segoe UI", 7, QFont.Weight.Bold))
            painter.setPen(QPen(QColor("#1e293b")))

            b_str = f"{b_val:.1f}" if unit == "s" else f"{int(b_val)}"
            c_str = f"{c_val:.1f}" if unit == "s" else f"{int(c_val)}"

            painter.drawText(
                QRectF(b_x - 6, b_y - 14, bar_w + 12, 12),
                Qt.AlignmentFlag.AlignCenter,
                b_str,
            )
            painter.drawText(
                QRectF(c_x - 6, c_y - 14, bar_w + 12, 12),
                Qt.AlignmentFlag.AlignCenter,
                c_str,
            )

            # Group Category Label below axis
            painter.setFont(safe_font("Segoe UI", 8))
            painter.setPen(QPen(QColor("#475569")))
            painter.drawText(
                QRectF(group_cx - group_w / 2.0, ground_y + 4, group_w, 20),
                Qt.AlignmentFlag.AlignCenter,
                f"{label} ({unit})",
            )


class ScenarioComparisonDialog(QDialog):
    """Accessible, responsive modal dialog for comparing two completed simulation runs."""

    def __init__(self, workbench: Workbench, parent: QWidget | None = None):
        super().__init__(parent or workbench)
        self.workbench = workbench
        self.current_comparison: ScenarioComparison | None = None
        self.setWindowTitle("Simulation Scenario Comparison — TMS-Sim")
        self.resize(840, 620)
        self.setMinimumSize(680, 480)

        self._init_ui()
        self.refresh_runs()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(12)

        # 1. Header bar
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("Simulation Run Comparison")
        lbl_title.setStyleSheet("font-size: 13pt; font-weight: 700; color: #0f172a;")
        lbl_sub = QLabel("Compare performance and efficiency between completed simulation runs.")
        lbl_sub.setStyleSheet("font-size: 9pt; color: #64748b;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header.addLayout(title_box)
        header.addStretch()

        self.btn_capture = QPushButton("📸  Capture Current Run")
        self.btn_capture.setToolTip("Capture the current simulation state if completed")
        self.btn_capture.setStyleSheet(
            "background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 5px; padding: 5px 12px; font-weight: 600;"
        )
        self.btn_capture.clicked.connect(self._on_capture_clicked)
        header.addWidget(self.btn_capture)
        main_layout.addLayout(header)

        # 2. Run selection card
        sel_card = QFrame()
        sel_card.setStyleSheet("background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 4px;")
        sel_layout = QHBoxLayout(sel_card)
        sel_layout.setContentsMargins(12, 8, 12, 8)
        sel_layout.setSpacing(10)

        # Baseline selector
        b_box = QVBoxLayout()
        b_box.setSpacing(3)
        lbl_b = QLabel("Baseline Run (Reference):")
        lbl_b.setStyleSheet("font-weight: 700; color: #1e40af; font-size: 8.5pt;")
        self.combo_baseline = QComboBox()
        self.combo_baseline.setFont(safe_font("Segoe UI", 9))
        self.combo_baseline.currentIndexChanged.connect(self._on_selection_changed)
        b_box.addWidget(lbl_b)
        b_box.addWidget(self.combo_baseline)
        sel_layout.addLayout(b_box, 1)

        # Swap button
        self.btn_swap = QPushButton("⇄  Swap")
        self.btn_swap.setToolTip("Swap baseline and candidate selections")
        self.btn_swap.setStyleSheet("padding: 4px 10px; font-weight: 600;")
        self.btn_swap.clicked.connect(self._on_swap_clicked)
        sel_layout.addWidget(self.btn_swap, 0, Qt.AlignmentFlag.AlignBottom)

        # Candidate selector
        c_box = QVBoxLayout()
        c_box.setSpacing(3)
        lbl_c = QLabel("Candidate Run (Comparison):")
        lbl_c.setStyleSheet("font-weight: 700; color: #6d28d9; font-size: 8.5pt;")
        self.combo_candidate = QComboBox()
        self.combo_candidate.setFont(safe_font("Segoe UI", 9))
        self.combo_candidate.currentIndexChanged.connect(self._on_selection_changed)
        c_box.addWidget(lbl_c)
        c_box.addWidget(self.combo_candidate)
        sel_layout.addLayout(c_box, 1)

        main_layout.addWidget(sel_card)

        # 3. Stacked widget: Page 0 = Empty State; Page 1 = Comparison View
        self.stack = QStackedWidget()

        # --- Empty state page ---
        self.empty_page = QWidget()
        empty_layout = QVBoxLayout(self.empty_page)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(10)

        self.lbl_empty_icon = QLabel("⚖")
        self.lbl_empty_icon.setStyleSheet("font-size: 36pt; color: #94a3b8;")
        self.lbl_empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_empty_title = QLabel("At Least Two Completed Runs Required")
        self.lbl_empty_title.setStyleSheet("font-size: 12pt; font-weight: 700; color: #334155;")
        self.lbl_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_empty_desc = QLabel(
            "To compare scenario configurations, run your simulation to completion (100%), "
            "make an edit to network, demand, or signal timing, and run another simulation to completion.\n\n"
            "Captured runs will appear automatically in the selectors above."
        )
        self.lbl_empty_desc.setStyleSheet("color: #64748b; font-size: 9pt; max-width: 500px;")
        self.lbl_empty_desc.setWordWrap(True)
        self.lbl_empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_layout.addWidget(self.lbl_empty_icon)
        empty_layout.addWidget(self.lbl_empty_title)
        empty_layout.addWidget(self.lbl_empty_desc)
        self.stack.addWidget(self.empty_page)

        # --- Comparison report page ---
        self.report_page = QWidget()
        report_layout = QVBoxLayout(self.report_page)
        report_layout.setContentsMargins(0, 0, 0, 0)
        report_layout.setSpacing(8)

        # Incompatibility / Duration warning banner
        self.warning_frame = QFrame()
        self.warning_frame.setStyleSheet(
            "background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 6px;"
        )
        wf_layout = QHBoxLayout(self.warning_frame)
        wf_layout.setContentsMargins(8, 4, 8, 4)
        self.lbl_warning = QLabel("")
        self.lbl_warning.setStyleSheet("color: #b45309; font-weight: 600; font-size: 8.5pt;")
        self.lbl_warning.setWordWrap(True)
        wf_layout.addWidget(self.lbl_warning)
        self.warning_frame.hide()
        report_layout.addWidget(self.warning_frame)

        # Visual Chart View
        self.chart_view = ComparisonChartView()
        report_layout.addWidget(self.chart_view)

        # Metrics Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Metric",
            "Baseline",
            "Candidate",
            "Abs Change",
            "% Change",
            "Assessment",
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setFont(safe_font("Segoe UI", 9))
        report_layout.addWidget(self.table, 1)

        self.stack.addWidget(self.report_page)
        main_layout.addWidget(self.stack, 1)

        # 4. Footer with Export and Close buttons
        footer = QHBoxLayout()
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 8.5pt;")
        footer.addWidget(self.lbl_status)
        footer.addStretch()

        self.btn_export_csv = QPushButton("📄  Export CSV…")
        self.btn_export_csv.setToolTip("Export the current scenario comparison as a CSV spreadsheet")
        self.btn_export_csv.setStyleSheet(
            "background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 5px; padding: 5px 12px; font-weight: 600;"
        )
        self.btn_export_csv.clicked.connect(lambda checked=False: self.export_csv())
        footer.addWidget(self.btn_export_csv)

        self.btn_export_html = QPushButton("🌐  Export HTML…")
        self.btn_export_html.setToolTip("Export the current scenario comparison as a readable HTML report")
        self.btn_export_html.setStyleSheet(
            "background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 5px; padding: 5px 12px; font-weight: 600;"
        )
        self.btn_export_html.clicked.connect(lambda checked=False: self.export_html())
        footer.addWidget(self.btn_export_html)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        main_layout.addLayout(footer)

    def refresh_runs(self) -> None:
        """Sync dialog run selectors with the workbench's captured runs."""
        runs: list[SimulationRunRecord] = getattr(self.workbench, "captured_runs", [])

        cur_b = self.combo_baseline.currentData()
        cur_c = self.combo_candidate.currentData()

        self.combo_baseline.blockSignals(True)
        self.combo_candidate.blockSignals(True)
        self.combo_baseline.clear()
        self.combo_candidate.clear()

        for idx, run in enumerate(runs):
            display_label = f"#{idx + 1}: {run.label}"
            self.combo_baseline.addItem(display_label, run.run_id)
            self.combo_candidate.addItem(display_label, run.run_id)

        # Set default selections: baseline = run 0, candidate = run 1 (or last)
        if len(runs) >= 2:
            sel_b_idx = 0
            sel_c_idx = len(runs) - 1
            for i, r in enumerate(runs):
                if r.run_id == cur_b:
                    sel_b_idx = i
                if r.run_id == cur_c:
                    sel_c_idx = i
            self.combo_baseline.setCurrentIndex(sel_b_idx)
            self.combo_candidate.setCurrentIndex(sel_c_idx)

        self.combo_baseline.blockSignals(False)
        self.combo_candidate.blockSignals(False)

        self._update_view()

    def select_runs(self, baseline_run_id: str, candidate_run_id: str) -> None:
        """Select specific baseline and candidate runs by run ID."""
        self.refresh_runs()
        idx_b = self.combo_baseline.findData(baseline_run_id)
        idx_c = self.combo_candidate.findData(candidate_run_id)

        self.combo_baseline.blockSignals(True)
        self.combo_candidate.blockSignals(True)
        if idx_b >= 0:
            self.combo_baseline.setCurrentIndex(idx_b)
        if idx_c >= 0:
            self.combo_candidate.setCurrentIndex(idx_c)
        self.combo_baseline.blockSignals(False)
        self.combo_candidate.blockSignals(False)

        self._update_view()

    def _on_selection_changed(self):
        """Update comparison report when user selects different runs."""
        self._update_view()

    def _on_swap_clicked(self):
        """Swap baseline and candidate selections."""
        idx_b = self.combo_baseline.currentIndex()
        idx_c = self.combo_candidate.currentIndex()
        self.combo_baseline.blockSignals(True)
        self.combo_candidate.blockSignals(True)
        self.combo_baseline.setCurrentIndex(idx_c)
        self.combo_candidate.setCurrentIndex(idx_b)
        self.combo_baseline.blockSignals(False)
        self.combo_candidate.blockSignals(False)
        self._update_view()

    def _on_capture_clicked(self):
        """Capture the current simulation state from workbench if completed."""
        if hasattr(self.workbench, "capture_current_run"):
            record = self.workbench.capture_current_run()
            if record:
                self.lbl_status.setText(f"Captured run: '{record.label}'.")
                self.refresh_runs()
            else:
                self.lbl_status.setText("Simulation must be 100% completed before it can be captured.")

    def _update_view(self):
        """Recompute and render comparison if 2+ runs exist."""
        runs: list[SimulationRunRecord] = getattr(self.workbench, "captured_runs", [])
        if len(runs) < 2:
            self.current_comparison = None
            self.stack.setCurrentWidget(self.empty_page)
            self.combo_baseline.setEnabled(False)
            self.combo_candidate.setEnabled(False)
            self.btn_swap.setEnabled(False)
            if hasattr(self, "btn_export_csv"):
                self.btn_export_csv.setEnabled(False)
            if hasattr(self, "btn_export_html"):
                self.btn_export_html.setEnabled(False)
            return

        self.combo_baseline.setEnabled(True)
        self.combo_candidate.setEnabled(True)
        self.btn_swap.setEnabled(True)

        id_b = self.combo_baseline.currentData()
        id_c = self.combo_candidate.currentData()

        run_b = next((r for r in runs if r.run_id == id_b), None)
        run_c = next((r for r in runs if r.run_id == id_c), None)

        if not run_b or not run_c:
            self.current_comparison = None
            self.stack.setCurrentWidget(self.empty_page)
            if hasattr(self, "btn_export_csv"):
                self.btn_export_csv.setEnabled(False)
            if hasattr(self, "btn_export_html"):
                self.btn_export_html.setEnabled(False)
            return

        self.stack.setCurrentWidget(self.report_page)
        comparison = compare_runs(run_b, run_c)
        self.current_comparison = comparison
        if hasattr(self, "btn_export_csv"):
            self.btn_export_csv.setEnabled(True)
        if hasattr(self, "btn_export_html"):
            self.btn_export_html.setEnabled(True)

        # Warning banner
        if comparison.warning:
            self.warning_frame.show()
            self.lbl_warning.setText(f"⚠ {comparison.warning}")
        else:
            self.warning_frame.hide()

        # Update Chart
        self.chart_view.set_comparison(comparison)

        # Update Table
        self._populate_table(comparison)

    def get_current_comparison(self) -> ScenarioComparison | None:
        """Return the active ScenarioComparison or None if unavailable."""
        return getattr(self, "current_comparison", None)

    def confirm_overwrite(self, path: Path) -> bool:
        """Prompt confirmation before overwriting an existing file."""
        if hasattr(self.workbench, "confirm_overwrite"):
            return self.workbench.confirm_overwrite(path)
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

    def export_csv(self, path: str | Path | None = None) -> bool:
        """Export current scenario comparison to CSV."""
        if path is None or isinstance(path, bool):
            path = None

        comparison = self.get_current_comparison()
        if not comparison:
            QMessageBox.warning(
                self,
                "Export Comparison",
                "No valid comparison is available to export.\nPlease select two completed runs.",
            )
            return False

        if path is None:
            default_name = f"comparison_{comparison.baseline.scenario_name}_vs_{comparison.candidate.scenario_name}.csv".replace(" ", "_")
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Comparison as CSV",
                default_name,
                "CSV Files (*.csv);;All Files (*)",
                options=QFileDialog.Option.DontConfirmOverwrite,
            )
            if not file_path:
                self.lbl_status.setText("Export cancelled.")
                return False
            path = file_path

        dest = Path(path)
        if dest.suffix.lower() != ".csv":
            dest = dest.with_suffix(".csv")

        if dest.exists() and not self.confirm_overwrite(dest):
            self.lbl_status.setText("Export cancelled: existing file not overwritten.")
            return False

        try:
            export_comparison_csv(comparison, dest)
            self.lbl_status.setText(f"Comparison exported to '{dest.name}'.")
            QMessageBox.information(
                self,
                "Export Successful",
                f"Comparison metrics successfully exported to:\n{dest}",
            )
            return True
        except Exception as exc:
            self.lbl_status.setText(f"Export failed: {exc}")
            QMessageBox.critical(self, "Export Failed", f"Failed to export comparison:\n{exc}")
            return False

    def export_html(self, path: str | Path | None = None) -> bool:
        """Export current scenario comparison to a readable HTML report."""
        if path is None or isinstance(path, bool):
            path = None

        comparison = self.get_current_comparison()
        if not comparison:
            QMessageBox.warning(
                self,
                "Export Comparison",
                "No valid comparison is available to export.\nPlease select two completed runs.",
            )
            return False

        if path is None:
            default_name = f"comparison_{comparison.baseline.scenario_name}_vs_{comparison.candidate.scenario_name}.html".replace(" ", "_")
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Comparison as HTML",
                default_name,
                "HTML Files (*.html *.htm);;All Files (*)",
                options=QFileDialog.Option.DontConfirmOverwrite,
            )
            if not file_path:
                self.lbl_status.setText("Export cancelled.")
                return False
            path = file_path

        dest = Path(path)
        if dest.suffix.lower() not in (".html", ".htm"):
            dest = dest.with_suffix(".html")

        if dest.exists() and not self.confirm_overwrite(dest):
            self.lbl_status.setText("Export cancelled: existing file not overwritten.")
            return False

        try:
            export_comparison_html(comparison, dest)
            self.lbl_status.setText(f"Comparison report exported to '{dest.name}'.")
            QMessageBox.information(
                self,
                "Export Successful",
                f"Comparison report successfully exported to:\n{dest}",
            )
            return True
        except Exception as exc:
            self.lbl_status.setText(f"Export failed: {exc}")
            QMessageBox.critical(self, "Export Failed", f"Failed to export comparison report:\n{exc}")
            return False

    def _populate_table(self, comp: ScenarioComparison):
        """Populate the 6-column comparison table with formatted values and status badges."""
        self.table.setRowCount(len(comp.metrics))

        for row, m in enumerate(comp.metrics):
            # 1. Metric Name
            item_name = QTableWidgetItem(f"{m.name} ({m.unit})")
            item_name.setToolTip(m.note)

            # 2. Baseline
            b_text = "—"
            if m.baseline_value is not None:
                b_text = f"{m.baseline_value:.1f}" if isinstance(m.baseline_value, float) else str(m.baseline_value)
            item_base = QTableWidgetItem(b_text)
            item_base.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 3. Candidate
            c_text = "—"
            if m.candidate_value is not None:
                c_text = f"{m.candidate_value:.1f}" if isinstance(m.candidate_value, float) else str(m.candidate_value)
            item_cand = QTableWidgetItem(c_text)
            item_cand.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 4. Absolute Change
            diff_text = "—"
            if m.absolute_change is not None:
                prefix = "+" if m.absolute_change > 0 else ""
                diff_text = f"{prefix}{m.absolute_change:.1f}" if isinstance(m.absolute_change, float) and "." in str(m.baseline_value) else f"{prefix}{m.absolute_change}"
            item_diff = QTableWidgetItem(diff_text)
            item_diff.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 5. % Change
            pct_text = "—"
            if m.percent_change is not None:
                prefix = "+" if m.percent_change > 0 else ""
                pct_text = f"{prefix}{m.percent_change:.1f}%"
            elif m.is_available and m.baseline_value == 0:
                pct_text = "N/A (base 0)"
            item_pct = QTableWidgetItem(pct_text)
            item_pct.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 6. Assessment badge
            badge_text = "— Unavailable"
            badge_color = "#64748b"

            if m.status == ComparisonStatus.IMPROVED:
                badge_text = "🟢 Improved"
                badge_color = "#16a34a"
            elif m.status == ComparisonStatus.REGRESSED:
                badge_text = "🔴 Regressed"
                badge_color = "#dc2626"
            elif m.status == ComparisonStatus.UNCHANGED:
                badge_text = "⚪ Unchanged"
                badge_color = "#475569"
            elif m.status == ComparisonStatus.UNAVAILABLE:
                badge_text = "— Not modeled"
                badge_color = "#94a3b8"

            item_status = QTableWidgetItem(badge_text)
            item_status.setForeground(QBrush(QColor(badge_color)))
            item_status.setFont(safe_font("Segoe UI", 9, QFont.Weight.Bold))
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row, 0, item_name)
            self.table.setItem(row, 1, item_base)
            self.table.setItem(row, 2, item_cand)
            self.table.setItem(row, 3, item_diff)
            self.table.setItem(row, 4, item_pct)
            self.table.setItem(row, 5, item_status)
