
import argparse
import copy
import ctypes
from datetime import datetime, timezone
from collections import deque
import logging
import platform
import shutil
import sqlite3
import subprocess
import sys
import json
import math
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

try:
    import psutil
except ImportError:  # Process RSS is supplemental; the benchmark itself has no extra dependency.
    psutil = None

from PySide6.QtCore import QAbstractNativeEventFilter, QEvent, QObject, QTimer
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QApplication

from tms_sim.ui.app import Workbench


DEFAULT_SCENARIO = ROOT / "fixtures/valid/performance_10_intersections.json"
DEFAULT_OUTPUT = ROOT / "artifacts/gui_fps_full_run.json"
SUPPORTED_SPEEDS = (0.5, 1.0, 2.0, 4.0)
CLOSE_DIAGNOSTIC_CONTEXT_SECONDS = 10.0
MAX_NON_CLIENT_MOUSE_EVENTS = 128
MAX_WINDOWS_CLOSE_MESSAGES = 64

WM_CLOSE = 0x0010
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_SYSCOMMAND = 0x0112
SC_CLOSE = 0xF060

WINDOWS_CLOSE_MESSAGE_NAMES = {
    WM_CLOSE: "WM_CLOSE",
    WM_QUERYENDSESSION: "WM_QUERYENDSESSION",
    WM_ENDSESSION: "WM_ENDSESSION",
}


class _WindowsPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int32), ("y", ctypes.c_int32)]


class _WindowsMessage(ctypes.Structure):
    """Pointer-sized subset of Win32 MSG used by the benchmark's passive filter."""

    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint32),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint32),
        ("pt", _WindowsPoint),
    ]


def measurement_failure_reason(
    *,
    expected_speed: float,
    actual_speed: float,
    engine_running: bool,
    engine_finished: bool,
    window_minimized: bool,
    seconds_since_last_frame: float,
) -> str | None:
    """Classify invalid measurements without masking pauses or renderer stalls."""
    if actual_speed != expected_speed:
        return f"Playback speed changed from {expected_speed:g}x to {actual_speed:g}x"
    if not engine_running and not engine_finished:
        return "Engine stopped before completion"
    if window_minimized:
        return "Workbench remained minimized after automatic restore"
    if seconds_since_last_frame > 30:
        return "No canvas frames were rendered for over 30 seconds"
    return None


