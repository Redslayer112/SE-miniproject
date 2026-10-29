
import sys
import json
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from tms_sim.ui.app import Workbench


SCENARIO = Path(
    "fixtures/valid/performance_10_intersections.json"
).resolve()

OUTPUT = Path("artifacts/gui_fps_full_run.json")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = Workbench(str(SCENARIO))
    window.show()

    samples = []
    started_at = None
    last_sample_at = None

    def start_measurement():
        nonlocal started_at, last_sample_at

        started_at = time.perf_counter()
        last_sample_at = started_at

        window.start_simulation()
        print("Full-run GUI measurement started.", flush=True)

    def sample_metrics():
        nonlocal last_sample_at

        if started_at is None:
            return

        now = time.perf_counter()
        metrics = window.canvas.get_rendering_performance_metrics()

        samples.append({
            "elapsed_wall_seconds": round(now - started_at, 2),
            "simulation_time_s": round(
                float(getattr(window.engine, "time", 0.0)), 2
            ),
            "fps": metrics.get("fps", 0.0),
            "full_run_fps": metrics.get("full_run_fps", 0.0),
            "total_frames": metrics.get("total_frames", 0),
            "avg_frame_ms": metrics.get("avg_frame_ms", 0.0),
        })

        last_sample_at = now

        if getattr(window.engine, "finished", False):
            finish_measurement()

    def finish_measurement():
        timer.stop()

        final_metrics = window.canvas.get_rendering_performance_metrics()
        result = {
            "scenario": str(SCENARIO),
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
            "final_metrics": final_metrics,
            "samples": samples,
            "acceptance_note": (
                "Use full-run FPS only after confirming the complete "
                "reference scenario and agreed acceptance conditions."
            ),
        }

        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )

        print("\nFull-run measurement saved:", OUTPUT.resolve(), flush=True)
        print(json.dumps({
            "finished": result["finished"],
            "simulation_time_s": result["simulation_time_s"],
            "measurement_wall_seconds": result["measurement_wall_seconds"],
            "vehicles_generated": result["vehicles_generated"],
            "vehicles_in_network": result["vehicles_in_network"],
            "final_metrics": final_metrics,
        }, indent=2), flush=True)

    timer = QTimer()
    timer.setInterval(1000)
    timer.timeout.connect(sample_metrics)

    QTimer.singleShot(1500, start_measurement)
    QTimer.singleShot(1500, timer.start)

    return_code = app.exec()
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
