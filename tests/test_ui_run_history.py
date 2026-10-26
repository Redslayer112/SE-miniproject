"""Automated tests for TMS-Sim Step 5H: Simulation Run History.

Covers:
1. Empty history state in SimulationRunHistoryDialog.
2. One or multiple completed runs displayed in reverse chronological order with latest indicator.
3. Identification of the latest run in table and banner.
4. Missing metrics (such as mean_travel_time=None) displayed as 'N/A' rather than zero.
5. Selection state transitions:
   - 0 selected: actions disabled.
   - 1 selected: view details, export CSV, export HTML enabled; compare disabled.
   - 2 selected: compare enabled; single-run actions disabled.
   - 3+ selected: all actions disabled.
6. Viewing details opens RunDetailsDialog with correct metric table values.
7. Comparing two selected runs pre-populates and opens ScenarioComparisonDialog.
8. Exporting selected run to CSV and HTML with mocked file dialogs.
9. Refreshing history automatically when a new run is captured.
10. Guard against duplicate capture of the same completed engine run.
11. Opening history dialog does not alter simulation clock, state, or timer.
12. Qt boolean callback protection on export actions.
13. Timestamp defaulting and metadata integrity in SimulationRunRecord.
"""
from __future__ import annotations

import csv
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from tms_sim.reporting.comparison import SimulationRunRecord, compare_runs
from tms_sim.reporting.metrics import SimulationMetrics
from tms_sim.ui.app import Workbench
from tms_sim.ui.comparison import ScenarioComparisonDialog
from tms_sim.ui.run_history import RunDetailsDialog, SimulationRunHistoryDialog

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
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    win = Workbench(SAMPLE_SCENARIO_PATH)
    win.canvas.resize(800, 600)
    yield win
    win.timer.stop()
    if hasattr(win, "comparison_dialog") and win.comparison_dialog:
        win.comparison_dialog.close()
    if hasattr(win, "history_dialog") and win.history_dialog:
        win.history_dialog.close()
    win.close()