class InputEventRecorder(QObject):
    """Keep canonical Qt input records separate from per-target delivery traces.

    Qt does not expose a portable native-action identity. A spontaneous event
    seen at a QWindow is counted once as a canonical Qt ingress; every callback
    remains in ``delivery_traces``. Spontaneous non-window deliveries remain
    trace-only and uncertain, so they cannot silently disappear from eligibility.
    No event is merged by metadata.
    """

    def __init__(self, window=None, close_input_context_seconds: float = 10.0):
        super().__init__()
        self.window = window
        self.close_input_context_seconds = close_input_context_seconds
        self.started_at = None
        # ``events`` remains the artifact's legacy canonical-input field.
        self.events = []
        self.delivery_traces = []
        self.window_close_events = []
        self._close_event_by_token = {}
        self._next_close_event_id = 1
        self.non_client_mouse_events = deque(maxlen=MAX_NON_CLIENT_MOUSE_EVENTS)
        self.windows_native_recorder = None
        self._target_identity_by_object = {}
        self._target_references = {}
        self._next_target_id = 1
        self._next_event_id = 1

    def _target_record(self, watched):
        object_key = id(watched)
        target_id = self._target_identity_by_object.get(object_key)
        if target_id is not None and self._target_references[target_id] is not watched:
            target_id = None
        if target_id is None:
            # PySide normally reuses wrappers, but compare live QObject wrappers
            # as a fallback so one native widget keeps one session identity.
            for candidate_id, candidate in self._target_references.items():
                try:
                    same_object = candidate is watched or candidate == watched
                except RuntimeError:
                    same_object = candidate is watched
                if same_object:
                    target_id = candidate_id
                    self._target_identity_by_object[object_key] = candidate_id
                    break
        if target_id is None:
            target_id = self._next_target_id
            self._next_target_id += 1
            self._target_identity_by_object[object_key] = target_id
            # Keep a strong reference so Python cannot reuse the id during this
            # recorder session. Only the session-local integer is serialized.
            self._target_references[target_id] = watched
        object_name = getattr(watched, "objectName", lambda: "")()
        class_name = type(watched).__name__
        return {
            "target_id": target_id,
            "label": object_name or class_name,
            "object_name": object_name,
            "class_name": class_name,
        }

    @staticmethod
    def _input_metadata(event):
        def enum_value(value):
            return int(value.value if hasattr(value, "value") else value)

        metadata = {}
        if hasattr(event, "timestamp"):
            metadata["timestamp"] = int(event.timestamp())
        if hasattr(event, "deviceType"):
            device = event.device() if hasattr(event, "device") else None
            metadata["device_type"] = str(event.deviceType())
            if device is not None:
                metadata["device_name"] = device.name()
        if hasattr(event, "key"):
            metadata["key"] = int(event.key())
            metadata["native_scan_code"] = int(event.nativeScanCode())
            metadata["native_virtual_key"] = int(event.nativeVirtualKey())
            metadata["native_modifiers"] = int(event.nativeModifiers())
            metadata["text"] = event.text()
            metadata["auto_repeat"] = bool(event.isAutoRepeat())
        if hasattr(event, "button"):
            metadata["button"] = enum_value(event.button())
            metadata["buttons"] = enum_value(event.buttons())
            if hasattr(event, "source"):
                metadata["mouse_source"] = str(event.source())
            if hasattr(event, "position"):
                point = event.position()
                metadata["position"] = [float(point.x()), float(point.y())]
        return metadata

    def eventFilter(self, watched, event):
        if (
            self.started_at is not None
            and watched is self.window
            and event.type() == QEvent.Type.Close
        ):
            event_token = f"close-{self._next_close_event_id:06d}"
            self._next_close_event_id += 1
            watched._benchmark_close_event_tokens.append(event_token)
            self._record_window_close(watched, event, event_token)
        elif (
            self.started_at is not None
            and self._is_workbench_native_target(watched)
            and event.type() in NON_CLIENT_MOUSE_EVENT_NAMES
        ):
            self._record_non_client_mouse_event(watched, event)
        elif self.started_at is not None and event.type() in (
            QEvent.Type.KeyPress,
            QEvent.Type.MouseButtonPress,
        ):
            spontaneous = bool(event.spontaneous())
            target = self._target_record(watched)
            delivery_id = self._next_event_id
            self._next_event_id += 1
            is_window_ingress = isinstance(watched, QWindow) and spontaneous
            trace = {
                "delivery_id": delivery_id,
                "elapsed_wall_seconds": round(time.perf_counter() - self.started_at, 3),
                "event_type": (
                    "key_press"
                    if event.type() == QEvent.Type.KeyPress
                    else "mouse_press"
                ),
                "origin": "external_system" if spontaneous else "internal_application",
                "spontaneous": spontaneous,
                "unexpected_external_input": spontaneous,
                "identity_uncertain": spontaneous,
                "canonical_event_id": None,
                "target": target,
                **self._input_metadata(event),
            }
            if spontaneous:
                trace["classification"] = (
                    "platform_window_ingress" if is_window_ingress
                    else "unattributed_external_delivery"
                )
                if is_window_ingress:
                    # This is a canonical Qt window ingress, not proof of one
                    # physical/human action. Preserve that limitation explicitly.
                    canonical_event_id = len(self.events) + 1
                    self.events.append({
                        **trace,
                        "event_id": canonical_event_id,
                        "canonical_event_id": canonical_event_id,
                        "delivery_id": delivery_id,
                        "native_event_identity_available": False,
                        "identity_uncertain": True,
                        "identity_uncertainty_reason": (
                            "Qt does not expose a portable native input-action identity"
                        ),
                        "delivery_targets": [target],
                    })
                    trace["canonical_event_id"] = canonical_event_id
            else:
                trace["classification"] = "internal_application_delivery"
            self.delivery_traces.append(trace)
        return False

    def _is_workbench_native_target(self, watched):
        if watched is self.window:
            return True
        try:
            return watched == self.window.windowHandle()
        except (AttributeError, RuntimeError):
            return False

    def _record_non_client_mouse_event(self, watched, event):
        elapsed = round(time.perf_counter() - self.started_at, 3)
        event_name = NON_CLIENT_MOUSE_EVENT_NAMES[event.type()]
        record = {
            "elapsed_wall_seconds": elapsed,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "event_type": event_name,
            "origin": "external_system" if event.spontaneous() else "internal_application",
            "spontaneous": bool(event.spontaneous()),
            "identity_uncertain": bool(event.spontaneous()),
            "target": self._target_record(watched),
            **self._input_metadata(event),
        }
        self.non_client_mouse_events.append(record)
        self._correlate_following_non_client_event(record)

    def _correlate_following_non_client_event(self, record):
        elapsed = record["elapsed_wall_seconds"]
        for close in reversed(self.window_close_events):
            delta = elapsed - close["elapsed_wall_seconds"]
            if (
                0 <= delta <= self.close_input_context_seconds
                and record.get("close_event_token") is None
            ):
                record["close_event_token"] = close["event_token"]
                record["correlation_direction"] = "following"
                close.setdefault("following_non_client_mouse_events", []).append(dict(record))
                return

    def _record_window_close(self, window, event, event_token):
        """Capture state and nearby input evidence without inferring who closed the window."""
        elapsed = round(time.perf_counter() - self.started_at, 3)
        engine = getattr(window, "engine", None)
        focused = None
        try:
            focus_widget = window.focusWidget()
            if focus_widget is not None:
                focused = {
                    "class_name": type(focus_widget).__name__,
                    "object_name": focus_widget.objectName(),
                }
        except (AttributeError, RuntimeError):
            pass

        initiator = getattr(window, "_pending_close_initiator", None)
        context_start = elapsed - self.close_input_context_seconds
        preceding_non_client_events = []
        for input_record in self.non_client_mouse_events:
            if (
                context_start <= input_record["elapsed_wall_seconds"] <= elapsed
                and input_record.get("close_event_token") is None
            ):
                input_record["close_event_token"] = event_token
                input_record["correlation_direction"] = "preceding"
                preceding_non_client_events.append(dict(input_record))
        record = {
            "event_token": event_token,
            "elapsed_wall_seconds": elapsed,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "event_type": "close",
            "event_spontaneous": (
                bool(event.spontaneous()) if hasattr(event, "spontaneous") else None
            ),
            "initiator_status": (
                "known_application_action" if initiator else "unknown"
            ),
            "initiator": initiator or "unknown",
            "window_state": {
                "visible": bool(window.isVisible()),
                "minimized": bool(window.isMinimized()),
                "active": bool(window.isActiveWindow()),
            },
            "focused_widget": focused,
            "engine_running": bool(getattr(engine, "running", False)),
            "simulation_time_s": round(float(getattr(engine, "time", 0.0)), 3)
            if engine is not None else None,
            "preceding_input_context_seconds": self.close_input_context_seconds,
            "preceding_input_events": [
                dict(record) for record in self.events
                if context_start <= record.get("elapsed_wall_seconds", -1) <= elapsed
            ],
            "preceding_input_delivery_traces": [
                dict(record) for record in self.delivery_traces
                if context_start <= record.get("elapsed_wall_seconds", -1) <= elapsed
            ],
            "preceding_non_client_mouse_events": preceding_non_client_events,
            "preceding_native_close_messages": (
                self.windows_native_recorder.correlate_preceding_close_messages(
                    event_token, elapsed, self.close_input_context_seconds
                ) if self.windows_native_recorder is not None else []
            ),
        }
        self.window_close_events.append(record)
        self._close_event_by_token[event_token] = record

    def record_close_outcome(self, event_token: str | None, accepted: bool):
        """Attach a close handler's outcome to the matching event token."""
        record = self._close_event_by_token.get(event_token)
        if record is not None:
            record["close_event_accepted"] = bool(accepted)

    def non_client_mouse_event_records(self):
        return [dict(record) for record in self.non_client_mouse_events]


