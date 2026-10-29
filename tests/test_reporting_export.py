"""Automated tests for TMS-Sim Step 5G: Export Simulation Reports.

Covers:
1. CSV headers, rows, units, values, and status for single run export.
2. Missing and unmodeled metrics distinguished from zero values (N/A vs 0).
3. Readable HTML report structure, styling, and safe escaping.
4. Comparison CSV headers, differences, percentage values, and assessments.
5. Comparison HTML report with duration warning and badges.
6. UTF-8 characters and CSV escaping (commas, quotes, newlines).
7. Invalid paths, unhandled types, and file write errors.
8. Stability: Export of Run 1 remains identical after Run 2 is simulated/captured.
9. UI: No completed run guards and warning messages.
10. UI: Fewer than two completed runs guards for comparison.
11. UI: Qt Boolean callback safety (triggered/clicked signals never passed as path).
12. UI: Mocked file dialog export for run and comparison.
13. UI: Overwrite confirmation handling.
"""
from __future__ import annotations

import csv
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from tms_sim.reporting.comparison import (
    ComparisonStatus,
    MetricComparison,
    MetricDirection,
    ScenarioComparison,
    SimulationRunRecord,
    calculate_metric_comparison,
    compare_runs,
)
from tms_sim.reporting.export import (
    ExportError,
    export_comparison_csv,
    export_comparison_html,
    export_run_csv,
    export_run_html,
    generate_comparison_csv,
    generate_comparison_html,
    generate_run_csv,
    generate_run_html,
)
from tms_sim.reporting.metrics import SimulationMetrics
from tms_sim.ui.app import Workbench
from tms_sim.ui.comparison import ScenarioComparisonDialog

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


def _make_dummy_run(
    travel_time: float | None = 16.4,
    completed: int = 30,
    in_network: int = 0,
    entered: int = 30,
    generated: int = 30,
    duration: float = 600.0,
    status: str = "Completed",
    scenario_name: str = "Test Scenario",
    label: str = "Run 1: Test Scenario",
) -> SimulationRunRecord:
    metrics = SimulationMetrics(
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
    return SimulationRunRecord(
        run_id="run_12345",
        label=label,
        scenario_name=scenario_name,
        metrics=metrics,
        timestamp="2026-10-26T08:00:00",
    )


# ---------------------------------------------------------------------------
# 1. Single Run CSV Export Tests
# ---------------------------------------------------------------------------

def test_generate_run_csv_headers_and_modeled_metrics():
    """Verify CSV headers, modeled metrics, units, and status."""
    run = _make_dummy_run(travel_time=16.4, completed=25, in_network=5, entered=30, generated=30)
    csv_text = generate_run_csv(run)

    reader = list(csv.reader(csv_text.splitlines()))
    assert len(reader) >= 10
    header = reader[0]
    assert header == ["Metric Key", "Metric", "Value", "Unit", "Status", "Notes"]

    data_map = {row[1]: row for row in reader[1:]}

    # Metadata
    assert data_map["Scenario Name"][2] == "Test Scenario"
    assert data_map["Run Label"][2] == "Run 1: Test Scenario"
    assert data_map["Run Status"][2] == "Completed"
    assert data_map["Simulation Duration"][2] == "600.0"
    assert data_map["Simulation Duration"][3] == "s"

    # Modeled metrics
    assert data_map["Vehicles Completed"][2] == "25"
    assert data_map["Vehicles Completed"][3] == "veh"
    assert data_map["Vehicles Completed"][4] == "Available"

    assert data_map["Vehicles in Network"][2] == "5"
    assert data_map["Vehicles in Network"][3] == "veh"
    assert data_map["Vehicles in Network"][4] == "Available"

    assert data_map["Average Travel Time"][0] == "mean_travel_time_s"
    assert data_map["Average Travel Time"][2] == "16.4"
    assert data_map["Average Travel Time"][3] == "s"
    assert data_map["Average Travel Time"][4] == "Available"


def test_exported_csv_contains_measured_issue10_values(tmp_path):
    metrics = SimulationMetrics(
        status="Completed", simulated_time=100.0, duration=100.0,
        vehicles_generated=4, total_scheduled=4, vehicles_entered=4,
        vehicles_completed=3, vehicles_in_network=1,
        mean_travel_time=12.34, average_speed_mps=7.89,
        throughput_vph=108.0, average_delay_s=2.34, maximum_delay_s=4.56,
        queue_length_veh=0.75, average_queue_length_by_approach={"A": 0.5},
    )
    run = SimulationRunRecord("csv-run", "CSV run", "Scenario", metrics)
    path = tmp_path / "summary.csv"
    export_run_csv(run, path)
    with path.open(encoding="utf-8", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))
    values = {row["Metric Key"]: row for row in rows}
    assert values["mean_travel_time_s"]["Value"] == "12.3"
    assert values["average_delay_s"]["Value"] == "2.3"
    assert values["maximum_delay_s"]["Value"] == "4.6"
    assert values["throughput_vph"]["Value"] == "108.0"
    assert values["average_speed_mps"]["Value"] == "7.9"
    assert values["average_queue_length_veh:A"]["Value"] == "0.5"


