
"""Reproducible headless load test for TMS-Sim."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow execution as: python scripts/run_load_test.py ...
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tms_sim.reporting.metrics import compute_metrics
from tms_sim.sim.scenario import load_scenario


def run_once(scenario_path: Path) -> dict:
    start = time.perf_counter()
    engine = load_scenario(scenario_path)
    engine.start()

    # Execute the simulation directly without GUI playback or sleeping.
    while not engine.finished:
        engine.step()

    elapsed = time.perf_counter() - start
    metrics = compute_metrics(engine)

    return {
        "scenario": str(scenario_path),
        "seed": next(
            (
                line.get("seed")
                for line in [json.loads(scenario_path.read_text(encoding="utf-8")).get("simulation", {})]
            ),
            None,
        ),
        "simulated_seconds": engine.time,
        "elapsed_seconds": round(elapsed, 6),
        "vehicles_generated": metrics.vehicles_generated,
        "vehicles_entered": metrics.vehicles_entered,
        "vehicles_completed": metrics.vehicles_completed,
        "vehicles_in_network": metrics.vehicles_in_network,
        "mean_travel_time_seconds": metrics.mean_travel_time,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        type=Path,
        default=ROOT / "fixtures/valid/small_valid_scenario.json",
    )
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/load_test.json")
    args = parser.parse_args()

    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    if not args.scenario.is_file():
        parser.error(f"Scenario file not found: {args.scenario}")

    runs = []
    for index in range(args.repeat):
        result = run_once(args.scenario)
        result["run"] = index + 1
        runs.append(result)

    elapsed = [run["elapsed_seconds"] for run in runs]
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "repeat": args.repeat,
        "results": runs,
        "summary": {
            "mean_elapsed_seconds": round(sum(elapsed) / len(elapsed), 6),
            "min_elapsed_seconds": min(elapsed),
            "max_elapsed_seconds": max(elapsed),
        },
        "note": (
            "Headless execution timings are not GUI FPS measurements. "
            "No acceptance threshold is asserted by this script."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nSaved report to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
