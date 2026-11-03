
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from measure_gui_fps import (
    InputEventRecorder,
    acceptance_eligibility,
    cleanup_benchmark_resources,
    measurement_failure_reason,
    verify_isolated_database,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_gui_measurement_detects_engine_pause_before_completion():
    assert measurement_failure_reason(
        expected_speed=4.0,
        actual_speed=4.0,
        engine_running=False,
        engine_finished=False,
        window_minimized=False,
        seconds_since_last_frame=0.0,
    ) == "Engine stopped before completion"


def test_gui_measurement_does_not_hide_speed_change():
    assert measurement_failure_reason(
        expected_speed=4.0,
        actual_speed=1.0,
        engine_running=True,
        engine_finished=False,
        window_minimized=False,
        seconds_since_last_frame=0.0,
    ) == "Playback speed changed from 4x to 1x"


def test_gui_measurement_keeps_frame_stall_failure_for_running_engine():
    assert measurement_failure_reason(
        expected_speed=4.0,
        actual_speed=4.0,
        engine_running=True,
        engine_finished=False,
        window_minimized=False,
        seconds_since_last_frame=31.0,
    ) == "No canvas frames were rendered for over 30 seconds"


@pytest.mark.parametrize(
    "event",
    [
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a"),
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(2.0, 3.0),
            QPointF(12.0, 13.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    ],
    ids=["key", "mouse"],
)
def test_input_recorder_deduplicates_propagation_and_keeps_targets(qapp, event):
    parent = QWidget()
    parent.setObjectName("parent")
    child = QWidget(parent)
    child.setObjectName("child")
    recorder = InputEventRecorder()
    recorder.started_at = time.perf_counter()
    qapp.installEventFilter(recorder)
    try:
        QApplication.sendEvent(child, event)
    finally:
        qapp.removeEventFilter(recorder)
        parent.close()

    assert len(recorder.events) == 1
    record = recorder.events[0]
    assert record["delivery_targets"] == ["child", "parent"]
    assert record["spontaneous"] is False
    assert record["origin"] == "internal_application"
    assert record["unexpected_external_input"] is False
    assert "timestamp" in record


def test_input_recorder_marks_external_origin_without_claiming_human_source(qapp):
    class ExternalKeyEvent:
        def type(self):
            return QEvent.Type.KeyPress

        def spontaneous(self):
            return True

        def timestamp(self):
            return 1234

        def key(self):
            return int(Qt.Key.Key_Control)

        def nativeScanCode(self):
            return 29

        def nativeVirtualKey(self):
            return 17

        def nativeModifiers(self):
            return 0

        def text(self):
            return ""

        def isAutoRepeat(self):
            return False

    parent = QWidget()
    child = QWidget(parent)
    recorder = InputEventRecorder()
    recorder.started_at = time.perf_counter()
    event = ExternalKeyEvent()
    recorder.eventFilter(child, event)
    recorder.eventFilter(parent, event)
    parent.close()

    assert len(recorder.events) == 1
    record = recorder.events[0]
    assert record["origin"] == "external_system"
    assert record["unexpected_external_input"] is True
    assert "operator" not in record


def test_isolated_database_preflight_closes_reopens_and_removes(tmp_path):
    directory = tmp_path / "isolated-history"
    directory.mkdir()

    database = verify_isolated_database(directory)

    assert database == directory / "sqlite-preflight.sqlite3"
    assert not database.exists()


def test_isolated_database_preflight_reports_sqlite_open_failure(tmp_path, monkeypatch):
    import measure_gui_fps

    def fail_connect(*_args, **_kwargs):
        raise OSError("test database path is unavailable")

    monkeypatch.setattr(measure_gui_fps.sqlite3, "connect", fail_connect)
    with pytest.raises(RuntimeError, match="SQLite preflight failed"):
        verify_isolated_database(tmp_path)


def test_benchmark_cleanup_closes_retained_library_store_before_temp_removal(qapp, tmp_path):
    from tms_sim.ui.app import Workbench

    scenario = ROOT / "fixtures" / "valid" / "small_valid_scenario.json"
    workbench = Workbench(scenario)
    database_dir = tmp_path / "isolated-library"
    database_dir.mkdir()
    workbench.library_path = database_dir / "run-history.sqlite3"
    dialog = workbench.open_scenario_library()
    assert workbench.library_path.exists()

    errors = cleanup_benchmark_resources(qapp, workbench, None, None)

    assert dialog.store is not None
    assert errors == []
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        dialog.store.list_scenarios()
    workbench.library_path.unlink()
    assert not workbench.library_path.exists()
    database_dir.rmdir()


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration_completed": False},
        {"duration_completed": None},
        {"average_fps": 14.99},
        {"average_fps": None},
        {"no_unexpected_external_input": False},
        {"no_unexpected_external_input": None},
        {"no_storage_errors": False},
        {"no_execution_failure": False},
        {"cleanup_succeeded": False},
        {"process_succeeded": False},
    ],
)
def test_acceptance_eligibility_fails_if_any_requirement_is_not_verified(overrides):
    conditions = {
        "duration_completed": True,
        "average_fps": 15.0,
        "no_unexpected_external_input": True,
        "no_storage_errors": True,
        "no_execution_failure": True,
        "cleanup_succeeded": True,
        "process_succeeded": True,
    }
    conditions.update(overrides)

    assert acceptance_eligibility(**conditions) is False