def _make_dummy_record(
    run_id: str = "run_1",
    label: str = "Run 1: Test",
    scenario_name: str = "Test Scenario",
    travel_time: float | None = 16.4,
    completed: int = 30,
    in_network: int = 0,
    entered: int = 30,
    generated: int = 30,
    duration: float = 600.0,
    timestamp: str = "2026-10-26 09:00:00",
) -> SimulationRunRecord:
    metrics = SimulationMetrics(
        status="Completed",
        simulated_time=duration,
        duration=duration,
        vehicles_generated=generated,
        total_scheduled=generated,
        vehicles_entered=entered,
        vehicles_completed=completed,
        vehicles_in_network=in_network,
        mean_travel_time=travel_time,
    )
    return SimulationRunRecord(
        run_id=run_id,
        label=label,
        scenario_name=scenario_name,
        metrics=metrics,
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# 1. Empty State Tests
# ---------------------------------------------------------------------------

def test_run_history_empty_state(workbench):
    """Verify dialog opens to empty state when no runs have been captured."""
    workbench.captured_runs = []
    dialog = SimulationRunHistoryDialog(workbench)

    assert dialog.stack.currentWidget() == dialog.empty_page
    assert not dialog.btn_view_details.isEnabled()
    assert not dialog.btn_compare.isEnabled()
    assert not dialog.btn_export_csv.isEnabled()
    assert not dialog.btn_export_html.isEnabled()
    dialog.close()


# ---------------------------------------------------------------------------
# 2. Populated History & Latest Identification
# ---------------------------------------------------------------------------

def test_run_history_single_run_and_latest_indicator(workbench):
    """Verify single run is displayed with latest indicator and enabled single-run actions."""
    run1 = _make_dummy_record(run_id="run_1", label="Run 1: First Run", travel_time=15.0)
    workbench.captured_runs = [run1]

    dialog = SimulationRunHistoryDialog(workbench)
    assert dialog.stack.currentWidget() == dialog.table_page
    assert dialog.table.rowCount() == 1

    # Row 0 should be marked as Latest
    badge_item = dialog.table.item(0, 0)
    assert "⭐" in badge_item.text()
    assert "Latest" in badge_item.text()
    assert "Run 1: First Run" in dialog.lbl_banner.text()

    # Single run selected by default
    selected = dialog.get_selected_runs()
    assert len(selected) == 1
    assert selected[0].run_id == "run_1"

    # Action buttons
    assert dialog.btn_view_details.isEnabled()
    assert dialog.btn_export_csv.isEnabled()
    assert dialog.btn_export_html.isEnabled()
    assert not dialog.btn_compare.isEnabled()
    dialog.close()


def test_run_history_multiple_runs_reverse_chronological(workbench):
    """Verify multiple runs are listed with the latest at the top."""
    run1 = _make_dummy_record(run_id="r1", label="Run 1", timestamp="2026-10-26 09:00:00")
    run2 = _make_dummy_record(run_id="r2", label="Run 2", timestamp="2026-10-26 09:10:00")
    run3 = _make_dummy_record(run_id="r3", label="Run 3", timestamp="2026-10-26 09:20:00")
    workbench.captured_runs = [run1, run2, run3]

    dialog = SimulationRunHistoryDialog(workbench)
    assert dialog.table.rowCount() == 3

    # Row 0 must be Run 3 (latest)
    assert dialog.table.item(0, 1).text() == "Run 3"
    assert "Latest" in dialog.table.item(0, 0).text()
    assert dialog.table.item(1, 1).text() == "Run 2"
    assert dialog.table.item(2, 1).text() == "Run 1"
    assert "Latest" not in dialog.table.item(1, 0).text()
    assert "Latest" not in dialog.table.item(2, 0).text()

    dialog.close()


# ---------------------------------------------------------------------------
# 3. Missing Metrics Display
# ---------------------------------------------------------------------------

def test_missing_metrics_displayed_as_unavailable(workbench):
    """Verify mean travel time when None is displayed as N/A, and zero values are displayed as 0."""
    run = _make_dummy_record(
        run_id="r_none",
        travel_time=None,  # 0 trips completed
        in_network=0,      # actually 0 active vehicles
        completed=0,
    )
    workbench.captured_runs = [run]

    dialog = SimulationRunHistoryDialog(workbench)
    # Column 6: In Network -> "0"
    assert dialog.table.item(0, 6).text() == "0"

    # Column 9: Mean Travel Time -> "N/A"
    assert dialog.table.item(0, 9).text() == "N/A"
    dialog.close()


# ---------------------------------------------------------------------------
# 4. Selection Transitions
# ---------------------------------------------------------------------------

def test_selection_transitions(workbench):
    """Verify button enablement based on 0, 1, 2, or 3 selected rows."""
    run1 = _make_dummy_record(run_id="r1", label="Run 1")
    run2 = _make_dummy_record(run_id="r2", label="Run 2")
    run3 = _make_dummy_record(run_id="r3", label="Run 3")
    workbench.captured_runs = [run1, run2, run3]

    dialog = SimulationRunHistoryDialog(workbench)

    # 1 selected (default row 0)
    assert len(dialog.get_selected_runs()) == 1
    assert dialog.btn_view_details.isEnabled()
    assert not dialog.btn_compare.isEnabled()

    # Clear selection (0 selected)
    dialog.table.clearSelection()
    assert len(dialog.get_selected_runs()) == 0
    assert not dialog.btn_view_details.isEnabled()
    assert not dialog.btn_compare.isEnabled()
    assert not dialog.btn_export_csv.isEnabled()
    assert not dialog.btn_export_html.isEnabled()

    # Select 2 rows (compare enabled)
    dialog.select_run_rows([0, 1])
    # Check selection
    selected = dialog.get_selected_runs()
    assert len(selected) == 2
    assert dialog.btn_compare.isEnabled()
    assert not dialog.btn_view_details.isEnabled()
    assert not dialog.btn_export_csv.isEnabled()
    assert not dialog.btn_export_html.isEnabled()

    # Select all 3 rows (compare disabled)
    dialog.table.selectAll()
    assert len(dialog.get_selected_runs()) == 3
    assert not dialog.btn_compare.isEnabled()
    assert not dialog.btn_view_details.isEnabled()

    dialog.close()


# ---------------------------------------------------------------------------
# 5. Details Dialog
# ---------------------------------------------------------------------------

def test_view_details_dialog(workbench):
    """Verify RunDetailsDialog displays all modeled and unmodeled metrics accurately."""
    run = _make_dummy_record(
        run_id="r_det",
        label="Run Details Test",
        travel_time=17.8,
        completed=42,
        in_network=3,
    )
    details = RunDetailsDialog(run, workbench)

    # Table contains 11 metrics
    assert details.table.rowCount() == 11

    # Check Completed row
    assert details.table.item(0, 0).text() == "Vehicles Completed"
    assert details.table.item(0, 1).text() == "42"
    assert details.table.item(0, 2).text() == "veh"
    assert details.table.item(0, 3).text() == "Available"

    # Check Mean Travel Time row
    assert details.table.item(1, 0).text() == "Mean Travel Time"
    assert details.table.item(1, 1).text() == "17.8"
    assert details.table.item(1, 2).text() == "s"

    # Check unmodeled metric
    assert details.table.item(8, 0).text() == "Hourly Throughput"
    assert details.table.item(8, 1).text() == "N/A"
    assert details.table.item(8, 3).text() == "Unavailable"

    details.close()


# ---------------------------------------------------------------------------
# 6. Compare Two Selected Runs
# ---------------------------------------------------------------------------

def test_compare_selected_runs_flow(workbench):
    """Verify selecting two runs and clicking compare opens comparison dialog with both selected."""
    run1 = _make_dummy_record(run_id="run_a", label="Run Alpha")
    run2 = _make_dummy_record(run_id="run_b", label="Run Beta")
    workbench.captured_runs = [run1, run2]

    dialog = SimulationRunHistoryDialog(workbench)
    # Select both rows
    dialog.select_run_rows([0, 1])
    assert len(dialog.get_selected_runs()) == 2

    dialog.compare_selected_runs()

    # Workbench comparison dialog should now be active
    assert workbench.comparison_dialog is not None
    assert workbench.comparison_dialog.isVisible()

    comp_dialog = workbench.comparison_dialog
    # The two runs should be loaded into baseline and candidate combos
    cur_b = comp_dialog.combo_baseline.currentData()
    cur_c = comp_dialog.combo_candidate.currentData()
    assert {cur_b, cur_c} == {"run_a", "run_b"}

    comp_dialog.close()
    dialog.close()


# ---------------------------------------------------------------------------
# 7. Export Selected Run
# ---------------------------------------------------------------------------

def test_export_selected_run_csv_and_html(workbench, tmp_path, monkeypatch):
    """Verify exporting selected run from history dialog writes valid files."""
    run = _make_dummy_record(run_id="r_exp", label="Export Run", travel_time=14.5)
    workbench.captured_runs = [run]

    dialog = SimulationRunHistoryDialog(workbench)
    dialog.table.selectRow(0)

    # Export CSV
    target_csv = tmp_path / "history_run.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target_csv), "CSV"))

    success_csv = dialog.export_selected_csv()
    assert success_csv is True
    assert target_csv.exists()
    assert "14.5" in target_csv.read_text(encoding="utf-8")
    assert "Exported run" in dialog.lbl_status.text()

    # Export HTML
    target_html = tmp_path / "history_run.html"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target_html), "HTML"))

    success_html = dialog.export_selected_html()
    assert success_html is True
    assert target_html.exists()
    assert "<!DOCTYPE html>" in target_html.read_text(encoding="utf-8")
    assert "Exported report" in dialog.lbl_status.text()

    dialog.close()


