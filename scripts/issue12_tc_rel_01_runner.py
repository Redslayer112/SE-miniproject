
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
import time
import traceback
import uuid

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tms_sim.reporting.metrics import (
    IncrementalMetricsCalculator,
    compute_metrics,
)
from tms_sim.sim.scenario import engine_from_document


SCENARIO_PATH = (
    ROOT / "fixtures" / "valid" / "performance_10_intersections.json"
)

FLOAT_TOLERANCE = 1e-6


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unavailable"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def compare_values(
    recorded: Any,
    recomputed: Any,
    path: str = "metrics",
    checks: list[dict] | None = None,
) -> list[dict]:

    if checks is None:
        checks = []

    passed = False
    tolerance = None

    if recorded is None or recomputed is None:

        passed = recorded is None and recomputed is None

    elif isinstance(recorded, bool) or isinstance(recomputed, bool):

        passed = (
            type(recorded) is type(recomputed)
            and recorded == recomputed
        )

    elif isinstance(recorded, dict) and isinstance(recomputed, dict):

        passed = recorded.keys() == recomputed.keys()

        checks.append({
            "name": path + ".keys",
            "expected": sorted(recorded.keys()),
            "actual": sorted(recomputed.keys()),
            "passed": passed,
        })

        if passed:
            for key in sorted(recorded):
                compare_values(
                    recorded[key],
                    recomputed[key],
                    f"{path}.{key}",
                    checks,
                )

        return checks

    elif (
        isinstance(recorded, (int, float))
        and isinstance(recomputed, (int, float))
    ):

        if isinstance(recorded, int) and isinstance(recomputed, int):

            passed = recorded == recomputed

        else:

            tolerance = FLOAT_TOLERANCE

            passed = (
                math.isfinite(float(recorded))
                and math.isfinite(float(recomputed))
                and abs(float(recorded) - float(recomputed))
                <= tolerance
            )

    else:

        passed = (
            type(recorded) is type(recomputed)
            and recorded == recomputed
        )

    checks.append({
        "name": path,
        "expected": recorded,
        "actual": recomputed,
        "tolerance": tolerance,
        "passed": passed,
    })

    return checks


def finite_numeric_values(
    value: Any,
    path: str = "metrics",
) -> list[str]:

    errors = []

    if isinstance(value, bool) or value is None:
        return errors

    if isinstance(value, (int, float)):

        if not math.isfinite(float(value)):
            errors.append(f"{path} is not finite")

        return errors

    if isinstance(value, dict):

        for key, item in value.items():
            errors.extend(
                finite_numeric_values(item, f"{path}.{key}")
            )

    elif isinstance(value, (list, tuple)):

        for index, item in enumerate(value):
            errors.extend(
                finite_numeric_values(item, f"{path}[{index}]")
            )

    return errors


def add_check(
    checks: list[dict],
    name: str,
    expected: Any,
    actual: Any,
    passed: bool,
    tolerance: float | None = None,
) -> None:

    checks.append({
        "name": name,
        "expected": expected,
        "actual": actual,
        "tolerance": tolerance,
        "passed": bool(passed),
    })


