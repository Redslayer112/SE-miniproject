"""Automated tests for TMS-Sim Step 5F: Simulation Scenario Comparison.

Covers:
1. Metric comparison absolute and percentage differences.
2. Zero baseline handling without division errors.
3. Missing or unmodeled metrics explicitly handled as unavailable.
4. Directionality: lower-is-better, higher-is-better, and neutral evaluations.
5. Equal metric values classified as unchanged.
6. Duration incompatibility detection and warning generation.
7. Incomplete simulation run rejection.
8. Independent, immutable run snapshots.
9. Comparison dialog empty state when fewer than two completed runs exist.
10. Comparison dialog table and chart rendering with two completed runs.
11. Selecting baseline/candidate and swapping runs updates view.
12. Auto-capture of runs upon simulation completion in Workbench.
13. Capturing run from dialog button.
14. Scenario dirty state and undo/redo remain unaffected by comparison features.
"""
from __future__ import annotations

import copy
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from tms_sim.reporting.comparison import (
    ComparisonStatus,
    MetricDirection,
    ScenarioComparison,
    SimulationRunRecord,
    calculate_metric_comparison,
    compare_runs,
)
from tms_sim.reporting.metrics import SimulationMetrics
from tms_sim.ui.app import Workbench
from tms_sim.ui.comparison import ComparisonChartView, ScenarioComparisonDialog

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

    win = Workbench(SAMPLE_SCENARIO_PATH)
    win.canvas.resize(800, 600)
    yield win
    win.timer.stop()
    if hasattr(win, "comparison_dialog") and win.comparison_dialog:
        win.comparison_dialog.close()
    win.close()


def _make_dummy_metrics(
    travel_time: float | None = 20.0,
    completed: int = 30,
    in_network: int = 0,
    entered: int = 30,
    generated: int = 30,
    duration: float = 600.0,
    status: str = "Completed",
) -> SimulationMetrics:
    return SimulationMetrics(
        status=status,
        simulated_time=duration,
        duration=duration,
        vehicles_generated=generated,
        total_scheduled=generated,
        vehicles_entered=entered,
        vehicles_completed=completed,
        vehicles_in_network=in_network,
        mean_travel_time=travel_time,
    )


# ---------------------------------------------------------------------------
# Unit tests on Comparison Data Models
# ---------------------------------------------------------------------------

def test_metric_comparison_absolute_and_percentage_differences():
    """Verify absolute and percentage differences are calculated accurately."""
    # Travel time: 20.0s -> 15.0s (Diff = -5.0s, -25.0%)
    m_tt = calculate_metric_comparison(
        key="mean_travel_time",
        name="Mean Travel Time",
        unit="s",
        baseline_val=20.0,
        candidate_val=15.0,
        direction=MetricDirection.LOWER_IS_BETTER,
    )
    assert m_tt.absolute_change == -5.0
    assert m_tt.percent_change == -25.0
    assert m_tt.status == ComparisonStatus.IMPROVED

    # Completed vehicles: 20 -> 25 (Diff = +5, +25.0%)
    m_comp = calculate_metric_comparison(
        key="vehicles_completed",
        name="Vehicles Completed",
        unit="veh",
        baseline_val=20,
        candidate_val=25,
        direction=MetricDirection.HIGHER_IS_BETTER,
    )
    assert m_comp.absolute_change == 5.0
    assert m_comp.percent_change == 25.0
    assert m_comp.status == ComparisonStatus.IMPROVED


def test_zero_baseline_percentage_handling():
    """Verify zero baseline values do not crash and report percent_change as None."""
    m = calculate_metric_comparison(
        key="vehicles_completed",
        name="Vehicles Completed",
        unit="veh",
        baseline_val=0,
        candidate_val=10,
        direction=MetricDirection.HIGHER_IS_BETTER,
    )
    assert m.absolute_change == 10.0
    assert m.percent_change is None
    assert m.status == ComparisonStatus.IMPROVED