# ---------------------------------------------------------------------------
# 8. Refresh and Dynamic Capture
# ---------------------------------------------------------------------------

def test_run_history_auto_refresh_on_capture(workbench):
    """Verify history dialog updates when workbench captures a new completed run."""
    run1 = _make_dummy_record(run_id="r1", label="Run 1")
    workbench.captured_runs = [run1]

    dialog = workbench.open_run_history_dialog()
    assert dialog.table.rowCount() == 1

    # Simulate new run capture in workbench
    run2 = _make_dummy_record(run_id="r2", label="Run 2")
    workbench.captured_runs.append(run2)
    dialog.refresh_history()

    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 1).text() == "Run 2"
    assert "Latest" in dialog.table.item(0, 0).text()

    dialog.close()


# ---------------------------------------------------------------------------
# 9. No Duplicate History Entry
# ---------------------------------------------------------------------------

def test_no_duplicate_capture_for_same_completed_run(workbench):
    """Verify calling capture_current_run multiple times on the same engine does not duplicate entries."""
    assert workbench.engine is not None
    # Fast-forward engine to completion
    while not workbench.engine.finished:
        workbench.engine.step()

    workbench.captured_runs = []
    workbench._last_captured_engine_signature = None

    rec1 = workbench.capture_current_run()
    assert rec1 is not None
    assert len(workbench.captured_runs) == 1

    # Second call without resetting engine must NOT duplicate
    rec2 = workbench.capture_current_run()
    assert rec2 is not None
    assert len(workbench.captured_runs) == 1
    assert rec1.run_id == rec2.run_id


# ---------------------------------------------------------------------------
# 10. Opening History Preserves Simulation State
# ---------------------------------------------------------------------------

def test_opening_history_preserves_simulation_state(workbench):
    """Verify opening history dialog does not pause, step, or reset an active simulation."""
    assert workbench.engine is not None
    # Advance engine 5 steps
    for _ in range(5):
        workbench.engine.step()

    time_before = workbench.engine.time
    assert time_before > 0.0

    # Open history dialog
    dialog = workbench.open_run_history_dialog()
    assert dialog.isVisible()

    # Time and state must be identical
    assert workbench.engine.time == time_before
    dialog.close()


# ---------------------------------------------------------------------------
# 11. Qt Boolean Callback Safety
# ---------------------------------------------------------------------------

def test_ui_boolean_callback_safety_in_history(workbench, tmp_path, monkeypatch):
    """Verify passing boolean (from Qt action.triggered) does not treat boolean as destination path."""
    run = _make_dummy_record()
    workbench.captured_runs = [run]
    dialog = SimulationRunHistoryDialog(workbench)
    dialog.table.selectRow(0)

    target = tmp_path / "bool_safe.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), "CSV"))

    # When connected to action.triggered(bool), checked=False is passed
    res = dialog.export_selected_csv(False)
    assert res is True
    assert target.exists()
    dialog.close()


# ---------------------------------------------------------------------------
# 12. Timestamp Defaulting
# ---------------------------------------------------------------------------

def test_simulation_run_record_timestamp_defaulting(workbench):
    """Verify SimulationRunRecord.from_engine sets a valid non-empty timestamp when none passed."""
    assert workbench.engine is not None
    while not workbench.engine.finished:
        workbench.engine.step()

    record = SimulationRunRecord.from_engine(workbench.engine)
    assert record.timestamp != ""
    assert len(record.timestamp) >= 10