def run_simulation(
    seed: int,
    duration: float,
    inject_exception: bool,
) -> dict:

    started_at = utc_now()
    wall_start = time.perf_counter()

    stage = "initialization"

    result = {
        "schema_version": 1,
        "run_id": str(uuid.uuid4()),
        "seed": seed,
        "status": "Failed",
        "started_at_utc": started_at,
        "finished_at_utc": None,
        "exception": None,
        "scenario": {},
        "environment": {},
        "engine": {},
        "metrics": {},
        "checks": [],
        "cleanup": {
            "status": "not_applicable",
            "errors": [],
        },
    }

    try:

        if not SCENARIO_PATH.is_file():
            raise FileNotFoundError(SCENARIO_PATH)

        stage = "scenario_loading"

        scenario_bytes = SCENARIO_PATH.read_bytes()

        document = json.loads(
            scenario_bytes.decode("utf-8")
        )

        original_duration = (
            document.get("simulation", {}).get(
                "duration_s",
                3600.0,
            )
        )

        configured_dt = (
            document.get("simulation", {}).get(
                "time_step_s",
                0.5,
            )
        )

        document.setdefault("simulation", {})["seed"] = seed

        document["simulation"]["duration_s"] = duration

        result["scenario"] = {
            "path": str(SCENARIO_PATH.relative_to(ROOT)),
            "sha256": hashlib.sha256(
                scenario_bytes
            ).hexdigest(),
            "scenario_id": document.get("scenario_id"),
            "requested_duration_s": duration,
            "original_fixture_duration_s": original_duration,
            "time_step_s": configured_dt,
        }

        result["environment"] = {
            "code_revision": git_revision(),
            "python_version": sys.version,
            "platform": platform.platform(),
            "executable": sys.executable,
        }

        stage = "engine_construction"

        engine = engine_from_document(document)

        stage = "simulation_execution"

        engine.start()

        # Negative control: deliberately raise an exception.
        if inject_exception:

            raise RuntimeError(
                "TC-REL-01 injected runner exception "
                "at simulation_execution"
            )

        # Execute the simulation and update incremental metrics.
        calculator = IncrementalMetricsCalculator()

        while not engine.finished:

            engine.step()

            calculator.calculate(engine)

        stage = "metrics_capture"

        recorded_metrics = asdict(
            calculator.calculate(engine)
        )

        recomputed_metrics = asdict(
            compute_metrics(engine)
        )

        # Compare incremental and independently recomputed metrics.
        metric_comparison = compare_values(
            recorded_metrics,
            recomputed_metrics,
        )

        result["metrics"] = {
            "recorded": recorded_metrics,
            "recomputed": recomputed_metrics,
            "comparison": metric_comparison,
        }

        # IMPORTANT: metrics comparison must affect overall PASS/FAIL.
        metric_comparison_passed = all(
            item["passed"]
            for item in metric_comparison
        )

        stage = "consistency_checks"

        checks = result["checks"]

        add_check(
            checks,
            "recorded_metrics_match_recomputed",
            True,
            metric_comparison_passed,
            metric_comparison_passed,
        )

        # 1. Engine completion.
        add_check(
            checks,
            "engine_finished",
            True,
            engine.finished,
            engine.finished is True,
        )

        # 2. Metrics status.
        add_check(
            checks,
            "metrics_status",
            "Completed",
            recomputed_metrics["status"],
            recomputed_metrics["status"] == "Completed",
        )

        # 3. Engine must not still be running.
        add_check(
            checks,
            "engine_not_running",
            False,
            engine.running,
            engine.running is False,
        )

        # 4. Simulation duration.
        duration_ok = (
            duration - FLOAT_TOLERANCE
            <= engine.time
            <= duration + engine.p.dt + FLOAT_TOLERANCE
        )

        add_check(
            checks,
            "simulation_duration",
            {
                "minimum": duration - FLOAT_TOLERANCE,
                "maximum": (
                    duration
                    + engine.p.dt
                    + FLOAT_TOLERANCE
                ),
            },
            engine.time,
            duration_ok,
            FLOAT_TOLERANCE,
        )

        # 5. Vehicle identity and lifecycle events.
        scheduled_ids = [
            vehicle.id for vehicle in engine.vehicles
        ]

        spawn_ids = [
            event["vehicle_id"]
            for event in engine.metric_events
            if event.get("type") == "spawn"
        ]

        exit_ids = [
            event["vehicle_id"]
            for event in engine.metric_events
            if event.get("type") == "exit"
        ]

        active_ids = [
            car.id for car in engine.cars
        ]

        exited_ids = [
            car.id for car in engine.exited
        ]

        scheduled_unique = (
            len(set(scheduled_ids)) == len(scheduled_ids)
        )

        spawn_unique = (
            len(set(spawn_ids)) == len(spawn_ids)
        )

        exit_unique = (
            len(set(exit_ids)) == len(exit_ids)
        )

        add_check(
            checks,
            "scheduled_vehicle_ids_unique",
            True,
            scheduled_unique,
            scheduled_unique,
        )

        add_check(
            checks,
            "spawn_ids_unique",
            True,
            spawn_unique,
            spawn_unique,
        )

        add_check(
            checks,
            "exit_ids_unique",
            True,
            exit_unique,
            exit_unique,
        )

        orphan_exits = sorted(
            set(exit_ids) - set(spawn_ids)
        )

        add_check(
            checks,
            "no_orphan_exit_ids",
            [],
            orphan_exits,
            not orphan_exits,
        )

        # 6. Demand accounting.
        generated = recomputed_metrics["vehicles_generated"]

        total_scheduled = (
            recomputed_metrics["total_scheduled"]
        )

        entered = recomputed_metrics["vehicles_entered"]

        completed = (
            recomputed_metrics["vehicles_completed"]
        )

        in_network = (
            recomputed_metrics["vehicles_in_network"]
        )

        add_check(
            checks,
            "scheduled_demand_accounting",
            len(engine.vehicles),
            generated,
            (
                generated
                == total_scheduled
                == len(engine.vehicles)
            ),
        )

        # 7. Spawn and exit event accounting.
        spawned_with_exits = (
            set(spawn_ids).intersection(exit_ids)
        )

        add_check(
            checks,
            "spawn_count_matches_entered",
            entered,
            len(set(spawn_ids)),
            len(set(spawn_ids)) == entered,
        )

        add_check(
            checks,
            "completed_ids_match_completed_count",
            completed,
            len(spawned_with_exits),
            len(spawned_with_exits) == completed,
        )

        add_check(
            checks,
            "active_count_matches_engine_cars",
            in_network,
            len(engine.cars),
            in_network == len(engine.cars),
        )

        # 8. Vehicle conservation.
        add_check(
            checks,
            "vehicle_conservation",
            entered,
            completed + in_network,
            entered == completed + in_network,
        )

        add_check(
            checks,
            "exited_state_matches_completed",
            completed,
            len(engine.exited),
            len(engine.exited) == completed,
        )

        # 9. Active/exited identity checks.
        active_unique = (
            len(set(active_ids)) == len(active_ids)
        )

        exited_unique = (
            len(set(exited_ids)) == len(exited_ids)
        )

        disjoint = not (
            set(active_ids) & set(exited_ids)
        )

        add_check(
            checks,
            "active_ids_unique",
            True,
            active_unique,
            active_unique,
        )

        add_check(
            checks,
            "exited_ids_unique",
            True,
            exited_unique,
            exited_unique,
        )

        add_check(
            checks,
            "active_and_exited_ids_disjoint",
            True,
            disjoint,
            disjoint,
        )

        # 10. Metrics must contain only finite numbers.
        finite_errors = finite_numeric_values(
            recomputed_metrics
        )

        add_check(
            checks,
            "metrics_are_finite",
            [],
            finite_errors,
            not finite_errors,
        )

        # 11. Metrics count bounds.
        count_checks = (
            generated >= 0
            and total_scheduled >= 0
            and entered >= 0
            and completed >= 0
            and in_network >= 0
            and generated <= total_scheduled
            and entered <= total_scheduled
            and completed <= entered
            and in_network <= entered
        )

        add_check(
            checks,
            "metrics_counts_are_bounded",
            True,
            count_checks,
            count_checks,
        )

        result["engine"] = {
            "finished": engine.finished,
            "running": engine.running,
            "time_s": engine.time,
            "duration_s": engine.duration,
            "time_step_s": engine.p.dt,
            "scheduled_vehicle_count": len(engine.vehicles),
            "spawn_event_count": len(spawn_ids),
            "exit_event_count": len(exit_ids),
            "active_vehicle_count": len(engine.cars),
            "exited_vehicle_count": len(engine.exited),
            "scheduled_vehicle_ids": scheduled_ids,
            "spawn_vehicle_ids": spawn_ids,
            "exit_vehicle_ids": exit_ids,
            "active_vehicle_ids": active_ids,
            "exited_vehicle_ids": exited_ids,
            "metric_event_count": len(engine.metric_events),
        }

        # The run passes only when every check passes.
        result["status"] = (
            "Passed"
            if all(check["passed"] for check in checks)
            else "Failed"
        )

    except BaseException as exc:

        result["status"] = "Failed"

        result["exception"] = {
            "stage": stage,
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "timestamp_utc": utc_now(),
        }

    finally:

        result["finished_at_utc"] = utc_now()

        result["wall_clock_seconds"] = (
            time.perf_counter() - wall_start
        )

    return result


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "TC-REL-01 isolated headless simulation runner"
        )
    )

    parser.add_argument(
        "--seed",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=3600.0,
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--inject-runner-exception",
        action="store_true",
        help="Test-only negative control",
    )

    args = parser.parse_args()

    if args.duration <= 0:
        parser.error("--duration must be greater than zero")

    output = args.output.resolve()

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Never overwrite previous evidence.
    if output.exists():
        parser.error(
            f"Output already exists; refusing to overwrite: {output}"
        )

    result = run_simulation(
        args.seed,
        args.duration,
        args.inject_runner_exception,
    )

    temporary_output = output.with_suffix(
        output.suffix + ".tmp"
    )

    try:

        temporary_output.write_text(
            json.dumps(
                result,
                indent=2,
                allow_nan=False,
            ) + "\n",
            encoding="utf-8",
        )

        temporary_output.replace(output)

    except Exception:

        if temporary_output.exists():
            temporary_output.unlink()

        raise

    print(
        json.dumps({
            "seed": args.seed,
            "status": result["status"],
            "output": str(output),
            "wall_clock_seconds": (
                result["wall_clock_seconds"]
            ),
        }),
        flush=True,
    )

    return (
        0 if result["status"] == "Passed" else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