NON_CLIENT_MOUSE_EVENT_NAMES = {
    event_type: name
    for name in (
        "NonClientAreaMouseButtonPress",
        "NonClientAreaMouseButtonRelease",
        "NonClientAreaMouseButtonDblClick",
    )
    if (event_type := getattr(QEvent.Type, name, None)) is not None
}


class WindowsCloseEventRecorder(QAbstractNativeEventFilter):
    """Bounded, passive observer for close-related Win32 messages on the Workbench HWND."""

    def __init__(self, input_recorder: InputEventRecorder, window):
        super().__init__()
        self.input_recorder = input_recorder
        self.window_handle = int(window.winId())
        self.events = deque(maxlen=MAX_WINDOWS_CLOSE_MESSAGES)
        self.parse_errors = 0

    @staticmethod
    def _event_type_name(event_type):
        data = event_type.data() if hasattr(event_type, "data") else event_type
        if isinstance(data, (bytes, bytearray)):
            return data.decode("ascii", errors="replace")
        return str(data)

    @staticmethod
    def _message_address(message):
        if isinstance(message, ctypes.c_void_p):
            return message.value
        return int(message)

    @staticmethod
    def _message_name(message_id, wparam):
        if message_id == WM_SYSCOMMAND:
            return "WM_SYSCOMMAND/SC_CLOSE" if (wparam & 0xFFF0) == SC_CLOSE else None
        return WINDOWS_CLOSE_MESSAGE_NAMES.get(message_id)

    def nativeEventFilter(self, event_type, message):
        """Observe matching messages and always return false so Qt handles them normally."""
        event_type_name = self._event_type_name(event_type)
        if event_type_name not in {"windows_generic_MSG", "windows_dispatcher_MSG"}:
            return False, 0
        if self.input_recorder.started_at is None:
            return False, 0
        try:
            message_pointer = ctypes.cast(
                self._message_address(message), ctypes.POINTER(_WindowsMessage)
            )
            native_message = message_pointer.contents
            self.record_message(
                event_type_name=event_type_name,
                hwnd=int(native_message.hwnd or 0),
                message_id=int(native_message.message),
                wparam=int(native_message.wParam),
                lparam=int(native_message.lParam),
            )
        except Exception:
            self.parse_errors += 1
        return False, 0

    def record_message(self, *, event_type_name, hwnd, message_id, wparam, lparam):
        """Record one recognized message for the benchmark Workbench without consuming it."""
        name = self._message_name(message_id, wparam)
        if name is None or hwnd != self.window_handle:
            return None
        started_at = self.input_recorder.started_at
        if started_at is None:
            return None
        record = {
            "elapsed_wall_seconds": round(time.perf_counter() - started_at, 3),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type_name,
            "message_name": name,
            "message_id": f"0x{message_id:04X}",
            "hwnd": f"0x{hwnd:X}",
            "wParam": f"0x{wparam:X}",
            "lParam": f"0x{lparam & ((1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1):X}",
            "close_event_token": None,
        }
        self.events.append(record)
        self._correlate_following_message(record)
        return record

    def correlate_preceding_close_messages(self, event_token, close_elapsed, context_seconds):
        context_start = close_elapsed - context_seconds
        matched = []
        for record in self.events:
            if (
                context_start <= record["elapsed_wall_seconds"] <= close_elapsed
                and record["close_event_token"] is None
            ):
                record["close_event_token"] = event_token
                record["correlation_direction"] = "preceding"
                matched.append(dict(record))
        return matched

    def _correlate_following_message(self, record):
        elapsed = record["elapsed_wall_seconds"]
        for close in reversed(self.input_recorder.window_close_events):
            delta = elapsed - close["elapsed_wall_seconds"]
            if (
                0 <= delta <= self.input_recorder.close_input_context_seconds
                and record["close_event_token"] is None
            ):
                record["close_event_token"] = close["event_token"]
                record["correlation_direction"] = "following"
                close.setdefault("following_native_close_messages", []).append(dict(record))
                return


