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
13. Scenario dirty state and undo/redo remain unaffected.
14. Average-speed comparison between two simulation runs.
"""

from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
import json
from typing import Any, cast

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from tms_sim.reporting.comparison import (
    ComparisonStatus,
    MetricDirection,
    SimulationRunRecord,
    calculate_metric_comparison,
    compare_runs,
)
from tms_sim.reporting.metrics import SimulationMetrics
from tms_sim.ui.app import Workbench
from tms_sim.ui.comparison import ScenarioComparisonDialog
from tms_sim.storage.store import ScenarioStore


SAMPLE_SCENARIO_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "scenario"
    / "small_valid_scenario.json"
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
    """Provide a fresh Workbench instance for each test."""
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )

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
    average_speed: float | None = None,
) -> SimulationMetrics:
    """Create sample metrics for comparison tests."""
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
        average_speed_mps=average_speed,
    )


# ---------------------------------------------------------------------------
# Unit tests on comparison data models
# ---------------------------------------------------------------------------


def test_metric_comparison_absolute_and_percentage_differences():
    """Verify absolute and percentage differences are calculated accurately."""
    metric = calculate_metric_comparison(
        key="mean_travel_time",
        name="Mean Travel Time",
        unit="s",
        baseline_val=20.0,
        candidate_val=15.0,
        direction=MetricDirection.LOWER_IS_BETTER,
    )

    assert metric.absolute_change == -5.0
    assert metric.percent_change == -25.0
    assert metric.status == ComparisonStatus.IMPROVED

    completed_metric = calculate_metric_comparison(
        key="vehicles_completed",
        name="Vehicles Completed",
        unit="veh",
        baseline_val=20,
        candidate_val=25,
        direction=MetricDirection.HIGHER_IS_BETTER,
    )

    assert completed_metric.absolute_change == 5.0
    assert completed_metric.percent_change == 25.0
    assert completed_metric.status == ComparisonStatus.IMPROVED


def test_run_comparison_includes_issue10_metrics_and_flags_scenario_mismatch():
    baseline_metrics = _make_dummy_metrics(average_speed=5.0)
    baseline_metrics = SimulationMetrics(**{
        **baseline_metrics.__dict__, "throughput_vph": 10.0,
        "average_delay_s": 2.0, "maximum_delay_s": 4.0,
        "queue_length_veh": 1.0,
        "average_queue_length_by_approach": {"A": 1.0},
    })
    candidate_metrics = SimulationMetrics(**{
        **baseline_metrics.__dict__, "throughput_vph": 12.0,
        "average_delay_s": 1.0, "maximum_delay_s": 2.0,
        "queue_length_veh": 0.5,
        "average_queue_length_by_approach": {"A": 0.5},
    })
    comparison = compare_runs(
        SimulationRunRecord("a", "A", "Scenario A", baseline_metrics),
        SimulationRunRecord("b", "B", "Scenario B", candidate_metrics),
    )
    assert comparison.warning and "Scenario names differ" in comparison.warning
    assert comparison.get_metric("throughput_vph").absolute_change == 2.0
    assert comparison.get_metric("average_delay_s").status == ComparisonStatus.IMPROVED
    assert comparison.get_metric("maximum_delay_s").absolute_change == -2.0
    assert comparison.get_metric("queue:A").absolute_change == -0.5


def test_comparison_dialog_loads_two_persisted_runs(workbench, tmp_path):
    workbench.library_path = tmp_path / "runs.sqlite3"
    metrics_a = _make_dummy_metrics(average_speed=5.0)
    metrics_b = _make_dummy_metrics(average_speed=6.0)
    snapshot = json.loads(SAMPLE_SCENARIO_PATH.read_text(encoding="utf-8"))
    with ScenarioStore(workbench.library_path) as store:
        for run_id, label, metrics in (("saved-a", "Saved A", metrics_a), ("saved-b", "Saved B", metrics_b)):
            store.save_run(run_id, "Stored Scenario", label, "2026-10-29T10:00:00", 42,
                           snapshot, asdict(metrics), {"duration_s": 600.0, "time_step_s": 0.5})
    workbench.captured_runs = []
    dialog = workbench.open_comparison_dialog("saved-a", "saved-b")
    assert dialog.combo_baseline.count() == 2
    assert dialog.combo_candidate.count() == 2
    assert dialog.current_comparison.baseline.run_id == "saved-a"
    assert dialog.current_comparison.candidate.run_id == "saved-b"
    assert dialog.current_comparison.get_metric("average_speed_mps").absolute_change == 1.0


def test_zero_baseline_percentage_handling():
    """Verify zero baseline values do not cause division errors."""
    metric = calculate_metric_comparison(
        key="vehicles_completed",
        name="Vehicles Completed",
        unit="veh",
        baseline_val=0,
        candidate_val=10,
        direction=MetricDirection.HIGHER_IS_BETTER,
    )

    assert metric.absolute_change == 10.0
    assert metric.percent_change is None
    assert metric.status == ComparisonStatus.IMPROVED


def test_missing_or_unmodeled_metrics_handled_explicitly():
    """Verify missing metric values are reported as unavailable."""
    metric_one = calculate_metric_comparison(
        key="mean_travel_time",
        name="Mean Travel Time",
        unit="s",
        baseline_val=None,
        candidate_val=16.4,
        direction=MetricDirection.LOWER_IS_BETTER,
    )

    assert metric_one.status == ComparisonStatus.UNAVAILABLE
    assert metric_one.absolute_change is None
    assert metric_one.percent_change is None
    assert not metric_one.is_available

    metric_two = calculate_metric_comparison(
        key="queue_length_veh",
        name="Queue Length",
        unit="veh",
        baseline_val=None,
        candidate_val=None,
        direction=MetricDirection.LOWER_IS_BETTER,
    )

    assert metric_two.status == ComparisonStatus.UNAVAILABLE
    assert metric_two.absolute_change is None
    assert metric_two.percent_change is None


def test_lower_is_better_and_higher_is_better_classification():
    """Verify metric direction determines improvement or regression."""
    worse_travel_time = calculate_metric_comparison(
        "tt",
        "Travel Time",
        "s",
        15.0,
        20.0,
        MetricDirection.LOWER_IS_BETTER,
    )
    assert worse_travel_time.status == ComparisonStatus.REGRESSED

    better_travel_time = calculate_metric_comparison(
        "tt",
        "Travel Time",
        "s",
        20.0,
        15.0,
        MetricDirection.LOWER_IS_BETTER,
    )
    assert better_travel_time.status == ComparisonStatus.IMPROVED

    better_completion = calculate_metric_comparison(
        "completed",
        "Completed Vehicles",
        "veh",
        20,
        25,
        MetricDirection.HIGHER_IS_BETTER,
    )
    assert better_completion.status == ComparisonStatus.IMPROVED

    worse_completion = calculate_metric_comparison(
        "completed",
        "Completed Vehicles",
        "veh",
        25,
        20,
        MetricDirection.HIGHER_IS_BETTER,
    )
    assert worse_completion.status == ComparisonStatus.REGRESSED


def test_equal_metric_values_classified_as_unchanged():
    """Verify equal metric values are classified as unchanged."""
    metric = calculate_metric_comparison(
        "tt",
        "Travel Time",
        "s",
        16.4,
        16.4,
        MetricDirection.LOWER_IS_BETTER,
    )

    assert metric.status == ComparisonStatus.UNCHANGED
    assert metric.absolute_change == 0.0
    assert metric.percent_change == 0.0


def test_duration_incompatibility_warning():
    """Verify different simulation durations produce a warning."""
    baseline = SimulationRunRecord(
        "1",
        "Run 1",
        "Scenario A",
        _make_dummy_metrics(duration=600.0),
    )
    same_duration = SimulationRunRecord(
        "2",
        "Run 2",
        "Scenario A",
        _make_dummy_metrics(duration=600.0),
    )
    different_duration = SimulationRunRecord(
        "3",
        "Run 3",
        "Scenario C",
        _make_dummy_metrics(duration=300.0),
    )

    compatible_comparison = compare_runs(baseline, same_duration)

    assert compatible_comparison.duration_compatible is True
    assert compatible_comparison.warning is None

    incompatible_comparison = compare_runs(baseline, different_duration)

    assert incompatible_comparison.duration_compatible is False
    assert incompatible_comparison.warning is not None
    assert "600.0s vs Candidate: 300.0s" in incompatible_comparison.warning


def test_incomplete_run_rejection():
    """Verify incomplete simulation runs cannot be captured."""
    class FakeEngine:
        finished = False
        running = True
        time = 100.0
        duration = 600.0
        vehicles = []
        cars = []
        events = []

    with pytest.raises(ValueError, match="incomplete"):
        SimulationRunRecord.from_engine(cast(Any, FakeEngine()))


def test_comparison_marks_incomplete_snapshots_as_incompatible():
    incomplete = SimulationRunRecord(
        "partial", "Partial", "Scenario",
        _make_dummy_metrics(status="Running"),
    )
    complete = SimulationRunRecord(
        "complete", "Complete", "Scenario",
        _make_dummy_metrics(status="Completed"),
    )
    comparison = compare_runs(incomplete, complete)
    assert "incomplete" in comparison.warning
    assert all(item.status == ComparisonStatus.INCOMPATIBLE for item in comparison.metrics)


def test_independent_immutable_snapshots(workbench):
    """Verify captured records remain unchanged after a simulation reset."""
    workbench.engine.time = workbench.engine.duration
    workbench.engine.finished = True

    record = workbench.capture_current_run("Baseline Run")

    assert record is not None
    initial_completed = record.metrics.vehicles_completed

    workbench.reset_simulation()

    assert workbench.engine.time == 0.0
    assert record.metrics.vehicles_completed == initial_completed
    assert record.metrics.duration == 600.0


# ---------------------------------------------------------------------------
# Integration tests on UI dialog and Workbench
# ---------------------------------------------------------------------------


def test_dialog_empty_state_when_fewer_than_two_runs(workbench):
    """Verify the dialog shows its empty state with fewer than two runs."""
    workbench.captured_runs.clear()

    dialog = ScenarioComparisonDialog(workbench)

    try:
        assert dialog.stack.currentWidget() == dialog.empty_page
        assert not dialog.combo_baseline.isEnabled()
        assert not dialog.combo_candidate.isEnabled()
        assert not dialog.btn_swap.isEnabled()

        run = SimulationRunRecord(
            "1",
            "Run 1",
            "Scenario",
            _make_dummy_metrics(),
        )
        workbench.captured_runs.append(run)
        dialog.refresh_runs()

        assert dialog.stack.currentWidget() == dialog.empty_page
    finally:
        dialog.close()


def test_dialog_two_runs_renders_table_and_chart(workbench):
    """Verify the dialog displays its table and chart for two runs."""
    workbench.captured_runs.clear()

    baseline = SimulationRunRecord(
        "1",
        "Baseline",
        "Small Net",
        _make_dummy_metrics(travel_time=20.0, completed=25),
    )
    candidate = SimulationRunRecord(
        "2",
        "Candidate",
        "Optimized",
        _make_dummy_metrics(travel_time=15.0, completed=30),
    )

    workbench.captured_runs.extend([baseline, candidate])

    dialog = ScenarioComparisonDialog(workbench)

    try:
        assert dialog.stack.currentWidget() == dialog.report_page
        assert dialog.combo_baseline.isEnabled()
        assert dialog.combo_candidate.isEnabled()
        assert dialog.btn_swap.isEnabled()

        assert dialog.table.rowCount() > 0

        travel_time_item = dialog.table.item(0, 0)
        assert travel_time_item is not None
        assert "Travel Time" in travel_time_item.text()

        status_item = dialog.table.item(0, 5)
        assert status_item is not None
        assert "Improved" in status_item.text()

        assert dialog.chart_view.comparison is not None
    finally:
        dialog.close()


def test_dialog_selecting_runs_and_swapping(workbench):
    """Verify swapping runs updates the comparison results."""
    workbench.captured_runs.clear()

    baseline = SimulationRunRecord(
        "1",
        "Slow Run",
        "Network A",
        _make_dummy_metrics(travel_time=25.0),
    )
    candidate = SimulationRunRecord(
        "2",
        "Fast Run",
        "Network B",
        _make_dummy_metrics(travel_time=15.0),
    )

    workbench.captured_runs.extend([baseline, candidate])

    dialog = ScenarioComparisonDialog(workbench)

    try:
        difference_item = dialog.table.item(0, 3)
        assert difference_item is not None
        assert "-10.0" in difference_item.text()

        status_item = dialog.table.item(0, 5)
        assert status_item is not None
        assert "Improved" in status_item.text()

        dialog.btn_swap.click()

        swapped_difference_item = dialog.table.item(0, 3)
        assert swapped_difference_item is not None
        assert "+10.0" in swapped_difference_item.text()

        swapped_status_item = dialog.table.item(0, 5)
        assert swapped_status_item is not None
        assert "Regressed" in swapped_status_item.text()
    finally:
        dialog.close()


def test_workbench_auto_capture_on_simulation_completion(workbench):
    """Verify a completed simulation is automatically captured."""
    initial_count = len(workbench.captured_runs)

    workbench.start_simulation()
    workbench.engine.time = workbench.engine.duration
    workbench.engine.finished = True
    workbench.advance_simulation()

    assert len(workbench.captured_runs) == initial_count + 1
    assert workbench.captured_runs[-1].metrics.status == "Completed"


def test_open_comparison_dialog_via_action_and_button(workbench):
    """Verify comparison opens from both the menu action and toolbar."""
    dialog = workbench.open_comparison_dialog()

    assert dialog.isVisible()
    dialog.close()

    workbench.btn_compare.click()

    assert workbench.comparison_dialog.isVisible()
    workbench.comparison_dialog.close()


def test_comparison_preserves_dirty_state_and_undo_redo(workbench):
    """Verify comparison does not change dirty state or undo/redo history."""
    workbench.set_dirty(False)

    initial_can_undo = workbench.can_undo
    initial_can_redo = workbench.can_redo

    workbench.engine.finished = True
    workbench.capture_current_run("Test Run")

    dialog = workbench.open_comparison_dialog()
    dialog.close()

    assert workbench.is_dirty is False
    assert workbench.can_undo == initial_can_undo
    assert workbench.can_redo == initial_can_redo


# ---------------------------------------------------------------------------
# Average-speed comparison test
# ---------------------------------------------------------------------------


def test_average_speed_is_included_in_run_comparison():
    """Verify average speed is compared correctly between two completed runs."""
    baseline = SimulationRunRecord(
        "baseline",
        "Baseline",
        "Small Net",
        _make_dummy_metrics(average_speed=5.0),
    )
    candidate = SimulationRunRecord(
        "candidate",
        "Candidate",
        "Small Net",
        _make_dummy_metrics(average_speed=8.0),
    )

    comparison = compare_runs(baseline, candidate)

    speed_metric = next(
        metric
        for metric in comparison.metrics
        if metric.key == "average_speed_mps"
    )

    assert speed_metric.absolute_change == 3.0
    assert speed_metric.percent_change == 60.0
    assert speed_metric.status == ComparisonStatus.IMPROVED