def test_missing_and_unmodeled_metrics_distinguished_from_zero():
    """Verify unavailable metrics are 'N/A' and zero values are clearly '0', not confused."""
    # When in_network is 0, it must be "0", NOT "N/A"
    # When travel_time is None (0 trips completed), it must be "N/A", NOT "0"
    run = _make_dummy_run(travel_time=None, completed=0, in_network=0, entered=0, generated=30)
    csv_text = generate_run_csv(run)

    reader = list(csv.reader(csv_text.splitlines()))
    data_map = {row[1]: row for row in reader[1:]}

    # Zero value check
    assert data_map["Vehicles in Network"][2] == "0"
    assert data_map["Vehicles in Network"][4] == "Available"

    # None / Missing travel time check
    assert data_map["Average Travel Time"][2] == "N/A"
    assert data_map["Average Travel Time"][4] == "Unavailable"

    # Unmodeled metrics check
    assert data_map["Throughput"][2] == "N/A"
    assert data_map["Throughput"][3] == "veh/h"
    assert data_map["Throughput"][4] == "Unavailable"

    assert data_map["Average Vehicle Delay"][2] == "N/A"
    assert data_map["Average Vehicle Delay"][3] == "s"
    assert data_map["Average Vehicle Delay"][4] == "Unavailable"

    assert data_map["Average Queue Length"][2] == "N/A"
    assert data_map["Average Queue Length"][3] == "veh"
    assert data_map["Average Queue Length"][4] == "Unavailable"


def test_invalid_export_path_reports_export_error():
    from tms_sim.reporting.export import ExportError

    with pytest.raises(ExportError, match="Invalid export path"):
        export_run_csv(_make_dummy_run(), None)


# ---------------------------------------------------------------------------
# 2. Single Run HTML Report Tests
# ---------------------------------------------------------------------------

def test_generate_run_html_structure_and_escaping():
    """Verify HTML report includes self-contained styling and escapes user-controlled strings."""
    malicious_scenario = '<script>alert("hack")</script> & "special"'
    malicious_label = "<b>Bold Run</b> & 'quotes'"
    run = _make_dummy_run(scenario_name=malicious_scenario, label=malicious_label, travel_time=18.5)

    html_content = generate_run_html(run)

    # HTML tags and structure
    assert "<!DOCTYPE html>" in html_content
    assert "<html" in html_content
    assert "<style>" in html_content
    assert "Simulation Run Report" in html_content
    assert "18.5 s" in html_content

    # Verify escaping: raw unescaped script tag MUST NOT appear
    assert '<script>alert("hack")</script>' not in html_content
    assert "&lt;script&gt;alert(&quot;hack&quot;)&lt;/script&gt;" in html_content
    assert "&lt;b&gt;Bold Run&lt;/b&gt;" in html_content


