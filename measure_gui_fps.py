
import argparse
import copy
import platform
import sys
import json
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

try:
    import psutil
except ImportError:  # Process RSS is supplemental; the benchmark itself has no extra dependency.
    psutil = None

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication

from tms_sim.ui.app import Workbench


DEFAULT_SCENARIO = ROOT / "fixtures/valid/performance_10_intersections.json"
DEFAULT_OUTPUT = ROOT / "artifacts/gui_fps_full_run.json"
SUPPORTED_SPEEDS = (0.5, 1.0, 2.0, 4.0)


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
    """Record user input that could pause or otherwise alter a visible run."""

    def __init__(self):
        super().__init__()
        self.started_at = None
        self.events = []

    def eventFilter(self, watched, event):
        if self.started_at is not None and event.type() in (
            QEvent.Type.KeyPress,
            QEvent.Type.MouseButtonPress,
        ):
            event_type = event.type()
            record = {
                "elapsed_wall_seconds": round(time.perf_counter() - self.started_at, 3),
                "event_type": "key_press" if event_type == QEvent.Type.KeyPress else "mouse_press",
                "target": getattr(watched, "objectName", lambda: "")() or type(watched).__name__,
            }
            if event_type == QEvent.Type.KeyPress:
                record["key"] = int(event.key())
            self.events.append(record)
        return False


