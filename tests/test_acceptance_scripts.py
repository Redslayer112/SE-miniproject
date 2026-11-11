
import json
import ctypes
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent, QMouseEvent, QWindow
from PySide6.QtWidgets import QApplication, QWidget

from measure_gui_fps import (
    InputEventRecorder,
    SC_CLOSE,
    WM_CLOSE,
    WM_ENDSESSION,
    WM_QUERYENDSESSION,
    WM_SYSCOMMAND,
    WindowsCloseEventRecorder,
    _WindowsMessage,
    _finalize_benchmark_result,
    _write_json_exclusive,
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

    assert recorder.events == []
    assert len(recorder.delivery_traces) == 2
    records = recorder.delivery_traces
    assert [record["target"]["label"] for record in records] == [
        "child",
        "parent",
    ]
    assert all(record["identity_uncertain"] is False for record in records)
    assert all(record["spontaneous"] is False for record in records)
    assert all(record["origin"] == "internal_application" for record in records)
    assert all(record["unexpected_external_input"] is False for record in records)
    assert all("timestamp" in record for record in records)


def test_matching_event_at_parent_after_child_accepts_is_not_merged(qapp):
    class AcceptingWidget(QWidget):
        def keyPressEvent(self, event):
            event.accept()

    parent = QWidget()
    child = AcceptingWidget(parent)
    recorder = InputEventRecorder()
    recorder.started_at = time.perf_counter()
    qapp.installEventFilter(recorder)
    try:
        first = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.NoModifier,
            "a",
        )
        first.setTimestamp(4321)
        QApplication.sendEvent(child, first)
        assert first.isAccepted()

        second = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.NoModifier,
            "a",
        )
        second.setTimestamp(4321)
        QApplication.sendEvent(parent, second)
    finally:
        qapp.removeEventFilter(recorder)
        parent.close()

    assert recorder.events == []
    assert len(recorder.delivery_traces) == 2
    assert [record["target"]["label"] for record in recorder.delivery_traces] == [
        "AcceptingWidget",
        "QWidget",
    ]
    assert all(record["identity_uncertain"] is False for record in recorder.delivery_traces)


def test_same_class_unnamed_widgets_keep_distinct_target_ids(qapp):
    parent = QWidget()
    child = QWidget(parent)
    recorder = InputEventRecorder()
    recorder.started_at = time.perf_counter()
    qapp.installEventFilter(recorder)
    try:
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.NoModifier,
            "a",
        )
        QApplication.sendEvent(child, event)
    finally:
        qapp.removeEventFilter(recorder)
        parent.close()

    assert recorder.events == []
    assert len(recorder.delivery_traces) == 2
    targets = [record["target"] for record in recorder.delivery_traces]
    assert [target["label"] for target in targets] == ["QWidget", "QWidget"]
    assert [target["class_name"] for target in targets] == ["QWidget", "QWidget"]
    assert len({target["target_id"] for target in targets}) == 2


def test_input_recorder_keeps_identical_distinct_events_separate(qapp):
    parent = QWidget()
    child = QWidget(parent)
    child.setObjectName("child")
    parent.setObjectName("parent")
    recorder = InputEventRecorder()
    recorder.started_at = time.perf_counter()
    qapp.installEventFilter(recorder)
    try:
        for _ in range(2):
            event = QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_A,
                Qt.KeyboardModifier.NoModifier,
                "a",
            )
            event.setTimestamp(1234)
            QApplication.sendEvent(child, event)
    finally:
        qapp.removeEventFilter(recorder)
        parent.close()

    assert recorder.events == []
    assert len(recorder.delivery_traces) == 4
    assert [event["target"]["label"] for event in recorder.delivery_traces] == [
        "child",
        "parent",
        "child",
        "parent",
    ]
    assert len({event["delivery_id"] for event in recorder.delivery_traces}) == 4
    assert all(event["identity_uncertain"] is False for event in recorder.delivery_traces)


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

    assert recorder.events == []
    assert len(recorder.delivery_traces) == 2
    assert all(record["origin"] == "external_system" for record in recorder.delivery_traces)
    assert all(record["unexpected_external_input"] is True for record in recorder.delivery_traces)
    assert all(record["identity_uncertain"] for record in recorder.delivery_traces)
    assert all("operator" not in record for record in recorder.delivery_traces)