def test_missing_or_unmodeled_metrics_handled_explicitly():
    """Verify missing values are handled gracefully as UNAVAILABLE."""
    # One value missing
    m1 = calculate_metric_comparison(
        key="mean_travel_time",
        name="Mean Travel Time",
        unit="s",
        baseline_val=None,
        candidate_val=16.4,
        direction=MetricDirection.LOWER_IS_BETTER,
    )
    assert m1.status == ComparisonStatus.UNAVAILABLE
    assert m1.absolute_change is None
    assert m1.percent_change is None
    assert not m1.is_available

    # Both values missing
    m2 = calculate_metric_comparison(
        key="queue_length_veh",
        name="Queue Length",
        unit="veh",
        baseline_val=None,
        candidate_val=None,
        direction=MetricDirection.LOWER_IS_BETTER,
    )
    assert m2.status == ComparisonStatus.UNAVAILABLE
    assert m2.absolute_change is None
    assert m2.percent_change is None


def test_lower_is_better_and_higher_is_better_classification():
    """Verify improvement vs regression depending on metric direction."""
    # Lower is better (travel time): increase is regression, decrease is improvement
    m_worse = calculate_metric_comparison("tt", "TT", "s", 15.0, 20.0, MetricDirection.LOWER_IS_BETTER)
    assert m_worse.status == ComparisonStatus.REGRESSED

    m_better = calculate_metric_comparison("tt", "TT", "s", 20.0, 15.0, MetricDirection.LOWER_IS_BETTER)
    assert m_better.status == ComparisonStatus.IMPROVED

    # Higher is better (completed trips): increase is improvement, decrease is regression
    m_comp_better = calculate_metric_comparison("c", "C", "veh", 20, 25, MetricDirection.HIGHER_IS_BETTER)
    assert m_comp_better.status == ComparisonStatus.IMPROVED

    m_comp_worse = calculate_metric_comparison("c", "C", "veh", 25, 20, MetricDirection.HIGHER_IS_BETTER)
    assert m_comp_worse.status == ComparisonStatus.REGRESSED


def test_equal_metric_values_classified_as_unchanged():
    """Verify identical metric values result in UNCHANGED status."""
    m_equal = calculate_metric_comparison("tt", "TT", "s", 16.4, 16.4, MetricDirection.LOWER_IS_BETTER)
    assert m_equal.status == ComparisonStatus.UNCHANGED
    assert m_equal.absolute_change == 0.0
    assert m_equal.percent_change == 0.0


def test_duration_incompatibility_warning():
    """Verify different simulation durations produce compatibility warning."""
    rec_b = SimulationRunRecord("1", "Run 1", "Scen A", _make_dummy_metrics(duration=600.0))
    rec_c_same = SimulationRunRecord("2", "Run 2", "Scen B", _make_dummy_metrics(duration=600.0))
    rec_c_diff = SimulationRunRecord("3", "Run 3", "Scen C", _make_dummy_metrics(duration=300.0))

    comp_same = compare_runs(rec_b, rec_c_same)
    assert comp_same.duration_compatible is True
    assert comp_same.warning is None

    comp_diff = compare_runs(rec_b, rec_c_diff)
    assert comp_diff.duration_compatible is False
    assert comp_diff.warning is not None
    assert "600.0s vs Candidate: 300.0s" in comp_diff.warning


def test_incomplete_run_rejection():
    """Verify incomplete simulation runs cannot be captured as run records."""
    # Incomplete metrics (status = "Running")
    class FakeEngine:
        finished = False
        running = True
        time = 100.0
        duration = 600.0
        vehicles = []
        cars = []
        events = []

    with pytest.raises(ValueError, match="incomplete"):
        SimulationRunRecord.from_engine(FakeEngine())


def test_independent_immutable_snapshots(workbench):
    """Verify captured run records are immutable and detached from engine state."""
    # Finish simulation
    workbench.engine.time = workbench.engine.duration
    workbench.engine.finished = True
    record = workbench.capture_current_run("Baseline Run")

    assert record is not None
    initial_completed = record.metrics.vehicles_completed

    # Reset workbench simulation
    workbench.reset_simulation()
    assert workbench.engine.time == 0.0

    # Captured record remains unaffected
    assert record.metrics.vehicles_completed == initial_completed
    assert record.metrics.duration == 600.0


# ---------------------------------------------------------------------------
# Integration tests on UI Dialog & Workbench
# ---------------------------------------------------------------------------