def acceptance_eligibility(
    *,
    duration_completed: bool | None,
    average_fps: float | None,
    no_unexpected_external_input: bool | None,
    input_recording_unambiguous: bool | None,
    no_storage_errors: bool | None,
    no_execution_failure: bool | None,
    cleanup_succeeded: bool | None,
    process_succeeded: bool | None,
) -> bool:
    """Return true only when every required acceptance condition is verified."""
    return (
        duration_completed is True
        and average_fps is not None
        and average_fps >= 15.0
        and no_unexpected_external_input is True
        and input_recording_unambiguous is True
        and no_storage_errors is True
        and no_execution_failure is True
        and cleanup_succeeded is True
        and process_succeeded is True
    )


def verify_isolated_database(directory: Path) -> Path:
    """Exercise SQLite create/write/close/reopen/remove in a known directory."""
    database = directory / "sqlite-preflight.sqlite3"
    try:
        connection = sqlite3.connect(database)
        try:
            connection.execute("CREATE TABLE probe (value TEXT NOT NULL)")
            connection.execute("INSERT INTO probe VALUES (?)", ("ok",))
            connection.commit()
        finally:
            connection.close()
        connection = sqlite3.connect(database)
        try:
            row = connection.execute("SELECT value FROM probe").fetchone()
        finally:
            connection.close()
        if row != ("ok",):
            raise sqlite3.DatabaseError("SQLite preflight read-back did not match")
        database.unlink()
        if database.exists():
            raise OSError("SQLite preflight database could not be removed")
    except Exception as exc:
        raise RuntimeError(f"Isolated SQLite preflight failed: {exc}") from exc
    return database


def cleanup_benchmark_resources(app, window, timer, recorder) -> list[str]:
    """Stop timers and close benchmark-owned Qt resources before temp cleanup."""
    errors = []
    if timer is not None:
        try:
            timer.stop()
        except Exception as exc:
            errors.append(f"stop benchmark timer: {exc}")
    if window is not None:
        try:
            window._benchmark_close_event_observer = None
            window._benchmark_close_event_tokens.clear()
        except Exception as exc:
            errors.append(f"clear benchmark close diagnostics: {exc}")
        try:
            window.timer.stop()
        except Exception as exc:
            errors.append(f"stop Workbench timer: {exc}")
    if app is not None and recorder is not None:
        try:
            app.removeEventFilter(recorder)
        except Exception as exc:
            errors.append(f"remove input event filter: {exc}")
        native_recorder = recorder.windows_native_recorder
        if native_recorder is not None:
            try:
                app.removeNativeEventFilter(native_recorder)
            except Exception as exc:
                errors.append(f"remove Windows close event filter: {exc}")
            finally:
                recorder.windows_native_recorder = None
    if window is not None:
        # Benchmark cleanup must never block on an unsaved-change prompt.
        window.save_prompt_handler = lambda: "discard"
        for attr in ("library_dialog", "history_dialog", "comparison_dialog"):
            dialog = getattr(window, attr, None)
            if dialog is not None:
                try:
                    if not dialog.close():
                        errors.append(f"close retained {attr} was rejected")
                except Exception as exc:
                    errors.append(f"close retained {attr}: {exc}")
    if app is not None:
        try:
            # Close modal warnings or other top-level windows that may remain.
            for widget in list(app.topLevelWidgets()):
                if widget is not window:
                    try:
                        widget.close()
                    except Exception as exc:
                        errors.append(f"close top-level {type(widget).__name__}: {exc}")
            if window is not None and not window.close():
                errors.append("Workbench close was rejected")
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
        except Exception as exc:
            errors.append(f"process Qt cleanup events: {exc}")
    return errors


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Measure a full GUI simulation run.")
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--playback-speed", type=float, choices=SUPPORTED_SPEEDS, default=1.0,
        help="Playback multiplier; values other than 1x are diagnostic and do not satisfy TC-PERF-01.",
    )
    parser.add_argument(
        "--duration-s", type=float, default=None,
        help="Optional short diagnostic duration override; omitted uses the scenario duration.",
    )
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_stage-output", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--_history-dir", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.scenario = args.scenario.resolve()
    args.output = args.output.resolve()
    if not args.scenario.is_file():
        parser.error(f"Scenario file not found: {args.scenario}")
    if args.duration_s is not None and args.duration_s <= 0:
        parser.error("--duration-s must be positive")
    if args._worker and (args._stage_output is None or args._history_dir is None):
        parser.error("Internal worker requires stage-output and history-dir")
    return args


def _write_json_exclusive(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)