def test_routed_qt_input_counts_one_canonical_ingress_and_preserves_all_targets(qapp):
    class ExternalKeyEvent:
        def type(self):
            return QEvent.Type.KeyPress

        def spontaneous(self):
            return True

        def timestamp(self):
            return 1234

        def key(self):
            return int(Qt.Key.Key_A)

        def nativeScanCode(self):
            return 30

        def nativeVirtualKey(self):
            return 65

        def nativeModifiers(self):
            return 0

        def text(self):
            return "a"

        def isAutoRepeat(self):
            return False

    parent = QWidget()
    child = QWidget(parent)
    window = QWindow()
    recorder = InputEventRecorder()
    recorder.started_at = time.perf_counter()
    event = ExternalKeyEvent()
    for target in (window, child, parent):
        recorder.eventFilter(target, event)

    assert len(recorder.events) == 1
    assert recorder.events[0]["classification"] == "platform_window_ingress"
    assert recorder.events[0]["delivery_targets"][0]["class_name"] == "QWindow"
    assert len(recorder.delivery_traces) == 3
    assert [trace["target"]["class_name"] for trace in recorder.delivery_traces] == [
        "QWindow", "QWidget", "QWidget",
    ]
    assert recorder.delivery_traces[0]["canonical_event_id"] == recorder.events[0]["event_id"]
    assert recorder.delivery_traces[1]["canonical_event_id"] is None
    assert recorder.delivery_traces[2]["canonical_event_id"] is None
    assert recorder.events[0]["identity_uncertain"] is True
    window.destroy()
    parent.close()


def test_distinct_matching_qwindow_events_remain_distinct_canonical_inputs(qapp):
    class ExternalKeyEvent:
        def type(self): return QEvent.Type.KeyPress
        def spontaneous(self): return True
        def timestamp(self): return 1234
        def key(self): return int(Qt.Key.Key_A)
        def nativeScanCode(self): return 30
        def nativeVirtualKey(self): return 65
        def nativeModifiers(self): return 0
        def text(self): return "a"
        def isAutoRepeat(self): return False

    window = QWindow()
    recorder = InputEventRecorder()
    recorder.started_at = time.perf_counter()
    recorder.eventFilter(window, ExternalKeyEvent())
    recorder.eventFilter(window, ExternalKeyEvent())

    assert len(recorder.events) == 2
    assert [event["event_id"] for event in recorder.events] == [1, 2]
    assert len(recorder.delivery_traces) == 2
    window.destroy()


def test_close_event_records_state_focus_and_recent_input_as_unknown(qapp):
    class ExternalKeyEvent:
        def type(self): return QEvent.Type.KeyPress
        def spontaneous(self): return True
        def timestamp(self): return 1234
        def key(self): return int(Qt.Key.Key_A)
        def nativeScanCode(self): return 30
        def nativeVirtualKey(self): return 65
        def nativeModifiers(self): return 0
        def text(self): return "a"
        def isAutoRepeat(self): return False

    focus = QWidget()
    focus.setObjectName("named-focus")
    engine = SimpleNamespace(running=True, time=42.125)
    window = SimpleNamespace(
        engine=engine,
        _pending_close_initiator=None,
        _benchmark_close_event_tokens=[],
        focusWidget=lambda: focus,
        isVisible=lambda: True,
        isMinimized=lambda: False,
        isActiveWindow=lambda: True,
    )
    recorder = InputEventRecorder(window=window, close_input_context_seconds=5.0)
    recorder.started_at = time.perf_counter()
    recorder.events.append({
        "elapsed_wall_seconds": -10.0,
        "event_id": 99,
        "key": int(Qt.Key.Key_B),
    })
    recorder.eventFilter(QWindow(), ExternalKeyEvent())
    recorder.eventFilter(window, QCloseEvent())
    event_token = window._benchmark_close_event_tokens.pop()
    recorder.record_close_outcome(event_token, True)

    assert len(recorder.window_close_events) == 1
    close = recorder.window_close_events[0]
    assert close["timestamp_utc"]
    assert close["event_type"] == "close"
    assert close["event_token"] == event_token
    assert close["close_event_accepted"] is True
    assert close["initiator_status"] == "unknown"
    assert close["initiator"] == "unknown"
    assert close["window_state"] == {
        "visible": True,
        "minimized": False,
        "active": True,
    }
    assert close["focused_widget"] == {
        "class_name": "QWidget",
        "object_name": "named-focus",
    }
    assert close["engine_running"] is True
    assert close["simulation_time_s"] == 42.125
    assert len(close["preceding_input_events"]) == 1
    assert close["preceding_input_events"][0]["key"] == int(Qt.Key.Key_A)
    assert close["preceding_input_delivery_traces"]