# ---------------------------------------------------------------------------
# 3. Scenario Comparison CSV Export Tests
# ---------------------------------------------------------------------------

def test_generate_comparison_csv_headers_and_differences():
    """Verify comparison CSV headers, differences, percentage values, and assessments."""
    run_base = _make_dummy_run(travel_time=20.0, completed=20, in_network=10, label="Baseline")
    run_cand = _make_dummy_run(travel_time=15.0, completed=25, in_network=5, label="Candidate")
    comp = compare_runs(run_base, run_cand)

    csv_text = generate_comparison_csv(comp)
    reader = list(csv.reader(csv_text.splitlines()))

    header = reader[0]
    assert header == [
        "Metric",
        "Baseline",
        "Candidate",
        "Absolute Change",
        "Percentage Change",
        "Unit",
        "Status",
        "Notes",
    ]

    data_map = {row[0]: row for row in reader[1:]}

    # Mean travel time: 20.0 -> 15.0 => diff -5.0, pct -25.0%, lower is better => improved
    tt_row = data_map["Mean Travel Time"]
    assert tt_row[1] == "20.0"
    assert tt_row[2] == "15.0"
    assert tt_row[3] == "-5.0"
    assert tt_row[4] == "-25.0%"
    assert tt_row[5] == "s"
    assert tt_row[6] == "improved"

    # Vehicles completed: 20 -> 25 => diff +5, pct +25.0%, higher is better => improved
    comp_row = data_map["Vehicles Completed"]
    assert comp_row[1] == "20"
    assert comp_row[2] == "25"
    assert comp_row[3] == "+5"
    assert comp_row[4] == "+25.0%"
    assert comp_row[5] == "veh"
    assert comp_row[6] == "improved"

    # Unmodeled metric in comparison
    tp_row = data_map["Hourly Throughput"]
    assert tp_row[1] == "N/A"
    assert tp_row[2] == "N/A"
    assert tp_row[3] == "N/A"
    assert tp_row[4] == "N/A"
    assert tp_row[5] == "veh/h"
    assert tp_row[6] == "unavailable"


def test_comparison_csv_zero_baseline_safe_percentage():
    """Verify comparison percentage change handles zero baseline without division error."""
    run_base = _make_dummy_run(completed=0, travel_time=None)
    run_cand = _make_dummy_run(completed=10, travel_time=20.0)
    comp = compare_runs(run_base, run_cand)

    csv_text = generate_comparison_csv(comp)
    reader = list(csv.reader(csv_text.splitlines()))
    data_map = {row[0]: row for row in reader[1:]}

    # Completed from 0 to 10
    comp_row = data_map["Vehicles Completed"]
    assert comp_row[1] == "0"
    assert comp_row[2] == "10"
    assert comp_row[3] == "+10"
    assert comp_row[4] == "N/A (base 0)"


# ---------------------------------------------------------------------------
# 4. Comparison HTML Report Tests
# ---------------------------------------------------------------------------

def test_generate_comparison_html_warning_and_badges():
    """Verify comparison HTML contains run details, duration warning when incompatible, and status badges."""
    run_base = _make_dummy_run(duration=300.0, label="Baseline 300s")
    run_cand = _make_dummy_run(duration=600.0, label="Candidate 600s")
    comp = compare_runs(run_base, run_cand)

    assert not comp.duration_compatible
    assert comp.warning is not None

    html_content = generate_comparison_html(comp)

    assert "<!DOCTYPE html>" in html_content
    assert "Simulation Scenario Comparison Report" in html_content
    assert "Baseline 300s" in html_content
    assert "Candidate 600s" in html_content
    assert "warning-banner" in html_content
    assert "Configured durations differ" in html_content
    assert "badge-improved" in html_content or "badge-unchanged" in html_content or "badge-unavailable" in html_content