def _finalize_benchmark_result(
    result: dict,
    *,
    worker_exit_code: int,
    temp_cleanup_error: str | None,
) -> dict:
    """Derive the final acceptance fields from measured worker outcomes."""
    result["process_exit_code"] = worker_exit_code
    result["process_succeeded"] = worker_exit_code == 0
    result["supervisor_temporary_cleanup_succeeded"] = temp_cleanup_error is None
    if temp_cleanup_error:
        result.setdefault("application_cleanup_errors", []).append(temp_cleanup_error)
    result["cleanup_succeeded"] = (
        result.get("application_cleanup_succeeded") is True
        and temp_cleanup_error is None
    )
    input_events = result.get("input_events")
    input_traces = result.get("input_delivery_traces")
    input_events_valid = isinstance(input_events, list)
    input_traces_valid = isinstance(input_traces, list)
    events = input_events if input_events_valid else []
    traces = input_traces if input_traces_valid else []
    result["unexpected_external_input"] = (
        not input_events_valid
        or not input_traces_valid
        or any(event.get("unexpected_external_input") is not False for event in events)
        or any(trace.get("spontaneous") is True for trace in traces)
    )
    result["no_unexpected_external_input"] = (
        not result["unexpected_external_input"]
        and result.get("window_restoration_count") == 0
    )
    result["input_recording_unambiguous"] = (
        input_events_valid
        and input_traces_valid
        and all(event.get("identity_uncertain") is False for event in events)
        and all(trace.get("identity_uncertain") is False for trace in traces)
    )
    storage_errors = result.get("storage_errors")
    result["no_storage_errors"] = (
        isinstance(storage_errors, list) and not storage_errors
    )
    metrics = result.get("final_metrics") or {}
    try:
        requested_duration_s = float(result.get("duration_s"))
        requested_speed = float(result.get("requested_playback_speed_multiplier"))
        actual_speed = float(result.get("playback_speed_multiplier"))
        tc_perf_01_configuration = (
            math.isfinite(requested_duration_s)
            and requested_duration_s >= 3600.0
            and requested_speed == 1.0
            and actual_speed == 1.0
        )
    except (TypeError, ValueError):
        tc_perf_01_configuration = False
    result["acceptance_checks"] = {
        "tc_perf_01_run_configuration": tc_perf_01_configuration,
        "duration_completed": (
            result.get("finished") is True
            and float(result.get("simulation_time_s") or 0.0)
            >= float(result.get("duration_s") or float("inf"))
        ),
        "average_fps_at_least_15": (
            metrics.get("full_run_fps") is not None
            and float(metrics["full_run_fps"]) >= 15.0
        ),
        "no_unexpected_external_input": result["no_unexpected_external_input"],
        "input_recording_unambiguous": result["input_recording_unambiguous"],
        "no_storage_errors": result["no_storage_errors"],
        "no_benchmark_execution_failure": (
            result.get("benchmark_execution_succeeded") is True
        ),
        "cleanup_succeeded": result["cleanup_succeeded"],
        "process_succeeded": result["process_succeeded"],
    }
    result["acceptance_eligible"] = tc_perf_01_configuration and acceptance_eligibility(
        duration_completed=result["acceptance_checks"]["duration_completed"],
        average_fps=metrics.get("full_run_fps"),
        no_unexpected_external_input=(
            result["acceptance_checks"]["no_unexpected_external_input"]
        ),
        input_recording_unambiguous=(
            result["acceptance_checks"]["input_recording_unambiguous"]
        ),
        no_storage_errors=result["acceptance_checks"]["no_storage_errors"],
        no_execution_failure=(
            result["acceptance_checks"]["no_benchmark_execution_failure"]
        ),
        cleanup_succeeded=result["acceptance_checks"]["cleanup_succeeded"],
        process_succeeded=result["acceptance_checks"]["process_succeeded"],
    )
    result["acceptance_note"] = (
        "Performance measurements are reported independently. Eligibility is finalized only "
        "for a requested one-hour 1x run and after full duration, FPS, input provenance, "
        "unambiguous event recording, storage, "
        "execution, cleanup, and worker-exit checks."
    )
    return result


