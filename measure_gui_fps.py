
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

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from tms_sim.ui.app import Workbench


DEFAULT_SCENARIO = ROOT / "fixtures/valid/performance_10_intersections.json"
DEFAULT_OUTPUT = ROOT / "artifacts/gui_fps_full_run.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure a full GUI simulation run.")
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    scenario = args.scenario.resolve()
    output = args.output.resolve()
    if not scenario.is_file():
        parser.error(f"Scenario file not found: {scenario}")

    app = QApplication.instance() or QApplication(sys.argv)
    window = Workbench(str(scenario))
    history_tmp = tempfile.TemporaryDirectory(prefix="tms-issue12-history-")
    window.library_path = Path(history_tmp.name) / "run-history.sqlite3"
    if args.seed is not None:
        scenario_data = copy.deepcopy(window.scenario_data)
        scenario_data.setdefault("simulation", {})["seed"] = args.seed
        if not window.load_scenario_data(scenario_data, scenario.name):
            history_tmp.cleanup()
            raise RuntimeError(f"Workbench rejected benchmark seed {args.seed}")
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

    def start_measurement():
        nonlocal started_at, last_sample_at, last_frame_progress_at
        nonlocal window_visible_at_start, window_active_at_start

        app.processEvents()
        if not window.isVisible() or window.isMinimized() or not window.isActiveWindow():
            raise RuntimeError("TC-PERF requires a visible, non-minimized, active Workbench window")
        window_visible_at_start = window.isVisible()
        window_active_at_start = window.isActiveWindow()
        window.speed_box.setCurrentText("1x")
        window.change_speed(window.speed_box.currentText())
        if window.engine.speed != 1:
            raise RuntimeError(f"Expected normal 1x playback, got {window.engine.speed}x")
        window.speed_box.setEnabled(False)
        window.canvas.reset_rendering_performance_metrics()
        started_at = time.perf_counter()
        last_sample_at = started_at
        last_frame_progress_at = started_at

        window.start_simulation()
        if window.engine.speed != 1:
            raise RuntimeError(f"Playback speed changed during startup to {window.engine.speed}x")
        print("Full-run GUI measurement started at 1x playback.", flush=True)

    def sample_metrics():
        nonlocal last_sample_at, peak_rss_bytes, last_frame_count
        nonlocal last_frame_progress_at, failure_reason, window_restoration_count

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
            "playback_speed_multiplier": window.engine.speed,
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
                f"speed {window.engine.speed}x; "
                f"active={window.isActiveWindow()}; visible={window.isVisible()}",
                flush=True,
            )

        if window.engine.speed != 1:
            failure_reason = f"Playback speed changed from 1x to {window.engine.speed}x"
        elif window.isMinimized():
            failure_reason = "Workbench remained minimized after automatic restore"
        elif last_frame_progress_at is not None and now - last_frame_progress_at > 30:
            failure_reason = "No canvas frames were rendered for over 30 seconds"
        if failure_reason:
            timer.stop()
            print(f"Benchmark invalid: {failure_reason}", flush=True)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({
                "scenario": str(scenario),
                "seed": window.scenario_data.get("simulation", {}).get("seed"),
                "finished": bool(getattr(window.engine, "finished", False)),
                "simulation_time_s": float(getattr(window.engine, "time", 0.0)),
                "playback_speed_multiplier": window.engine.speed,
                "window_restoration_count": window_restoration_count,
                "measurement_failure_reason": failure_reason,
                "run_history_database_isolated": True,
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
            "seed": window.scenario_data.get("simulation", {}).get("seed"),
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
            "final_metrics": final_metrics,
            "samples": samples,
            "acceptance_note": (
                "Use full-run FPS only after confirming the complete "
                "reference scenario and agreed acceptance conditions."
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