def test_close_event_marks_known_application_action_when_available():
    window = SimpleNamespace(
        engine=SimpleNamespace(running=False, time=0.0),
        _pending_close_initiator="file_menu_exit",
        _benchmark_close_event_tokens=[],
        focusWidget=lambda: None,
        isVisible=lambda: True,
        isMinimized=lambda: False,
        isActiveWindow=lambda: False,
    )
    recorder = InputEventRecorder(window=window)
    recorder.started_at = time.perf_counter()
    recorder.eventFilter(window, QCloseEvent())
    event_token = window._benchmark_close_event_tokens.pop()
    recorder.record_close_outcome(event_token, False)

    close = recorder.window_close_events[0]
    assert close["event_token"] == event_token
    assert close["close_event_accepted"] is False
    assert close["initiator_status"] == "known_application_action"
    assert close["initiator"] == "file_menu_exit"


def test_sequential_close_outcomes_are_correlated_by_event_token():
    window = SimpleNamespace(
        engine=SimpleNamespace(running=False, time=0.0),
        _pending_close_initiator=None,
        _benchmark_close_event_tokens=[],
        focusWidget=lambda: None,
        isVisible=lambda: True,
        isMinimized=lambda: False,
        isActiveWindow=lambda: False,
    )
    recorder = InputEventRecorder(window=window)
    recorder.started_at = time.perf_counter()

    recorder.eventFilter(window, QCloseEvent())
    accepted_token = window._benchmark_close_event_tokens.pop()
    recorder.record_close_outcome(accepted_token, True)
    recorder.eventFilter(window, QCloseEvent())
    ignored_token = window._benchmark_close_event_tokens.pop()
    recorder.record_close_outcome(ignored_token, False)

    assert accepted_token != ignored_token
    assert [event["event_token"] for event in recorder.window_close_events] == [
        accepted_token,
        ignored_token,
    ]
    assert [event["close_event_accepted"] for event in recorder.window_close_events] == [
        True,
        False,
    ]


def test_windows_close_native_messages_are_passive_recognized_and_bounded(qapp):
    """Synthetic MSG coverage validates parsing; native delivery still needs a Windows run."""
    window = QWidget()
    input_recorder = InputEventRecorder(window=window)
    input_recorder.started_at = time.perf_counter()
    native_recorder = WindowsCloseEventRecorder(input_recorder, window)
    message = _WindowsMessage()
    message.hwnd = native_recorder.window_handle
    message.message = WM_SYSCOMMAND
    message.wParam = SC_CLOSE
    message.lParam = 123
    unchanged = (message.hwnd, message.message, message.wParam, message.lParam)

    result = native_recorder.nativeEventFilter(
        b"windows_generic_MSG", ctypes.addressof(message)
    )

    assert result == (False, 0)
    assert (message.hwnd, message.message, message.wParam, message.lParam) == unchanged
    assert [record["message_name"] for record in native_recorder.events] == [
        "WM_SYSCOMMAND/SC_CLOSE"
    ]
    assert native_recorder.nativeEventFilter(b"not_windows", 0) == (False, 0)
    assert native_recorder.record_message(
        event_type_name="windows_generic_MSG",
        hwnd=native_recorder.window_handle,
        message_id=WM_SYSCOMMAND,
        wparam=0xF020,
        lparam=0,
    ) is None

    message_ids = [WM_CLOSE, WM_QUERYENDSESSION, WM_ENDSESSION]
    for message_id in message_ids * 24:
        native_recorder.record_message(
            event_type_name="windows_generic_MSG",
            hwnd=native_recorder.window_handle,
            message_id=message_id,
            wparam=0,
            lparam=0,
        )
    assert native_recorder.events.maxlen == 64
    assert len(native_recorder.events) == 64
    assert {
        record["message_name"] for record in native_recorder.events
    } == {"WM_CLOSE", "WM_QUERYENDSESSION", "WM_ENDSESSION"}
    window.destroy()


