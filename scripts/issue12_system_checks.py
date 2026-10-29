"""Run Issue #12 headless reliability, determinism, and Workbench workflow checks."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import sys
import tempfile
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import psutil
from PySide6.QtWidgets import QApplication, QMessageBox

from tms_sim.reporting.comparison import SimulationRunRecord, compare_runs
from tms_sim.reporting.metrics import compute_metrics
from tms_sim.sim.scenario import engine_from_document
from tms_sim.storage.store import ScenarioStore
from tms_sim.ui.app import Workbench


SCENARIO_PATH = ROOT / "fixtures/valid/performance_10_intersections.json"
WORKFLOW_SCENARIO_PATH = ROOT / "tests/data/scenario/small_valid_scenario.json"
OUTPUT_DIR = ROOT / "artifacts/issue12"
PROCESS = psutil.Process()
_peak_rss = 0
_stop_sampler = threading.Event()


def _sample_process_rss() -> None:
    global _peak_rss
    while not _stop_sampler.wait(0.05):
        try:
            _peak_rss = max(_peak_rss, PROCESS.memory_info().rss)
        except psutil.Error:
            pass


def run_engine(document: dict) -> tuple[dict, list[dict], dict]:
    engine = engine_from_document(document)
    engine.start()
    while not engine.finished:
        engine.step()
    metrics = asdict(compute_metrics(engine))
    demand = [asdict(vehicle) for vehicle in engine.vehicles]
    metric_events = list(engine.metric_events)
    return {
        "status": "Completed" if engine.finished else "Failed",
        "simulated_seconds": engine.time,
        "generated": len(engine.vehicles),
        "completed": len(engine.exited),
        "in_network": len(engine.cars),
    }, demand + metric_events, metrics


def sha256(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def main() -> int:
    global _peak_rss
    if not SCENARIO_PATH.is_file():
        raise FileNotFoundError(SCENARIO_PATH)
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "commit": os.environ.get("ISSUE12_COMMIT", "working-tree"),
        "scenario": str(SCENARIO_PATH),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "reliability_headless": [],
        "determinism": {},
        "analyst_workflow": {},
        "run_history_database_isolation": "temporary database in a TemporaryDirectory; removed after the workflow",
    }

    _peak_rss = PROCESS.memory_info().rss
    sampler = threading.Thread(target=_sample_process_rss, daemon=True)
    sampler.start()
    try:
        # Three full-duration, separately seeded headless runs.
        for seed in (42, 43, 44):
            print(f"Headless reliability run seed={seed} started.", flush=True)
            document = json.loads(json.dumps(scenario))
            document["simulation"]["seed"] = seed
            cpu_start = time.process_time()
            wall_start = time.perf_counter()
            counts, _, metrics = run_engine(document)
            result = {
                "seed": seed,
                **counts,
                "elapsed_wall_seconds": round(time.perf_counter() - wall_start, 6),
                "cpu_seconds": round(time.process_time() - cpu_start, 6),
                "metrics": metrics,
                "crash_or_exception": False,
            }
            report["reliability_headless"].append(result)

        # Two independent same-scenario, same-seed runs with complete demand,
        # canonical measurement/lifecycle events, and all metrics compared.
        deterministic_document = json.loads(json.dumps(scenario))
        deterministic_document["simulation"]["seed"] = 42
        print("Same-seed determinism comparison started.", flush=True)
        first_counts, first_events, first_metrics = run_engine(deterministic_document)
        second_counts, second_events, second_metrics = run_engine(deterministic_document)
        # run_engine returns generated demand followed by metric events. Separate
        # demand from its event log by the generated count for stable hashing.
        demand_count = first_counts["generated"]
        first_demand, first_log = first_events[:demand_count], first_events[demand_count:]
        second_demand, second_log = second_events[:demand_count], second_events[demand_count:]
        metrics_non_null = all(
            first_metrics[key] is not None
            for key in ("throughput_vph", "average_delay_s", "queue_length_veh")
        )
        report["determinism"] = {
            "seed": 42,
            "runs_compared": 2,
            "demand_identical": first_demand == second_demand,
            "complete_metric_event_logs_identical": first_log == second_log,
            "all_metrics_identical": first_metrics == second_metrics,
            "required_metrics_non_null": metrics_non_null,
            "demand_count": demand_count,
            "metric_event_count": len(first_log),
            "demand_sha256": sha256(first_demand),
            "metric_event_log_sha256": sha256(first_log),
            "metrics_sha256": sha256(first_metrics),
            "run_counts": [first_counts, second_counts],
            "metrics": first_metrics,
        }

        # Run the actual Workbench workflow using only a temporary SQLite file.
        app = QApplication.instance() or QApplication([])
        print("Temporary-store Workbench workflow started.", flush=True)
        with tempfile.TemporaryDirectory(prefix="tms-issue12-workflow-") as temporary:
            temporary_path = Path(temporary)
            database = temporary_path / "scenario-library.sqlite3"
            exported_scenario = temporary_path / "reference.json"
            csv_path = temporary_path / "run.csv"
            window = Workbench(str(WORKFLOW_SCENARIO_PATH))
            print("Workbench constructed.", flush=True)
            window.library_path = database
            network = window.scenario_data["network"]
            with ScenarioStore(database) as store:
                store.save_scenario("Issue12 reference", window.scenario_data)
                store.export_scenario("Issue12 reference", exported_scenario)
                store.import_scenario(exported_scenario, "Issue12 imported")
                imported_document = store.load_scenario("Issue12 imported")
            print("Scenario save/export/import/load completed.", flush=True)

            load_ok = window.load_scenario_data(imported_document, "Issue12 imported")
            print(f"Workbench scenario reload: {load_ok}.", flush=True)
            run_records = []
            for index in range(2):
                print(f"Workbench run {index + 1} started.", flush=True)
                if index:
                    load_ok = window.load_scenario_data(imported_document, "Issue12 imported") and load_ok
                window.engine.start()
                while not window.engine.finished:
                    window.engine.step()
                window.update_metrics()
                record = window.capture_current_run(f"Issue12 workflow run {index + 1}")
                if record is None:
                    raise AssertionError("Workbench did not capture the completed run")
                run_records.append(record)
                print(f"Workbench run {index + 1} persisted.", flush=True)

            with ScenarioStore(database) as store:
                stored_runs = [store.load_run(record.run_id) for record in run_records]
                stored_names = store.list_scenarios()
            print("Persisted runs reloaded from SQLite.", flush=True)
            restored_records = [SimulationRunRecord.from_stored(row) for row in stored_runs]
            print("Run records reconstructed.", flush=True)
            comparison = compare_runs(restored_records[0], restored_records[1])
            print("Two-run comparison computed.", flush=True)
            # Suppress the success modal for this non-interactive offscreen run;
            # file export and return value remain the actual Workbench code path.
            QMessageBox.information = staticmethod(
                lambda *args, **kwargs: QMessageBox.StandardButton.Ok
            )
            csv_exported = window.export_current_run_csv(csv_path)
            print(f"Workbench CSV export: {csv_exported}.", flush=True)
            with csv_path.open("r", encoding="utf-8", newline="") as source:
                csv_rows = list(csv.DictReader(source))
            dashboard_updated = (
                bool(window.delay_metric_label.text())
                and bool(window.queue_metric_label.text())
                and "Not available" not in window.delay_metric_label.text()
            )
            window.timer.stop()
            window.set_dirty(False)
            window.close()
            print("Workbench closed cleanly.", flush=True)

            report["analyst_workflow"] = {
                "network_loaded": bool(network.get("intersections") and network.get("segments")),
                "intersection_count": len(network.get("intersections", [])),
                "segment_count": len(network.get("segments", [])),
                "scenario_saved_exported_imported_and_reloaded": bool(load_ok and "Issue12 imported" in stored_names),
                "runs_completed_and_persisted": len(stored_runs) == 2,
                "stored_runs_reloaded": len(restored_records) == 2,
                "results_dashboard_updated": dashboard_updated,
                "two_run_comparison_duration_compatible": comparison.duration_compatible,
                "two_run_metrics_equal": asdict(restored_records[0].metrics) == asdict(restored_records[1].metrics),
                "csv_export_parsed": bool(csv_exported and csv_rows),
                "csv_row_count": len(csv_rows),
                "database_isolated": True,
            }
    finally:
        _stop_sampler.set()
        sampler.join(timeout=2)

    report["headless_reliability_process_peak_rss_bytes"] = _peak_rss
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / "system_checks.json"
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    print(f"Evidence saved to: {output}")

    all_headless_completed = all(
        run["status"] == "Completed" and run["simulated_seconds"] >= 3600 and not run["crash_or_exception"]
        for run in report["reliability_headless"]
    )
    deterministic = report["determinism"]
    workflow = report["analyst_workflow"]
    return 0 if (
        all_headless_completed
        and deterministic["demand_identical"]
        and deterministic["complete_metric_event_logs_identical"]
        and deterministic["all_metrics_identical"]
        and deterministic["required_metrics_non_null"]
        and all(workflow.values())
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