def test_dialog_empty_state_when_fewer_than_two_runs(workbench):
    """Verify dialog shows empty state message when fewer than 2 completed runs exist."""
    workbench.captured_runs.clear()

    dialog = ScenarioComparisonDialog(workbench)
    try:
        assert dialog.stack.currentWidget() == dialog.empty_page
        assert dialog.combo_baseline.isEnabled() is False
        assert dialog.combo_candidate.isEnabled() is False
        assert dialog.btn_swap.isEnabled() is False

        # Add 1 run -> still empty state
        r1 = SimulationRunRecord("1", "Run 1", "Scen", _make_dummy_metrics())
        workbench.captured_runs.append(r1)
        dialog.refresh_runs()
        assert dialog.stack.currentWidget() == dialog.empty_page
    finally:
        dialog.close()


def test_dialog_two_runs_renders_table_and_chart(workbench):
    """Verify dialog displays full table and comparison chart when 2 completed runs exist."""
    workbench.captured_runs.clear()
    r1 = SimulationRunRecord("1", "Baseline", "Small Net", _make_dummy_metrics(travel_time=20.0, completed=25))
    r2 = SimulationRunRecord("2", "Candidate", "Optimized", _make_dummy_metrics(travel_time=15.0, completed=30))
    workbench.captured_runs.extend([r1, r2])

    dialog = ScenarioComparisonDialog(workbench)
    try:
        assert dialog.stack.currentWidget() == dialog.report_page
        assert dialog.combo_baseline.isEnabled() is True
        assert dialog.combo_candidate.isEnabled() is True
        assert dialog.btn_swap.isEnabled() is True

        # Table populated with metrics
        assert dialog.table.rowCount() > 0
        tt_item = dialog.table.item(0, 0)
        assert "Travel Time" in tt_item.text()

        # Status badge
        status_item = dialog.table.item(0, 5)
        assert "Improved" in status_item.text()

        # Chart updated
        assert dialog.chart_view.comparison is not None
    finally:
        dialog.close()


def test_dialog_selecting_runs_and_swapping(workbench):
    """Verify selecting different runs and clicking Swap updates comparison results."""
    workbench.captured_runs.clear()
    r1 = SimulationRunRecord("1", "Slow Run", "Net A", _make_dummy_metrics(travel_time=25.0))
    r2 = SimulationRunRecord("2", "Fast Run", "Net B", _make_dummy_metrics(travel_time=15.0))
    workbench.captured_runs.extend([r1, r2])

    dialog = ScenarioComparisonDialog(workbench)
    try:
        # Candidate (Fast: 15) vs Baseline (Slow: 25) -> Travel time improved (-10s)
        diff_item = dialog.table.item(0, 3)
        assert "-10.0" in diff_item.text()
        assert "Improved" in dialog.table.item(0, 5).text()

        # Click Swap
        dialog.btn_swap.click()

        # Now Candidate (Slow: 25) vs Baseline (Fast: 15) -> Travel time regressed (+10s)
        diff_item_swapped = dialog.table.item(0, 3)
        assert "+10.0" in diff_item_swapped.text()
        assert "Regressed" in dialog.table.item(0, 5).text()
    finally:
        dialog.close()


def test_workbench_auto_capture_on_simulation_completion(workbench):
    """Verify completing a simulation automatically records a run record."""
    initial_count = len(workbench.captured_runs)

    # Fast forward simulation to finish
    workbench.start_simulation()
    workbench.engine.time = workbench.engine.duration
    workbench.engine.finished = True
    workbench.advance_simulation()

    assert len(workbench.captured_runs) == initial_count + 1
    assert workbench.captured_runs[-1].metrics.status == "Completed"


def test_open_comparison_dialog_via_action_and_button(workbench):
    """Verify opening comparison view from menu action and toolbar button."""
    # Via action
    dlg1 = workbench.open_comparison_dialog()
    assert dlg1.isVisible()
    dlg1.close()

    # Via compare button
    workbench.btn_compare.click()
    assert workbench.comparison_dialog.isVisible()
    workbench.comparison_dialog.close()


def test_comparison_preserves_dirty_state_and_undo_redo(workbench):
    """Verify comparing runs does not alter scenario dirty state or undo/redo stacks."""
    workbench.set_dirty(False)
    initial_can_undo = workbench.can_undo
    initial_can_redo = workbench.can_redo

    # Open dialog and capture run
    workbench.engine.finished = True
    workbench.capture_current_run("Test Run")
    dlg = workbench.open_comparison_dialog()
    dlg.close()

    # Dirty and undo/redo states must remain unchanged
    assert workbench.is_dirty is False
    assert workbench.can_undo == initial_can_undo
    assert workbench.can_redo == initial_can_redo