def test_native_and_non_client_events_correlate_to_close_token(qapp):
    non_client_press = getattr(QEvent.Type, "NonClientAreaMouseButtonPress", None)
    if non_client_press is None:
        pytest.skip("Qt build does not expose non-client mouse events")

    window = QWidget()
    window._benchmark_close_event_tokens = []
    input_recorder = InputEventRecorder(window=window)
    input_recorder.started_at = time.perf_counter()
    native_recorder = WindowsCloseEventRecorder(input_recorder, window)
    input_recorder.windows_native_recorder = native_recorder
    native_recorder.record_message(
        event_type_name="windows_generic_MSG",
        hwnd=native_recorder.window_handle,
        message_id=WM_SYSCOMMAND,
        wparam=SC_CLOSE,
        lparam=0,
    )
    mouse_event = QMouseEvent(
        non_client_press,
        QPointF(4.0, 5.0),
        QPointF(4.0, 5.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    input_recorder.eventFilter(window, mouse_event)
    input_recorder.eventFilter(window, QCloseEvent())

    close = input_recorder.window_close_events[0]
    event_token = close["event_token"]
    assert len(close["preceding_native_close_messages"]) == 1
    assert close["preceding_native_close_messages"][0]["close_event_token"] == event_token
    assert close["preceding_non_client_mouse_events"][0]["close_event_token"] == event_token
    assert native_recorder.events[0]["close_event_token"] == event_token
    assert input_recorder.non_client_mouse_events[0]["close_event_token"] == event_token
    native_recorder.record_message(
        event_type_name="windows_generic_MSG",
        hwnd=native_recorder.window_handle,
        message_id=WM_ENDSESSION,
        wparam=1,
        lparam=0,
    )
    assert close["following_native_close_messages"][0]["close_event_token"] == event_token
    window.destroy()


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


def test_benchmark_cleanup_removes_close_observer_after_exception(qapp):
    from tms_sim.ui.app import Workbench

    scenario = ROOT / "fixtures" / "valid" / "small_valid_scenario.json"
    workbench = Workbench(scenario)
    recorder = InputEventRecorder(window=workbench)
    native_recorder = WindowsCloseEventRecorder(recorder, workbench)
    recorder.windows_native_recorder = native_recorder
    qapp.installNativeEventFilter(native_recorder)
    workbench._benchmark_close_event_observer = recorder.record_close_outcome
    workbench._benchmark_close_event_tokens.append("close-pending")

    with pytest.raises(RuntimeError, match="simulated worker failure"):
        try:
            raise RuntimeError("simulated worker failure")
        finally:
            cleanup_errors = cleanup_benchmark_resources(
                qapp, workbench, None, recorder
            )

    assert cleanup_errors == []
    assert workbench._benchmark_close_event_observer is None
    assert workbench._benchmark_close_event_tokens == []
    assert recorder.windows_native_recorder is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration_completed": False},
        {"duration_completed": None},
        {"average_fps": 14.99},
        {"average_fps": None},
        {"no_unexpected_external_input": False},
        {"no_unexpected_external_input": None},
        {"input_recording_unambiguous": False},
        {"input_recording_unambiguous": None},
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
        "input_recording_unambiguous": True,
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
        input_recording_unambiguous=True,
        no_storage_errors=True,
        no_execution_failure=True,
        cleanup_succeeded=True,
        process_succeeded=True,
    ) is True


@pytest.mark.parametrize(
    ("failure", "worker_exit_code", "storage_errors", "app_cleanup", "temp_cleanup_error"),
    [
        ("worker", 7, [], True, None),
        ("storage", 0, [{"operation": "save", "error": "disk I/O error"}], True, None),
        ("cleanup", 0, [], False, None),
    ],
)
def test_final_artifact_is_ineligible_on_worker_storage_or_cleanup_failure(
    tmp_path,
    failure,
    worker_exit_code,
    storage_errors,
    app_cleanup,
    temp_cleanup_error,
):
    result = {
        "scenario": "synthetic-test-scenario",
        "finished": True,
        "duration_s": 30.0,
        "simulation_time_s": 30.0,
        "final_metrics": {"full_run_fps": 20.0},
        "input_events": [],
        "input_delivery_traces": [],
        "window_restoration_count": 0,
        "storage_errors": storage_errors,
        "benchmark_execution_succeeded": True,
        "application_cleanup_succeeded": app_cleanup,
        "application_cleanup_errors": [],
    }
    final_result = _finalize_benchmark_result(
        result,
        worker_exit_code=worker_exit_code,
        temp_cleanup_error=temp_cleanup_error,
    )
    artifact = tmp_path / f"{failure}-failure.json"
    _write_json_exclusive(artifact, final_result)
    persisted = json.loads(artifact.read_text(encoding="utf-8"))

    assert persisted["acceptance_eligible"] is False
    assert persisted["acceptance_checks"]["process_succeeded"] is (worker_exit_code == 0)
    assert persisted["acceptance_checks"]["no_storage_errors"] is (not storage_errors)
    assert persisted["acceptance_checks"]["cleanup_succeeded"] is app_cleanup


def _completed_acceptance_candidate(duration_s, playback_speed):
    return {
        "finished": True,
        "duration_s": duration_s,
        "simulation_time_s": duration_s,
        "requested_playback_speed_multiplier": playback_speed,
        "playback_speed_multiplier": playback_speed,
        "final_metrics": {"full_run_fps": 20.0},
        "input_events": [],
        "input_delivery_traces": [],
        "window_restoration_count": 0,
        "storage_errors": [],
        "benchmark_execution_succeeded": True,
        "application_cleanup_succeeded": True,
        "application_cleanup_errors": [],
    }


def test_short_completed_diagnostic_is_not_tc_perf_01_eligible(tmp_path):
    result = _finalize_benchmark_result(
        _completed_acceptance_candidate(30.0, 1.0),
        worker_exit_code=0,
        temp_cleanup_error=None,
    )
    artifact = tmp_path / "short-diagnostic.json"
    _write_json_exclusive(artifact, result)
    persisted = json.loads(artifact.read_text(encoding="utf-8"))

    assert persisted["acceptance_checks"]["duration_completed"] is True
    assert persisted["acceptance_checks"]["tc_perf_01_run_configuration"] is False
    assert persisted["acceptance_eligible"] is False


@pytest.mark.parametrize("playback_speed", [0.5, 2.0, 4.0])
def test_non_1x_completed_run_is_not_tc_perf_01_eligible(tmp_path, playback_speed):
    result = _finalize_benchmark_result(
        _completed_acceptance_candidate(3600.0, playback_speed),
        worker_exit_code=0,
        temp_cleanup_error=None,
    )
    artifact = tmp_path / f"diagnostic-{playback_speed}x.json"
    _write_json_exclusive(artifact, result)
    persisted = json.loads(artifact.read_text(encoding="utf-8"))

    assert persisted["acceptance_checks"]["tc_perf_01_run_configuration"] is False
    assert persisted["acceptance_eligible"] is False


def test_complete_clean_one_hour_1x_artifact_can_be_eligible(tmp_path):
    result = _finalize_benchmark_result(
        _completed_acceptance_candidate(3600.0, 1.0),
        worker_exit_code=0,
        temp_cleanup_error=None,
    )
    artifact = tmp_path / "eligible-reference-run.json"
    _write_json_exclusive(artifact, result)
    persisted = json.loads(artifact.read_text(encoding="utf-8"))

    assert persisted["acceptance_checks"]["tc_perf_01_run_configuration"] is True
    assert persisted["acceptance_eligible"] is True


def test_final_artifact_is_ineligible_when_input_delivery_identity_is_uncertain(tmp_path):
    result = {
        "finished": True,
        "duration_s": 30.0,
        "simulation_time_s": 30.0,
        "final_metrics": {"full_run_fps": 20.0},
        "input_events": [{
            "unexpected_external_input": False,
            "identity_uncertain": True,
        }],
        "input_delivery_traces": [{
            "spontaneous": True,
            "identity_uncertain": True,
        }],
        "window_restoration_count": 0,
        "storage_errors": [],
        "benchmark_execution_succeeded": True,
        "application_cleanup_succeeded": True,
        "application_cleanup_errors": [],
    }
    final_result = _finalize_benchmark_result(
        result,
        worker_exit_code=0,
        temp_cleanup_error=None,
    )
    artifact = tmp_path / "ambiguous-input.json"
    _write_json_exclusive(artifact, final_result)
    persisted = json.loads(artifact.read_text(encoding="utf-8"))

    assert persisted["acceptance_checks"]["input_recording_unambiguous"] is False
    assert persisted["acceptance_eligible"] is False


def test_final_artifact_fails_closed_when_input_evidence_is_missing(tmp_path):
    result = {
        "finished": True,
        "duration_s": 30.0,
        "simulation_time_s": 30.0,
        "final_metrics": {"full_run_fps": 20.0},
        "window_restoration_count": 0,
        "storage_errors": [],
        "benchmark_execution_succeeded": True,
        "application_cleanup_succeeded": True,
        "application_cleanup_errors": [],
    }
    final_result = _finalize_benchmark_result(
        result,
        worker_exit_code=0,
        temp_cleanup_error=None,
    )
    artifact = tmp_path / "missing-input-evidence.json"
    _write_json_exclusive(artifact, final_result)
    persisted = json.loads(artifact.read_text(encoding="utf-8"))

    assert persisted["acceptance_checks"]["no_unexpected_external_input"] is False
    assert persisted["acceptance_checks"]["input_recording_unambiguous"] is False
    assert persisted["acceptance_eligible"] is False


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