def _run_gui_worker(args) -> int:
    """Run the visible Qt measurement in a child process supervised by main()."""
    stage_output = args._stage_output
    history_dir = args._history_dir
    history_dir.mkdir(parents=True, exist_ok=True)
    storage_errors = []
    execution_error = None
    cleanup_errors = []
    result = None
    app = None
    window = None
    timer = None
    recorder = None
    app_logger = logging.getLogger("tms_sim.ui.app")

    class AppStorageErrorHandler(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                storage_errors.append({
                    "operation": record.getMessage(),
                    "error": self.format(record),
                })

    error_handler = AppStorageErrorHandler(level=logging.ERROR)
    error_handler.setFormatter(logging.Formatter("%(message)s"))

    samples = []
    started_at = None
    last_frame_count = 0
    last_frame_progress_at = None
    window_restoration_count = 0
    window_visible_at_start = False
    window_active_at_start = False
    process = psutil.Process() if psutil is not None else None
    peak_rss_bytes = None
    process_cpu_seconds = 0.0
    failure_reason = None
    app_exec_code = None
    windows_native_diagnostics_setup_error = None

    def make_result():
        engine = getattr(window, "engine", None)
        duration = float(getattr(engine, "duration", 0.0))
        finished = bool(getattr(engine, "finished", False))
        simulated_time = float(getattr(engine, "time", 0.0))
        metrics = (
            window.canvas.get_rendering_performance_metrics()
            if window is not None else {}
        )
        started = float(started_at) if started_at is not None else None
        return {
            "scenario": str(args.scenario),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "processor": platform.processor(),
            "machine": platform.machine(),
            "started_at": datetime.fromtimestamp(
                time.time() - (time.perf_counter() - started), timezone.utc
            ).isoformat() if started is not None else None,
            "playback_speed_multiplier": getattr(engine, "speed", None),
            "requested_playback_speed_multiplier": args.playback_speed,
            "seed": window.scenario_data.get("simulation", {}).get("seed")
            if window is not None else args.seed,
            "duration_s": duration,
            "acceptance_eligible": False,
            "run_history_database_isolated": True,
            "run_history_database_path": str(window.library_path)
            if window is not None else None,
            "sqlite_preflight_succeeded": True,
            "window_restoration_count": window_restoration_count,
            "window_visible_before_start": window_visible_at_start,
            "window_active_before_start": window_active_at_start,
            "measurement_method": "full-run FPS = (total frames - 1) / elapsed wall time between first and last paint events",
            "finished": finished,
            "simulation_time_s": round(simulated_time, 2),
            "vehicles_generated": len(getattr(engine, "vehicles", [])),
            "vehicles_in_network": len(getattr(engine, "cars", [])),
            "measurement_wall_seconds": round(
                time.perf_counter() - started, 2
            ) if started is not None else 0.0,
            "peak_process_rss_bytes": peak_rss_bytes,
            "process_cpu_seconds": process_cpu_seconds if process is not None else None,
            "final_metrics": metrics,
            "input_events": recorder.events if recorder is not None else [],
            "input_delivery_traces": (
                recorder.delivery_traces if recorder is not None else []
            ),
            "non_client_mouse_events": (
                recorder.non_client_mouse_event_records() if recorder is not None else []
            ),
            "windows_native_close_messages": (
                list(recorder.windows_native_recorder.events)
                if recorder is not None and recorder.windows_native_recorder is not None
                else []
            ),
            "windows_native_close_diagnostic_parse_errors": (
                recorder.windows_native_recorder.parse_errors
                if recorder is not None and recorder.windows_native_recorder is not None
                else 0
            ),
            "windows_native_close_diagnostic_setup_error": windows_native_diagnostics_setup_error,
            "window_close_events": (
                recorder.window_close_events if recorder is not None else []
            ),
            "input_event_recording_method": (
                "One canonical record per spontaneous QWindow ingress; all Qt target deliveries "
                "are retained separately. Qt does not expose portable native-action identity."
            ),
            "unexpected_external_input": any(
                trace.get("spontaneous") is True
                for trace in (recorder.delivery_traces if recorder is not None else [])
            ),
            "input_recording_unambiguous": (
                not any(event.get("identity_uncertain") for event in
                        (recorder.events if recorder is not None else []))
                and not any(trace.get("identity_uncertain") for trace in
                            (recorder.delivery_traces if recorder is not None else []))
            ),
            "engine_running_transitions": (
                list(getattr(engine, "running_state_transitions", []))
            ),
            "pause_provenance": (
                list(getattr(window, "pause_provenance", [])) if window is not None else []
            ),
            "samples": samples,
            "measurement_failure_reason": failure_reason,
            "benchmark_execution_succeeded": (
                execution_error is None
                and failure_reason is None
                and finished
                and app_exec_code == 0
            ),
            "execution_error": execution_error,
            "application_cleanup_succeeded": not cleanup_errors,
            "application_cleanup_errors": cleanup_errors,
            "storage_errors": storage_errors,
            "acceptance_note": (
                "FPS is a measurement field; acceptance_eligible is finalized by the parent process "
                "only after the worker process and temporary resources finish successfully."
            ),
        }

    def quit_with_failure(message):
        nonlocal failure_reason, result
        failure_reason = message
        if timer is not None:
            timer.stop()
        result = make_result()
        if app is not None:
            app.quit()

    try:
        verify_isolated_database(history_dir)
        app = QApplication.instance() or QApplication(sys.argv)
        window = Workbench(str(args.scenario))
        window.library_path = history_dir / "run-history.sqlite3"
        app_logger.addHandler(error_handler)

        if args.seed is not None or args.duration_s is not None:
            scenario_data = copy.deepcopy(window.scenario_data)
            simulation = scenario_data.setdefault("simulation", {})
            if args.seed is not None:
                simulation["seed"] = args.seed
            if args.duration_s is not None:
                simulation["duration_s"] = args.duration_s
            if not window.load_scenario_data(scenario_data, args.scenario.name):
                raise RuntimeError("Workbench rejected the benchmark scenario settings")

        window.show()
        window.raise_()
        window.activateWindow()
        recorder = InputEventRecorder(window=window)
        window._benchmark_close_event_observer = recorder.record_close_outcome
        app.installEventFilter(recorder)

        def start_measurement():
            nonlocal windows_native_diagnostics_setup_error
            nonlocal execution_error
            nonlocal started_at, last_frame_progress_at
            nonlocal window_visible_at_start, window_active_at_start
            try:
                app.processEvents()
                if not window.isVisible() or window.isMinimized() or not window.isActiveWindow():
                    raise RuntimeError("TC-PERF requires a visible, non-minimized, active Workbench window")
                window_visible_at_start = window.isVisible()
                window_active_at_start = window.isActiveWindow()
                speed_text = f"{args.playback_speed:g}x"
                window.speed_box.setCurrentText(speed_text)
                window.change_speed(window.speed_box.currentText())
                if window.engine.speed != args.playback_speed:
                    raise RuntimeError(
                        f"Expected {args.playback_speed:g}x playback, got {window.engine.speed}x"
                    )
                window.speed_box.setEnabled(False)
                window.canvas.reset_rendering_performance_metrics()
                started_at = time.perf_counter()
                last_frame_progress_at = started_at
                # Arm after harness-owned setup, before simulation startup.
                recorder.started_at = started_at
                if sys.platform == "win32":
                    try:
                        native_recorder = WindowsCloseEventRecorder(recorder, window)
                        app.installNativeEventFilter(native_recorder)
                        recorder.windows_native_recorder = native_recorder
                    except Exception as exc:
                        windows_native_diagnostics_setup_error = (
                            f"{type(exc).__name__}: {exc}"
                        )
                window.start_simulation()
                if window.engine.speed != args.playback_speed:
                    raise RuntimeError("Playback speed changed during startup")
                print(f"GUI measurement started at {args.playback_speed:g}x playback.", flush=True)
            except Exception as exc:
                execution_error = f"Benchmark startup failed: {type(exc).__name__}: {exc}"
                quit_with_failure(execution_error)

        def sample_metrics():
            nonlocal execution_error
            nonlocal last_frame_count, last_frame_progress_at
            nonlocal peak_rss_bytes, process_cpu_seconds
            nonlocal window_restoration_count, result
            if started_at is None:
                return
            try:
                now = time.perf_counter()
                if window.isMinimized():
                    window.showNormal()
                    window.raise_()
                    window.activateWindow()
                    app.processEvents()
                    window_restoration_count += 1
                metrics = window.canvas.get_rendering_performance_metrics()
                total_frames = int(metrics.get("total_frames", 0))
                if total_frames > last_frame_count:
                    last_frame_count = total_frames
                    last_frame_progress_at = now
                rss_bytes = process.memory_info().rss if process is not None else None
                if rss_bytes is not None:
                    peak_rss_bytes = max(peak_rss_bytes or 0, rss_bytes)
                    cpu_times = process.cpu_times()
                    process_cpu_seconds = cpu_times.user + cpu_times.system

                samples.append({
                    "elapsed_wall_seconds": round(now - started_at, 2),
                    "simulation_time_s": round(float(getattr(window.engine, "time", 0.0)), 2),
                    "fps": metrics.get("fps", 0.0),
                    "full_run_fps": metrics.get("full_run_fps", 0.0),
                    "total_frames": total_frames,
                    "avg_frame_ms": metrics.get("avg_frame_ms", 0.0),
                    "process_rss_bytes": rss_bytes,
                    "process_cpu_seconds": process_cpu_seconds if process is not None else None,
                    "playback_speed_multiplier": window.engine.speed,
                    "engine_running": bool(getattr(window.engine, "running", False)),
                    "simulation_timer_active": window.timer.isActive(),
                    "status_text": window.status_label.text(),
                    "window_visible": window.isVisible(),
                    "window_minimized": window.isMinimized(),
                    "window_active": window.isActiveWindow(),
                })

                if len(samples) % 60 == 0:
                    print(
                        f"Progress: {total_frames} frames; "
                        f"simulation {float(window.engine.time):.1f}/{float(window.engine.duration):.1f} s; "
                        f"elapsed {now - started_at:.0f} s; speed {window.engine.speed}x; "
                        f"running={window.engine.running}; active={window.isActiveWindow()}; "
                        f"visible={window.isVisible()}", flush=True,
                    )

                failure = measurement_failure_reason(
                    expected_speed=args.playback_speed,
                    actual_speed=window.engine.speed,
                    engine_running=bool(getattr(window.engine, "running", False)),
                    engine_finished=bool(getattr(window.engine, "finished", False)),
                    window_minimized=window.isMinimized(),
                    seconds_since_last_frame=(now - last_frame_progress_at)
                    if last_frame_progress_at is not None else float("inf"),
                )
                if failure:
                    print(f"Benchmark invalid: {failure}", flush=True)
                    quit_with_failure(failure)
                    return

                if getattr(window.engine, "finished", False):
                    timer.stop()
                    result = make_result()
                    app.quit()
            except Exception as exc:
                execution_error = f"Benchmark sampling failed: {type(exc).__name__}: {exc}"
                quit_with_failure(execution_error)

        timer = QTimer()
        timer.setInterval(1000)
        timer.timeout.connect(sample_metrics)
        QTimer.singleShot(1500, start_measurement)
        QTimer.singleShot(1500, timer.start)
        app_exec_code = app.exec()
        if result is None:
            execution_error = "Qt event loop exited before measurement completed"
            failure_reason = execution_error
            result = make_result()
    except Exception as exc:
        execution_error = f"Benchmark setup failed: {type(exc).__name__}: {exc}"
        if isinstance(exc, (sqlite3.Error, OSError)) or "SQLite preflight" in str(exc):
            storage_errors.append({"operation": "isolated database setup", "error": str(exc)})
    finally:
        cleanup_errors.extend(
            cleanup_benchmark_resources(app, window, timer, recorder)
        )
        if window is not None:
            storage_errors.extend(
                error for error in getattr(window, "storage_errors", [])
                if error not in storage_errors
            )
        if app_logger.handlers and error_handler in app_logger.handlers:
            app_logger.removeHandler(error_handler)

    if result is None:
        result = {
            "scenario": str(args.scenario),
            "seed": args.seed,
            "duration_s": args.duration_s,
            "finished": False,
            "simulation_time_s": 0.0,
            "final_metrics": {},
            "samples": samples,
            "input_events": recorder.events if recorder is not None else [],
            "input_delivery_traces": (
                recorder.delivery_traces if recorder is not None else []
            ),
            "non_client_mouse_events": (
                recorder.non_client_mouse_event_records() if recorder is not None else []
            ),
            "windows_native_close_messages": (
                list(recorder.windows_native_recorder.events)
                if recorder is not None and recorder.windows_native_recorder is not None
                else []
            ),
            "windows_native_close_diagnostic_parse_errors": (
                recorder.windows_native_recorder.parse_errors
                if recorder is not None and recorder.windows_native_recorder is not None
                else 0
            ),
            "windows_native_close_diagnostic_setup_error": windows_native_diagnostics_setup_error,
            "window_close_events": (
                recorder.window_close_events if recorder is not None else []
            ),
        }
    result["execution_error"] = execution_error
    result["measurement_failure_reason"] = failure_reason
    result["benchmark_execution_succeeded"] = (
        execution_error is None
        and failure_reason is None
        and result.get("finished") is True
        and app_exec_code == 0
    )
    result["application_cleanup_succeeded"] = not cleanup_errors
    result["application_cleanup_errors"] = cleanup_errors
    result["storage_errors"] = storage_errors
    try:
        _write_json_exclusive(stage_output, result)
    except Exception as exc:
        print(f"Could not write benchmark staging result: {exc}", file=sys.stderr, flush=True)
        return 1
    print("GUI worker cleanup complete.", flush=True)
    return 0 if result["benchmark_execution_succeeded"] and not cleanup_errors else 1


def _run_supervisor(args) -> int:
    """Run the GUI worker and finalize eligibility after its actual exit status."""
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite existing benchmark artifact: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    supervisor_temp = tempfile.TemporaryDirectory(
        prefix=".tms-issue12-benchmark-", dir=ROOT
    )
    temp_root = Path(supervisor_temp.name)
    stage_output = temp_root / "worker-result.json"
    history_dir = temp_root / "run-history"
    command = [
        sys.executable, str(ROOT / "measure_gui_fps.py"),
        "--scenario", str(args.scenario),
        "--output", str(args.output),
        "--playback-speed", str(args.playback_speed),
        "--_worker", "--_stage-output", str(stage_output),
        "--_history-dir", str(history_dir),
    ]
    if args.seed is not None:
        command.extend(["--seed", str(args.seed)])
    if args.duration_s is not None:
        command.extend(["--duration-s", str(args.duration_s)])

    worker_exit_code = 1
    process_error = None
    result = None
    temp_cleanup_error = None
    try:
        child = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert child.stdout is not None
        for line in child.stdout:
            print(line, end="", flush=True)
        worker_exit_code = child.wait()
        if stage_output.is_file():
            result = json.loads(stage_output.read_text(encoding="utf-8"))
        else:
            process_error = "GUI worker exited without producing a staging result"
    except Exception as exc:
        process_error = f"Benchmark supervisor failed: {type(exc).__name__}: {exc}"
    finally:
        try:
            supervisor_temp.cleanup()
        except Exception as exc:
            temp_cleanup_error = f"Temporary benchmark resources could not be removed: {exc}"

    if result is None:
        result = {
            "scenario": str(args.scenario),
            "seed": args.seed,
            "duration_s": args.duration_s,
            "requested_playback_speed_multiplier": args.playback_speed,
            "finished": False,
            "simulation_time_s": 0.0,
            "final_metrics": {},
            "samples": [],
            "input_events": [],
            "input_delivery_traces": [],
            "non_client_mouse_events": [],
            "windows_native_close_messages": [],
            "windows_native_close_diagnostic_parse_errors": 0,
            "windows_native_close_diagnostic_setup_error": None,
            "window_close_events": [],
            "storage_errors": [],
            "execution_error": process_error,
            "benchmark_execution_succeeded": False,
            "application_cleanup_succeeded": False,
            "application_cleanup_errors": [process_error] if process_error else [],
        }

    result = _finalize_benchmark_result(
        result,
        worker_exit_code=worker_exit_code,
        temp_cleanup_error=temp_cleanup_error,
    )
    metrics = result.get("final_metrics") or {}
    try:
        _write_json_exclusive(args.output, result)
    except Exception as exc:
        print(f"Could not write final benchmark artifact: {exc}", file=sys.stderr)
        return 1
    print(f"\nFinal benchmark artifact saved: {args.output}", flush=True)
    print(json.dumps({
        "finished": result.get("finished"),
        "simulation_time_s": result.get("simulation_time_s"),
        "full_run_fps": metrics.get("full_run_fps"),
        "acceptance_eligible": result["acceptance_eligible"],
        "process_exit_code": worker_exit_code,
        "cleanup_succeeded": result["cleanup_succeeded"],
    }, indent=2), flush=True)
    return 0 if worker_exit_code == 0 and temp_cleanup_error is None else 1


def main(argv=None) -> int:
    args = _parse_args(argv)
    if args._worker:
        return _run_gui_worker(args)
    return _run_supervisor(args)


if __name__ == "__main__":
    raise SystemExit(main())