def main() -> int:
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
    args = parser.parse_args()
    scenario = args.scenario.resolve()
    output = args.output.resolve()
    if not scenario.is_file():
        parser.error(f"Scenario file not found: {scenario}")
    if args.duration_s is not None and args.duration_s <= 0:
        parser.error("--duration-s must be positive")

    app = QApplication.instance() or QApplication(sys.argv)
    window = Workbench(str(scenario))
    history_tmp = tempfile.TemporaryDirectory(prefix="tms-issue12-history-")
    window.library_path = Path(history_tmp.name) / "run-history.sqlite3"
    if args.seed is not None or args.duration_s is not None:
        scenario_data = copy.deepcopy(window.scenario_data)
        simulation = scenario_data.setdefault("simulation", {})
        if args.seed is not None:
            simulation["seed"] = args.seed
        if args.duration_s is not None:
            simulation["duration_s"] = args.duration_s
        if not window.load_scenario_data(scenario_data, scenario.name):
            history_tmp.cleanup()
            raise RuntimeError("Workbench rejected the diagnostic scenario settings")
    window.show()
    window.raise_()
    window.activateWindow()

    samples = []
    started_at = None
    last_sample_at = None
    last_frame_count = 0
    last_frame_progress_at = None
    failure_reason = None
    window_restoration_count = 0
    window_visible_at_start = False
    window_active_at_start = False
    process = psutil.Process() if psutil is not None else None
    peak_rss_bytes = None
    process_cpu_seconds = 0.0
    input_recorder = InputEventRecorder()
    app.installEventFilter(input_recorder)

    def start_measurement():
        nonlocal started_at, last_sample_at, last_frame_progress_at
        nonlocal window_visible_at_start, window_active_at_start

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
        last_sample_at = started_at
        last_frame_progress_at = started_at
        input_recorder.started_at = started_at

        window.start_simulation()
        if window.engine.speed != args.playback_speed:
            raise RuntimeError("Playback speed changed during startup")
        print(
            f"GUI measurement started at {args.playback_speed:g}x playback.",
            flush=True,
        )

    def sample_metrics():
        nonlocal last_sample_at, peak_rss_bytes, last_frame_count
        nonlocal last_frame_progress_at, failure_reason, window_restoration_count
        nonlocal process_cpu_seconds

        if started_at is None:
            return

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
            "simulation_time_s": round(
                float(getattr(window.engine, "time", 0.0)), 2
            ),
            "fps": metrics.get("fps", 0.0),
            "full_run_fps": metrics.get("full_run_fps", 0.0),
            "total_frames": metrics.get("total_frames", 0),
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

        last_sample_at = now

        if len(samples) % 60 == 0:
            print(
                f"Progress: {metrics.get('total_frames', 0)} frames; "
                f"simulation {float(getattr(window.engine, 'time', 0.0)):.1f}/"
                f"{float(getattr(window.engine, 'duration', 0.0)):.1f} s; "
                f"elapsed {now - float(started_at):.0f} s; "
                f"speed {window.engine.speed}x; running={window.engine.running}; "
                f"active={window.isActiveWindow()}; visible={window.isVisible()}",
                flush=True,
            )

        failure_reason = measurement_failure_reason(
            expected_speed=args.playback_speed,
            actual_speed=window.engine.speed,
            engine_running=bool(getattr(window.engine, "running", False)),
            engine_finished=bool(getattr(window.engine, "finished", False)),
            window_minimized=window.isMinimized(),
            seconds_since_last_frame=(now - last_frame_progress_at)
            if last_frame_progress_at is not None else float("inf"),
        )
        if failure_reason:
            timer.stop()
            print(f"Benchmark invalid: {failure_reason}", flush=True)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({
                "scenario": str(scenario),
                "seed": window.scenario_data.get("simulation", {}).get("seed"),
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "duration_s": window.engine.duration,
                "requested_playback_speed_multiplier": args.playback_speed,
                "acceptance_eligible": args.playback_speed == 1.0 and window.engine.duration >= 3600.0,
                "finished": bool(getattr(window.engine, "finished", False)),
                "simulation_time_s": float(getattr(window.engine, "time", 0.0)),
                "playback_speed_multiplier": window.engine.speed,
                "engine_running": bool(getattr(window.engine, "running", False)),
                "simulation_timer_active": window.timer.isActive(),
                "status_text": window.status_label.text(),
                "window_restoration_count": window_restoration_count,
                "measurement_failure_reason": failure_reason,
                "run_history_database_isolated": True,
                "input_events": input_recorder.events,
                "peak_process_rss_bytes": peak_rss_bytes,
                "process_cpu_seconds": process_cpu_seconds if process is not None else None,
                "samples": samples,
            }, indent=2), encoding="utf-8")
            app.quit()
            return

        if getattr(window.engine, "finished", False):
            finish_measurement()

    def finish_measurement():
        timer.stop()

        final_metrics = window.canvas.get_rendering_performance_metrics()
        result = {
            "scenario": str(scenario),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "processor": platform.processor(),
            "machine": platform.machine(),
            "playback_speed_multiplier": window.engine.speed,
            "requested_playback_speed_multiplier": args.playback_speed,
            "seed": window.scenario_data.get("simulation", {}).get("seed"),
            "duration_s": window.engine.duration,
            "acceptance_eligible": args.playback_speed == 1.0 and window.engine.duration >= 3600.0,
            "run_history_database_isolated": True,
            "window_restoration_count": window_restoration_count,
            "window_visible_before_start": window_visible_at_start,
            "window_active_before_start": window_active_at_start,
            "measurement_method": "full-run FPS = (total frames - 1) / elapsed wall time between first and last paint events",
            "finished": bool(getattr(window.engine, "finished", False)),
            "simulation_time_s": round(
                float(getattr(window.engine, "time", 0.0)), 2
            ),
            "vehicles_generated": len(
                getattr(window.engine, "vehicles", [])
            ),
            "vehicles_in_network": len(
                getattr(window.engine, "cars", [])
            ),
            "measurement_wall_seconds": round(
                time.perf_counter() - float(started_at), 2
            ) if started_at is not None else 0.0,
            "peak_process_rss_bytes": peak_rss_bytes,
            "process_cpu_seconds": process_cpu_seconds if process is not None else None,
            "final_metrics": final_metrics,
            "input_events": input_recorder.events,
            "samples": samples,
            "acceptance_note": (
                "A run at a speed other than 1x or shorter than one simulated hour "
                "is diagnostic only and cannot satisfy TC-PERF-01."
            ),
        }

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )

        print("\nFull-run measurement saved:", output, flush=True)
        print(json.dumps({
            "finished": result["finished"],
            "simulation_time_s": result["simulation_time_s"],
            "measurement_wall_seconds": result["measurement_wall_seconds"],
            "vehicles_generated": result["vehicles_generated"],
            "vehicles_in_network": result["vehicles_in_network"],
            "peak_process_rss_bytes": peak_rss_bytes,
            "final_metrics": final_metrics,
        }, indent=2), flush=True)
        app.quit()

    timer = QTimer()
    timer.setInterval(1000)
    timer.timeout.connect(sample_metrics)

    QTimer.singleShot(1500, start_measurement)
    QTimer.singleShot(1500, timer.start)

    return_code = app.exec()
    history_tmp.cleanup()
    return 1 if failure_reason else return_code


if __name__ == "__main__":
    raise SystemExit(main())
