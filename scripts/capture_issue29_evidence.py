"""Generate high-resolution PNG screenshot evidence for Issue #29.

Demonstrates:
1. Main workbench.
2. Network editing interface.
3. 2D network visualization.
4. Live vehicle movement.
5. Traffic signal states and queues.
6. Metrics dashboard and charts.
7. Simulation completion/results.
"""
from __future__ import annotations

import os
from pathlib import Path

# Ensure offscreen Qt platform for headless screenshot generation
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from tms_sim.ui.app import Workbench

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SCENARIO_PATH = ROOT / "tests" / "data" / "scenario" / "small_valid_scenario.json"


def main():
    app = QApplication.instance() or QApplication(["--platform", "offscreen"])
    w = Workbench(str(SCENARIO_PATH))
    w.library_path = OUT_DIR / "temp_store.sqlite3"
    w.resize(1366, 768)
    w.show()
    app.processEvents()

    # 1. Main workbench
    pix = w.grab()
    path1 = OUT_DIR / "01_main_workbench.png"
    pix.save(str(path1))
    print(f"Captured: {path1.name}")

    # 2. Network editing interface (select segment R1 to show properties)
    w.canvas.set_selection("segment", "R1")
    w.set_tool_mode("select")
    app.processEvents()
    pix = w.grab()
    path2 = OUT_DIR / "02_network_editing_interface.png"
    pix.save(str(path2))
    print(f"Captured: {path2.name}")

    # 3. 2D network visualization (focus on canvas)
    w.canvas.set_selection(None, None)
    app.processEvents()
    pix = w.canvas.grab()
    path3 = OUT_DIR / "03_2d_network_visualization.png"
    pix.save(str(path3))
    print(f"Captured: {path3.name}")

    # 4. Live vehicle movement (advance simulation to ~25s with active vehicles)
    w.engine.start()
    while w.engine.time < 24.0 and not w.engine.finished:
        w.engine.step()
    w.canvas.update()
    w.update_metrics(force_history_sample=True)
    app.processEvents()
    pix = w.canvas.grab()
    path4 = OUT_DIR / "04_live_vehicle_movement.png"
    pix.save(str(path4))
    print(f"Captured: {path4.name}")

    # 5. Traffic signal states and queues (advance into red phase with queued vehicles)
    while w.engine.time < 48.0 and not w.engine.finished:
        w.engine.step()
    w.canvas.update()
    w.update_metrics(force_history_sample=True)
    app.processEvents()
    pix = w.canvas.grab()
    path5 = OUT_DIR / "05_signal_states_and_queues.png"
    pix.save(str(path5))
    print(f"Captured: {path5.name}")

    # 6. Metrics dashboard and charts (grab right-side performance panel)
    pix = w.performance_panel.grab()
    path6 = OUT_DIR / "06_metrics_dashboard_and_charts.png"
    pix.save(str(path6))
    print(f"Captured: {path6.name}")

    # 7. Simulation completion/results (run to finish at 600s)
    w.engine.set_speed(4)
    while not w.engine.finished:
        w.engine.step()
    w.canvas.update()
    w.update_metrics(force_history_sample=True)
    app.processEvents()
    pix = w.grab()
    path7 = OUT_DIR / "07_simulation_completion_results.png"
    pix.save(str(path7))
    print(f"Captured: {path7.name}")

    w.timer.stop()
    w.close()
    print("All 7 screenshots generated successfully.")


if __name__ == "__main__":
    main()