def test_acceptance_eligibility_passes_only_when_all_requirements_are_verified():
    assert acceptance_eligibility(
        duration_completed=True,
        average_fps=15.0,
        no_unexpected_external_input=True,
        no_storage_errors=True,
        no_execution_failure=True,
        cleanup_succeeded=True,
        process_succeeded=True,
    ) is True


def test_load_test_script_creates_report(tmp_path):
    output = tmp_path / "load_test.json"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_load_test.py"),
            "--repeat", "2",
            "--output", str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert output.exists()

    report = json.loads(output.read_text(encoding="utf-8"))

    assert len(report["results"]) == 2
    assert all(
        run["vehicles_generated"] == 30
        for run in report["results"]
    )
    assert all(
        run["vehicles_completed"] == 30
        for run in report["results"]
    )

    # Resource measurements should be recorded by the load-test script.
    assert all("cpu_seconds" in run for run in report["results"])
    assert all(
        "peak_python_memory_bytes" in run
        for run in report["results"]
    )


def test_acceptance_report_script_creates_markdown(tmp_path):
    source = tmp_path / "load_test.json"
    output = tmp_path / "acceptance_report.md"

    sample_report = {
        "python_version": "3.13.7",
        "platform": "Test platform",
        "summary": {
            "mean_elapsed_seconds": 0.05,
            "mean_cpu_seconds": 0.04,
            "max_peak_python_memory_bytes": 1024,
        },
        "results": [
            {
                "run": run_number,
                "scenario": "sample.json",
                "simulated_seconds": 600.0,
                "elapsed_seconds": 0.05,
                "cpu_seconds": 0.04,
                "peak_python_memory_bytes": 1024,
                "vehicles_generated": 30,
                "vehicles_entered": 30,
                "vehicles_completed": 30,
                "vehicles_in_network": 0,
            }
            for run_number in (1, 2)
        ],
    }

    source.write_text(
        json.dumps(sample_report),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "acceptance_report.py"),
            "--input", str(source),
            "--output", str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    assert output.exists()

    report = output.read_text(encoding="utf-8")

    assert "Repeatability of vehicle counts: PASS" in report
    assert "All generated vehicles completed: PASS" in report
    assert "GUI frame-rate target (15 FPS): NOT MEASURED" in report
    assert "Total process RAM: NOT MEASURED" in report
    assert "Mean CPU time" in report
    assert "Maximum traced Python memory" in report
    assert "Final acceptance: Pending" in report