# ---------------------------------------------------------------------------
# 5. UTF-8 and CSV Escaping Tests
# ---------------------------------------------------------------------------

def test_utf8_text_and_csv_escaping(tmp_path):
    """Verify Unicode strings and CSV control characters (commas, quotes, newlines) round-trip accurately."""
    complex_name = 'Scenario with, commas, "quotes", and\nnewline, plus Unicode: München 🚦 自動車'
    run = _make_dummy_run(scenario_name=complex_name, label=f"Label: {complex_name}")

    out_csv = tmp_path / "test_escaping.csv"
    export_run_csv(run, out_csv)

    assert out_csv.exists()
    content = out_csv.read_text(encoding="utf-8")
    assert "München" in content
    assert "自動車" in content

    # Read back with standard csv.reader
    with open(out_csv, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    data_map = {r[1]: r for r in rows[1:]}
    assert data_map["Scenario Name"][2] == complex_name


# ---------------------------------------------------------------------------
# 6. File Export & Error Handling Tests
# ---------------------------------------------------------------------------

def test_export_functions_write_valid_files(tmp_path):
    """Verify all four export functions create files with content on disk."""
    run_base = _make_dummy_run(label="Base")
    run_cand = _make_dummy_run(label="Cand")
    comp = compare_runs(run_base, run_cand)

    path_run_csv = tmp_path / "run.csv"
    path_run_html = tmp_path / "run.html"
    path_comp_csv = tmp_path / "comp.csv"
    path_comp_html = tmp_path / "comp.html"

    export_run_csv(run_base, path_run_csv)
    export_run_html(run_base, path_run_html)
    export_comparison_csv(comp, path_comp_csv)
    export_comparison_html(comp, path_comp_html)

    assert path_run_csv.stat().st_size > 0
    assert path_run_html.stat().st_size > 0
    assert path_comp_csv.stat().st_size > 0
    assert path_comp_html.stat().st_size > 0


def test_invalid_paths_raise_export_error(tmp_path, monkeypatch):
    """Verify file write errors raise ExportError cleanly."""
    run = _make_dummy_run()

    # Invalid run parameter
    with pytest.raises(ValueError):
        generate_run_csv(None)  # type: ignore

    with pytest.raises(ValueError):
        generate_comparison_csv(None)  # type: ignore

    # Unwritable destination
    invalid_dest = tmp_path / "non_existent_folder" / "sub" / "run.csv"
    # Monkeypatch mkdir to fail
    def fail_mkdir(*args, **kwargs):
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    with pytest.raises(ExportError) as exc_info:
        export_run_csv(run, invalid_dest)
    assert "Failed to write export file" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 7. Snapshot Stability After Subsequent Runs
# ---------------------------------------------------------------------------

def test_run_snapshot_stability_after_subsequent_runs():
    """Verify exported content for run 1 remains completely identical after run 2 is created."""
    run1 = _make_dummy_run(travel_time=20.0, completed=10, label="Run 1")
    csv_1_before = generate_run_csv(run1)

    # Simulate run 2 with completely different metrics
    run2 = _make_dummy_run(travel_time=12.0, completed=50, label="Run 2")
    _ = generate_run_csv(run2)

    csv_1_after = generate_run_csv(run1)
    assert csv_1_before == csv_1_after


# ---------------------------------------------------------------------------
# 8. UI Integration Tests
# ---------------------------------------------------------------------------

def test_ui_export_run_guards_when_no_completed_run(workbench, monkeypatch):
    """Verify warning is shown and False is returned when no completed run is available."""
    warning_calls = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warning_calls.append(args))

    # At initial state, engine is not finished
    assert workbench.engine is not None
    assert not workbench.engine.finished

    res_csv = workbench.export_current_run_csv()
    assert res_csv is False
    assert len(warning_calls) == 1
    assert "No completed simulation run" in str(warning_calls[0])

    res_html = workbench.export_current_run_html()
    assert res_html is False
    assert len(warning_calls) == 2


