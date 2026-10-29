"""Simulation Run History dialog and run inspection views (Step 5H).

Provides:
- RunDetailsDialog: Accessible modal dialog displaying complete metrics of a single captured run.
- SimulationRunHistoryDialog: Session-based run history dialog to browse, inspect, compare,
  and export completed simulation runs without rerunning simulations.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
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
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tms_sim.reporting.comparison import SimulationRunRecord
from tms_sim.reporting.export import export_run_csv, export_run_html

if TYPE_CHECKING:
    from tms_sim.ui.app import Workbench


def safe_font(family: str = "Segoe UI", point_size: int = 9, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Return a QFont with a guaranteed positive integer point size, avoiding Qt font warnings."""
    valid_size = int(point_size) if point_size and int(point_size) > 0 else 9
    font = QFont(family, valid_size, weight)
    if font.pointSize() <= 0:
        font.setPointSize(valid_size)
    return font


class RunDetailsDialog(QDialog):
    """Detailed modal view for inspecting all metrics and metadata of a single run."""

    def __init__(self, run: SimulationRunRecord, workbench: Workbench | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.run = run
        self.workbench = workbench
        self.setWindowTitle(f"Simulation Run Details — {run.label}")
        self.resize(720, 520)
        self.setMinimumSize(560, 380)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # Header card
        header_card = QFrame()
        header_card.setStyleSheet("background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px;")
        hc_layout = QVBoxLayout(header_card)
        hc_layout.setSpacing(4)

        lbl_title = QLabel(self.run.label)
        lbl_title.setStyleSheet("font-size: 12pt; font-weight: 700; color: #0f172a;")
        hc_layout.addWidget(lbl_title)

        meta_text = (
            f"Scenario: <b>{self.run.scenario_name}</b> &nbsp;&bull;&nbsp; "
            f"Duration: <b>{self.run.metrics.duration:.1f}s</b> &nbsp;&bull;&nbsp; "
            f"Status: <b>{self.run.metrics.status}</b>"
        )
        if self.run.timestamp:
            meta_text += f" &nbsp;&bull;&nbsp; Captured: <b>{self.run.timestamp}</b>"
        lbl_meta = QLabel(meta_text)
        lbl_meta.setStyleSheet("color: #475569; font-size: 8.5pt;")
        hc_layout.addWidget(lbl_meta)
        layout.addWidget(header_card)

        # Metrics Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Metric", "Value", "Unit", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setFont(safe_font("Segoe UI", 9))
        self._populate_table()
        layout.addWidget(self.table, 1)

        # Footer
        footer = QHBoxLayout()
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 8.5pt;")
        footer.addWidget(self.lbl_status)
        footer.addStretch()

        btn_csv = QPushButton("📄  Export CSV…")
        btn_csv.clicked.connect(lambda checked=False: self._on_export_csv())
        footer.addWidget(btn_csv)

        btn_html = QPushButton("🌐  Export HTML…")
        btn_html.clicked.connect(lambda checked=False: self._on_export_html())
        footer.addWidget(btn_html)

        btn_close = QPushButton("Close")
        btn_close.setToolTip("Close this dialog")
        btn_close.setStyleSheet(
            "background: #ffffff; border: 1px solid #d0d5dd; border-radius: 5px; padding: 5px 14px; font-weight: 500;"
        )
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        layout.addLayout(footer)

    def _populate_table(self):
        m = self.run.metrics
        rows = [
            ("Vehicles Completed", str(m.vehicles_completed), "veh", "Available", "Total journeys finished"),
            (
                "Mean Travel Time",
                f"{m.mean_travel_time:.1f}" if m.mean_travel_time is not None else "N/A",
                "s",
                "Available" if m.mean_travel_time is not None else "Unavailable",
                "Average trip duration for completed journeys",
            ),
            ("Vehicles in Network", str(m.vehicles_in_network), "veh", "Available", "Active vehicles remaining"),
            ("Vehicles Entered", str(m.vehicles_entered), "veh", "Available", "Spawned into network"),
            ("Vehicles Generated", str(m.vehicles_generated), "veh", "Available", "Departed from demand schedule"),
            ("Total Scheduled Demand", str(m.total_scheduled), "veh", "Available", "Configured demand trips"),
            ("Simulated Time", f"{m.simulated_time:.1f}", "s", "Available", "Elapsed simulation time"),
            ("Simulation Duration", f"{m.duration:.1f}", "s", "Available", "Configured time horizon"),
            ("Hourly Throughput", f"{m.throughput_vph:.1f}" if m.throughput_vph is not None else "N/A", "veh/h", "Available" if m.throughput_vph is not None else "Unavailable", "Completed trips per simulated hour"),
            ("Average Speed", f"{m.average_speed_mps:.1f}" if m.average_speed_mps is not None else "N/A", "m/s", "Available" if m.average_speed_mps is not None else "Unavailable", "Distance divided by vehicle-time including stopped time"),
            ("Average Vehicle Delay", f"{m.average_delay_s:.1f}" if m.average_delay_s is not None else "N/A", "s", "Available" if m.average_delay_s is not None else "Unavailable", "Mean completed-trip delay from free-flow time"),
            ("Maximum Vehicle Delay", f"{m.maximum_delay_s:.1f}" if m.maximum_delay_s is not None else "N/A", "s", "Available" if m.maximum_delay_s is not None else "Unavailable", "Maximum completed-trip delay from free-flow time"),
            ("Average Queue Length", f"{m.queue_length_veh:.1f}" if m.queue_length_veh is not None else "N/A", "veh", "Available" if m.queue_length_veh is not None else "Unavailable", "Network-wide time-average queue count"),
        ]
        rows.extend(
            (f"Average Queue — {approach}", f"{value:.1f}", "veh", "Available", "Time-average queue count on this approach")
            for approach, value in sorted(m.average_queue_length_by_approach.items())
        )

        self.table.setRowCount(len(rows))
        for row_idx, (name, val, unit, status, desc) in enumerate(rows):
            item_name = QTableWidgetItem(name)
            item_name.setToolTip(desc)

            item_val = QTableWidgetItem(val)
            item_val.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            item_unit = QTableWidgetItem(unit)
            item_unit.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            item_status = QTableWidgetItem(status)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            color = "#16a34a" if status == "Available" else "#94a3b8"
            item_status.setForeground(QBrush(QColor(color)))

            self.table.setItem(row_idx, 0, item_name)
            self.table.setItem(row_idx, 1, item_val)
            self.table.setItem(row_idx, 2, item_unit)
            self.table.setItem(row_idx, 3, item_status)

    def _on_export_csv(self):
        default_name = f"run_{self.run.scenario_name}_{int(self.run.metrics.duration)}s.csv".replace(" ", "_")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Run as CSV",
            default_name,
            "CSV Files (*.csv);;All Files (*)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not file_path:
            return
        dest = Path(file_path)
        if dest.suffix.lower() != ".csv":
            dest = dest.with_suffix(".csv")
        try:
            export_run_csv(self.run, dest)
            self.lbl_status.setText(f"Exported to '{dest.name}'")
            QMessageBox.information(self, "Export Successful", f"Run metrics successfully exported to:\n{dest}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Failed to export CSV:\n{exc}")

    def _on_export_html(self):
        default_name = f"run_{self.run.scenario_name}_{int(self.run.metrics.duration)}s.html".replace(" ", "_")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Run as HTML",
            default_name,
            "HTML Files (*.html *.htm);;All Files (*)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not file_path:
            return
        dest = Path(file_path)
        if dest.suffix.lower() not in (".html", ".htm"):
            dest = dest.with_suffix(".html")
        try:
            export_run_html(self.run, dest)
            self.lbl_status.setText(f"Exported to '{dest.name}'")
            QMessageBox.information(self, "Export Successful", f"Run report successfully exported to:\n{dest}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Failed to export HTML:\n{exc}")


class SimulationRunHistoryDialog(QDialog):
    """Accessible session-based dialog for browsing and managing completed simulation runs."""

    def __init__(self, workbench: Workbench, parent: QWidget | None = None):
        super().__init__(parent or workbench)
        self.workbench = workbench
        self.setWindowTitle("Simulation Run History — TMS-Sim")
        self.resize(960, 560)
        self.setMinimumSize(740, 420)
        self._displayed_runs: list[SimulationRunRecord] = []

        self._init_ui()
        self.refresh_history()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)

        # 1. Header
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("Simulation Run History")
        lbl_title.setStyleSheet("font-size: 13pt; font-weight: 700; color: #0f172a;")
        lbl_sub = QLabel("Browse completed runs from the current session, inspect metrics, or select runs to compare.")
        lbl_sub.setStyleSheet("font-size: 9pt; color: #64748b;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header.addLayout(title_box)
        header.addStretch()

        self.btn_capture = QPushButton("📸  Capture Current Run")
        self.btn_capture.setToolTip("Capture the current simulation run if it is completed")
        self.btn_capture.setStyleSheet(
            "background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 5px; padding: 5px 12px; font-weight: 600;"
        )
        self.btn_capture.clicked.connect(lambda checked=False: self._on_capture_clicked())
        header.addWidget(self.btn_capture)

        self.btn_refresh = QPushButton("🔄  Refresh")
        self.btn_refresh.setToolTip("Refresh run history list")
        self.btn_refresh.setStyleSheet(
            "background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 5px; padding: 5px 12px; font-weight: 600;"
        )
        self.btn_refresh.clicked.connect(lambda checked=False: self.refresh_history())
        header.addWidget(self.btn_refresh)
        main_layout.addLayout(header)

        # 2. Stacked widget: Page 0 = Empty state; Page 1 = Table view
        self.stack = QStackedWidget()

        # --- Empty state ---
        self.empty_page = QWidget()
        empty_layout = QVBoxLayout(self.empty_page)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(10)

        self.lbl_empty_icon = QLabel("📜")
        self.lbl_empty_icon.setStyleSheet("font-size: 38pt; color: #94a3b8;")
        self.lbl_empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_empty_title = QLabel("No Completed Simulation Runs")
        self.lbl_empty_title.setStyleSheet("font-size: 12pt; font-weight: 700; color: #334155;")
        self.lbl_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_empty_desc = QLabel(
            "Runs will appear here automatically once your simulation reaches 100% completion.\n\n"
            "Run a simulation in the workbench to inspect metrics, compare configurations, and export reports."
        )
        self.lbl_empty_desc.setStyleSheet("color: #64748b; font-size: 9pt; max-width: 500px;")
        self.lbl_empty_desc.setWordWrap(True)
        self.lbl_empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_layout.addWidget(self.lbl_empty_icon)
        empty_layout.addWidget(self.lbl_empty_title)
        empty_layout.addWidget(self.lbl_empty_desc)
        self.stack.addWidget(self.empty_page)

        # --- Table view ---
        self.table_page = QWidget()
        table_layout = QVBoxLayout(self.table_page)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(6)

        # Latest run banner
        self.banner_frame = QFrame()
        self.banner_frame.setStyleSheet(
            "background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 6px;"
        )
        bf_layout = QHBoxLayout(self.banner_frame)
        bf_layout.setContentsMargins(8, 4, 8, 4)
        self.lbl_banner = QLabel("")
        self.lbl_banner.setStyleSheet("color: #15803d; font-size: 8.5pt; font-weight: 600;")
        bf_layout.addWidget(self.lbl_banner)
        table_layout.addWidget(self.banner_frame)

        # History Table
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Run",
            "Label",
            "Scenario",
            "Captured Time",
            "Duration",
            "Completed",
            "In Network",
            "Entered",
            "Generated",
            "Mean Travel Time",
        ])
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setFont(safe_font("Segoe UI", 9))
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(lambda item: self.view_selected_details())
        table_layout.addWidget(self.table, 1)

        # Selection hint label
        self.lbl_selection_hint = QLabel("Select 1 run to view details or export, or select 2 runs to compare.")
        self.lbl_selection_hint.setStyleSheet("color: #64748b; font-size: 8.5pt; font-style: italic;")
        table_layout.addWidget(self.lbl_selection_hint)

        self.stack.addWidget(self.table_page)
        main_layout.addWidget(self.stack, 1)

        # 3. Footer actions
        footer = QHBoxLayout()
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 8.5pt;")
        footer.addWidget(self.lbl_status)
        footer.addStretch()

        self.btn_view_details = QPushButton("🔍  View Details…")
        self.btn_view_details.setToolTip("View detailed metrics of selected run (select 1 run)")
        self.btn_view_details.setStyleSheet("padding: 5px 12px; font-weight: 600;")
        self.btn_view_details.clicked.connect(lambda checked=False: self.view_selected_details())
        footer.addWidget(self.btn_view_details)

        self.btn_compare = QPushButton("⚖  Compare Selected…")
        self.btn_compare.setToolTip("Compare exactly two selected runs side-by-side")
        self.btn_compare.setStyleSheet("padding: 5px 12px; font-weight: 600;")
        self.btn_compare.clicked.connect(lambda checked=False: self.compare_selected_runs())
        footer.addWidget(self.btn_compare)

        self.btn_export_csv = QPushButton("📄  Export CSV…")
        self.btn_export_csv.setToolTip("Export selected run metrics to CSV")
        self.btn_export_csv.setStyleSheet("padding: 5px 12px;")
        self.btn_export_csv.clicked.connect(lambda checked=False: self.export_selected_csv())
        footer.addWidget(self.btn_export_csv)

        self.btn_export_html = QPushButton("🌐  Export HTML…")
        self.btn_export_html.setToolTip("Export selected run metrics as readable HTML report")
        self.btn_export_html.setStyleSheet("padding: 5px 12px;")
        self.btn_export_html.clicked.connect(lambda checked=False: self.export_selected_html())
        footer.addWidget(self.btn_export_html)

        btn_close = QPushButton("Close")
        btn_close.setToolTip("Close run history dialog")
        btn_close.setStyleSheet(
            "background: #ffffff; border: 1px solid #d0d5dd; border-radius: 5px; padding: 5px 14px; font-weight: 500;"
        )
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        main_layout.addLayout(footer)

    def refresh_history(self) -> None:
        """Synchronize the table with workbench's captured runs."""
        runs: list[SimulationRunRecord] = getattr(self.workbench, "captured_runs", [])
        if not runs:
            self._displayed_runs = []
            self.stack.setCurrentWidget(self.empty_page)
            self.btn_view_details.setEnabled(False)
            self.btn_compare.setEnabled(False)
            self.btn_export_csv.setEnabled(False)
            self.btn_export_html.setEnabled(False)
            return

        self.stack.setCurrentWidget(self.table_page)

        # Order runs in reverse chronological order (latest at top)
        self._displayed_runs = list(reversed(runs))
        latest_run = runs[-1]

        # Update latest banner
        time_str = f" at {latest_run.timestamp}" if latest_run.timestamp else ""
        travel_str = f"{latest_run.metrics.mean_travel_time:.1f}s" if latest_run.metrics.mean_travel_time is not None else "N/A"
        self.lbl_banner.setText(
            f"⭐ Latest Run: <b>{latest_run.label}</b>{time_str} &nbsp;&bull;&nbsp; "
            f"Completed: <b>{latest_run.metrics.vehicles_completed} veh</b> &nbsp;&bull;&nbsp; "
            f"Mean Travel Time: <b>{travel_str}</b>"
        )

        self.table.blockSignals(True)
        self.table.setRowCount(len(self._displayed_runs))

        for row_idx, run in enumerate(self._displayed_runs):
            m = run.metrics
            is_latest = (run.run_id == latest_run.run_id)

            # 0. Run badge
            run_num = len(runs) - row_idx
            badge_text = f"⭐ #{run_num} (Latest)" if is_latest else f"#{run_num}"
            item_badge = QTableWidgetItem(badge_text)
            if is_latest:
                item_badge.setFont(safe_font("Segoe UI", 9, QFont.Weight.Bold))
                item_badge.setForeground(QBrush(QColor("#15803d")))
            else:
                item_badge.setForeground(QBrush(QColor("#475569")))

            # 1. Label
            item_label = QTableWidgetItem(run.label)
            if is_latest:
                item_label.setFont(safe_font("Segoe UI", 9, QFont.Weight.Bold))

            # 2. Scenario
            item_scen = QTableWidgetItem(run.scenario_name)

            # 3. Captured Time
            item_time = QTableWidgetItem(run.timestamp or "—")
            item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # 4. Duration
            item_dur = QTableWidgetItem(f"{m.duration:.1f}s")
            item_dur.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 5. Completed
            item_comp = QTableWidgetItem(f"{m.vehicles_completed}")
            item_comp.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 6. In Network (Remaining)
            item_net = QTableWidgetItem(f"{m.vehicles_in_network}")
            item_net.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 7. Entered
            item_ent = QTableWidgetItem(f"{m.vehicles_entered}")
            item_ent.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 8. Generated
            item_gen = QTableWidgetItem(f"{m.vehicles_generated}")
            item_gen.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 9. Mean Travel Time
            tt_str = f"{m.mean_travel_time:.1f}s" if m.mean_travel_time is not None else "N/A"
            item_tt = QTableWidgetItem(tt_str)
            item_tt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if m.mean_travel_time is None:
                item_tt.setForeground(QBrush(QColor("#94a3b8")))

            self.table.setItem(row_idx, 0, item_badge)
            self.table.setItem(row_idx, 1, item_label)
            self.table.setItem(row_idx, 2, item_scen)
            self.table.setItem(row_idx, 3, item_time)
            self.table.setItem(row_idx, 4, item_dur)
            self.table.setItem(row_idx, 5, item_comp)
            self.table.setItem(row_idx, 6, item_net)
            self.table.setItem(row_idx, 7, item_ent)
            self.table.setItem(row_idx, 8, item_gen)
            self.table.setItem(row_idx, 9, item_tt)

        # Select first row by default
        self.table.selectRow(0)
        self.table.blockSignals(False)
        self._on_selection_changed()

    def select_run_rows(self, rows: list[int]) -> None:
        """Programmatically select specific rows by index."""
        from PySide6.QtCore import QItemSelectionModel
        self.table.clearSelection()
        for r in rows:
            if 0 <= r < self.table.rowCount():
                self.table.selectionModel().select(
                    self.table.model().index(r, 0),
                    QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
                )

    def get_selected_runs(self) -> list[SimulationRunRecord]:
        """Return list of selected SimulationRunRecords based on table selection."""
        rows = sorted(set(index.row() for index in self.table.selectedIndexes()))
        results: list[SimulationRunRecord] = []
        for row in rows:
            if 0 <= row < len(self._displayed_runs):
                results.append(self._displayed_runs[row])
        return results

    def _on_selection_changed(self):
        """Update actions and tooltips based on current selection count."""
        selected = self.get_selected_runs()
        count = len(selected)

        if count == 1:
            self.btn_view_details.setEnabled(True)
            self.btn_export_csv.setEnabled(True)
            self.btn_export_html.setEnabled(True)
            self.btn_compare.setEnabled(False)
            self.btn_compare.setToolTip("Select exactly two runs from the table to compare (Ctrl+Click to select 2)")
            self.lbl_selection_hint.setText(f"Selected 1 run: <b>{selected[0].label}</b>. Ready to view details or export.")
        elif count == 2:
            self.btn_view_details.setEnabled(False)
            self.btn_export_csv.setEnabled(False)
            self.btn_export_html.setEnabled(False)
            self.btn_compare.setEnabled(True)
            self.btn_compare.setToolTip(f"Compare '{selected[1].label}' (Baseline) vs '{selected[0].label}' (Candidate)")
            self.lbl_selection_hint.setText(
                f"Selected 2 runs: <b>{selected[1].label}</b> vs <b>{selected[0].label}</b>. Ready to compare."
            )
        else:
            self.btn_view_details.setEnabled(False)
            self.btn_export_csv.setEnabled(False)
            self.btn_export_html.setEnabled(False)
            self.btn_compare.setEnabled(False)
            if count == 0:
                self.btn_compare.setToolTip("Select exactly two runs to compare")
                self.lbl_selection_hint.setText("Select 1 run to view details or export, or select 2 runs to compare.")
            else:
                self.btn_compare.setToolTip("Cannot compare more than two runs simultaneously")
                self.lbl_selection_hint.setText(f"{count} runs selected. Select exactly 2 runs to compare, or 1 to view details.")

    def _on_capture_clicked(self):
        """Manually capture the current completed run from workbench if available."""
        if hasattr(self.workbench, "capture_current_run"):
            record = self.workbench.capture_current_run()
            if record:
                self.lbl_status.setText(f"Captured run: '{record.label}'.")
                self.refresh_history()
            else:
                self.lbl_status.setText("Simulation must be 100% completed before it can be captured.")

    def view_selected_details(self) -> None:
        """Open detailed metrics view for the single selected run."""
        selected = self.get_selected_runs()
        if len(selected) != 1:
            QMessageBox.information(self, "View Details", "Please select exactly one run to view details.")
            return

        dialog = RunDetailsDialog(selected[0], self.workbench, self)
        dialog.exec()

    def compare_selected_runs(self) -> None:
        """Trigger scenario comparison between the two selected runs."""
        selected = self.get_selected_runs()
        if len(selected) != 2:
            QMessageBox.warning(
                self,
                "Compare Runs",
                f"Please select exactly two runs to compare. Currently selected: {len(selected)}.",
            )
            return

        # Convention: Older run is baseline, newer run is candidate
        # Since _displayed_runs is reverse chronological, selected[1] is older, selected[0] is newer
        run_baseline = selected[1]
        run_candidate = selected[0]

        if hasattr(self.workbench, "open_comparison_dialog"):
            self.workbench.open_comparison_dialog(
                baseline_run_id=run_baseline.run_id,
                candidate_run_id=run_candidate.run_id,
            )

    def export_selected_csv(self, path: str | Path | None = None) -> bool:
        """Export the selected run metrics to CSV."""
        if path is None or isinstance(path, bool):
            path = None

        selected = self.get_selected_runs()
        if len(selected) != 1:
            QMessageBox.warning(self, "Export CSV", "Please select exactly one run to export.")
            return False

        run = selected[0]
        if path is None:
            default_name = f"run_{run.scenario_name}_{int(run.metrics.duration)}s.csv".replace(" ", "_")
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Simulation Run as CSV",
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

        if dest.exists():
            if hasattr(self.workbench, "confirm_overwrite") and not self.workbench.confirm_overwrite(dest):
                self.lbl_status.setText("Export cancelled: existing file not overwritten.")
                return False

        try:
            export_run_csv(run, dest)
            self.lbl_status.setText(f"Exported run to '{dest.name}'.")
            QMessageBox.information(self, "Export Successful", f"Run metrics successfully exported to:\n{dest}")
            return True
        except Exception as exc:
            self.lbl_status.setText(f"Export failed: {exc}")
            QMessageBox.critical(self, "Export Failed", f"Failed to export CSV:\n{exc}")
            return False

    def export_selected_html(self, path: str | Path | None = None) -> bool:
        """Export the selected run metrics as readable HTML report."""
        if path is None or isinstance(path, bool):
            path = None

        selected = self.get_selected_runs()
        if len(selected) != 1:
            QMessageBox.warning(self, "Export HTML", "Please select exactly one run to export.")
            return False

        run = selected[0]
        if path is None:
            default_name = f"run_{run.scenario_name}_{int(run.metrics.duration)}s.html".replace(" ", "_")
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Simulation Run as HTML",
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

        if dest.exists():
            if hasattr(self.workbench, "confirm_overwrite") and not self.workbench.confirm_overwrite(dest):
                self.lbl_status.setText("Export cancelled: existing file not overwritten.")
                return False

        try:
            export_run_html(run, dest)
            self.lbl_status.setText(f"Exported report to '{dest.name}'.")
            QMessageBox.information(self, "Export Successful", f"Run report successfully exported to:\n{dest}")
            return True
        except Exception as exc:
            self.lbl_status.setText(f"Export failed: {exc}")
            QMessageBox.critical(self, "Export Failed", f"Failed to export HTML:\n{exc}")
            return False