def test_ui_export_comparison_guards_when_fewer_than_two_runs(workbench, monkeypatch):
    """Verify warning is shown when attempting to export comparison with < 2 runs."""
    warning_calls = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warning_calls.append(args))

    workbench.captured_runs = []
    res_csv = workbench.export_comparison_csv()
    assert res_csv is False
    assert len(warning_calls) == 1

    res_html = workbench.export_comparison_html()
    assert res_html is False
    assert len(warning_calls) == 2


def test_ui_boolean_callback_protection(workbench, tmp_path, monkeypatch):
    """Verify passing a boolean (from Qt triggered/clicked signals) does not crash or use boolean as path."""
    # Set up a completed run
    run = _make_dummy_run()
    workbench.captured_runs = [run]

    # Mock QFileDialog to return a real path
    target = tmp_path / "test_bool.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), "CSV"))

    # When connected to action.triggered or button.clicked, Qt passes checked: bool = False
    # If the function does not guard against bool, Path(False) would fail or be used
    res = workbench.export_current_run_csv(False)
    assert res is True
    assert target.exists()


def test_ui_export_run_flow(workbench, tmp_path, monkeypatch):
    """Verify complete UI export run workflow for CSV and HTML."""
    run = _make_dummy_run(travel_time=15.2, completed=30)
    workbench.captured_runs = [run]

    target_csv = tmp_path / "exported_run.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target_csv), "CSV"))

    success = workbench.export_current_run_csv()
    assert success is True
    assert target_csv.exists()
    assert "15.2" in target_csv.read_text(encoding="utf-8")
    assert "Simulation run exported" in workbench.status_label.text()

    target_html = tmp_path / "exported_run.html"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target_html), "HTML"))

    success_html = workbench.export_current_run_html()
    assert success_html is True
    assert target_html.exists()
    assert "<!DOCTYPE html>" in target_html.read_text(encoding="utf-8")


def test_ui_comparison_dialog_export_flow(workbench, tmp_path, monkeypatch):
    """Verify export buttons in ScenarioComparisonDialog function correctly."""
    run1 = _make_dummy_run(travel_time=20.0, label="Run 1")
    run2 = _make_dummy_run(travel_time=16.0, label="Run 2")
    workbench.captured_runs = [run1, run2]

    dialog = ScenarioComparisonDialog(workbench)
    assert dialog.current_comparison is not None
    assert dialog.btn_export_csv.isEnabled()
    assert dialog.btn_export_html.isEnabled()

    target_csv = tmp_path / "comp_out.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target_csv), "CSV"))

    res = dialog.export_csv()
    assert res is True
    assert target_csv.exists()
    assert "comparison exported" in dialog.lbl_status.text().lower()

    target_html = tmp_path / "comp_out.html"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target_html), "HTML"))

    res_html = dialog.export_html()
    assert res_html is True
    assert target_html.exists()
    assert "<!DOCTYPE html>" in target_html.read_text(encoding="utf-8")
    dialog.close()


def test_ui_export_cancel_and_overwrite_denial(workbench, tmp_path, monkeypatch):
    """Verify canceling the dialog or denying overwrite does not alter file."""
    run = _make_dummy_run()
    workbench.captured_runs = [run]

    # User cancels dialog
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", ""))
    res = workbench.export_current_run_csv()
    assert res is False
    assert "cancelled" in workbench.status_label.text().lower()

    # File exists and user denies overwrite
    existing_file = tmp_path / "existing.csv"
    existing_file.write_text("initial content", encoding="utf-8")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(existing_file), "CSV"))
    monkeypatch.setattr(workbench, "confirm_overwrite", lambda path: False)

    res = workbench.export_current_run_csv()
    assert res is False
    assert existing_file.read_text(encoding="utf-8") == "initial content"
    assert "not overwritten" in workbench.status_label.text().lower()
