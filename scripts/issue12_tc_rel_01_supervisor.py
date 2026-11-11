
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


ROOT = Path(__file__).resolve().parents[1]

RUNNER = (
    ROOT / "scripts" / "issue12_tc_rel_01_runner.py"
)

EVIDENCE_DIR = (
    ROOT / "artifacts" / "issue12" / "tc_rel_01"
)

SEEDS = (42, 43, 44)

DURATION_SECONDS = 3600.0
WALL_TIMEOUT_SECONDS = 60.0

GRACEFUL_TERMINATE_SECONDS = 5.0
FORCE_KILL_SECONDS = 5.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def unique_stamp() -> str:
    return datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S_%fZ"
    )


def write_json_new(path: Path, data: dict) -> None:
    """Create new evidence without overwriting existing files."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite evidence: {path}"
        )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    if temporary.exists():
        raise FileExistsError(
            f"Temporary evidence already exists: {temporary}"
        )

    payload = (
        json.dumps(
            data,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )

    with temporary.open(
        "x",
        encoding="utf-8",
    ) as handle:
        handle.write(payload)

    # Exclusive creation prevents accidental replacement.
    try:
        with path.open(
            "x",
            encoding="utf-8",
        ) as handle:
            handle.write(payload)
    finally:
        if temporary.exists():
            temporary.unlink()


def process_exists(pid: int) -> bool:
    return psutil.pid_exists(pid)


def get_descendant_pids(pid: int) -> list[int]:
    """Return currently observable descendants recursively."""

    try:
        parent = psutil.Process(pid)

        return [
            child.pid
            for child in parent.children(recursive=True)
        ]

    except psutil.NoSuchProcess:
        return []

    except psutil.AccessDenied:
        return []


def terminate_process_tree(
    process: subprocess.Popen,
    inject_cleanup_failure: bool = False,
) -> dict[str, Any]:
    """
    Terminate descendants first, then the parent.

    Wait for graceful termination before force-killing.
    Always attempt to reap the Popen parent process.
    """

    result = {
        "initial_pid": process.pid,
        "descendant_pids": [],
        "terminated_pids": [],
        "killed_pids": [],
        "graceful_wait_seconds": (
            GRACEFUL_TERMINATE_SECONDS
        ),
        "force_wait_seconds": FORCE_KILL_SECONDS,
        "parent_reaped": False,
        "remaining_pids": [],
        "status": "Passed",
        "errors": [],
    }

    descendants = get_descendant_pids(process.pid)

    result["descendant_pids"] = descendants

    child_processes = []

    for pid in descendants:
        try:
            child_processes.append(
                psutil.Process(pid)
            )
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied as exc:
            result["errors"].append(
                f"Cannot inspect descendant PID {pid}: {exc}"
            )

    parent_process = None

    try:
        parent_process = psutil.Process(process.pid)
    except psutil.NoSuchProcess:
        pass
    except psutil.AccessDenied as exc:
        result["errors"].append(
            f"Cannot inspect parent PID {process.pid}: {exc}"
        )

    # Step 1: terminate descendants before parent.
    for item in child_processes:
        try:
            item.terminate()

            result["terminated_pids"].append(
                item.pid
            )

        except psutil.NoSuchProcess:
            pass

        except psutil.AccessDenied as exc:
            result["errors"].append(
                f"Terminate PID {item.pid}: {exc}"
            )

    # Step 2: terminate parent.
    if parent_process is not None:
        try:
            parent_process.terminate()

            result["terminated_pids"].append(
                parent_process.pid
            )

        except psutil.NoSuchProcess:
            pass

        except psutil.AccessDenied as exc:
            result["errors"].append(
                f"Terminate parent PID {process.pid}: {exc}"
            )

    # Step 3: wait for descendants to exit.
    if child_processes:
        _, alive = psutil.wait_procs(
            child_processes,
            timeout=GRACEFUL_TERMINATE_SECONDS,
        )
    else:
        alive = []

    # Step 4: force-kill remaining descendants.
    for item in alive:
        try:
            item.kill()

            result["killed_pids"].append(
                item.pid
            )

        except psutil.NoSuchProcess:
            pass

        except psutil.AccessDenied as exc:
            result["errors"].append(
                f"Force-kill PID {item.pid}: {exc}"
            )

    # Step 5: wait for force-killed descendants.
    if alive:
        _, still_alive = psutil.wait_procs(
            alive,
            timeout=FORCE_KILL_SECONDS,
        )
    else:
        still_alive = []

    for item in still_alive:
        result["remaining_pids"].append(
            item.pid
        )

    # Step 6: reap the parent Popen process.
    try:
        process.wait(
            timeout=GRACEFUL_TERMINATE_SECONDS
        )

        result["parent_reaped"] = True

    except subprocess.TimeoutExpired:

        try:
            process.kill()

            result["killed_pids"].append(
                process.pid
            )

            process.wait(
                timeout=FORCE_KILL_SECONDS
            )

            result["parent_reaped"] = True

        except Exception as exc:
            result["errors"].append(
                f"Parent reaping failed: {exc}"
            )

    # Step 7: verify originally discovered descendants.
    for pid in descendants:

        try:
            item = psutil.Process(pid)

            if item.is_running():
                if pid not in result["remaining_pids"]:
                    result["remaining_pids"].append(pid)

        except psutil.NoSuchProcess:
            pass

        except psutil.AccessDenied:
            if pid not in result["remaining_pids"]:
                result["remaining_pids"].append(pid)

    # Step 8: verify parent process is gone.
    if process_exists(process.pid):

        if process.pid not in result["remaining_pids"]:
            result["remaining_pids"].append(process.pid)

    if not result["parent_reaped"]:
        result["status"] = "Failed"

    if result["remaining_pids"]:
        result["status"] = "Failed"

    if result["errors"]:
        result["status"] = "Failed"

    # Test-only negative control.
    # The real cleanup attempt happens before injecting this error.
    if inject_cleanup_failure:

        try:
            raise RuntimeError(
                "TC-REL-01 injected cleanup failure"
            )

        except RuntimeError:
            result["status"] = "Failed"

            result["errors"].append(
                traceback.format_exc()
            )

    return result


def launch_runner(
    seed: int,
    duration: float,
    output_path: Path,
    timeout_seconds: float,
    inject_runner_exception: bool = False,
    inject_cleanup_failure: bool = False,
) -> dict:

    started_at = utc_now()
    wall_start = time.monotonic()

    stdout_path = output_path.with_suffix(
        ".stdout.txt"
    )

    stderr_path = output_path.with_suffix(
        ".stderr.txt"
    )

    result = {
        "seed": seed,
        "requested_duration_s": duration,
        "timeout_seconds": timeout_seconds,
        "started_at_utc": started_at,
        "finished_at_utc": None,
        "pid": None,
        "exit_code": None,
        "timed_out": False,
        "runner_status": "NotStarted",
        "runner_output": None,
        "stdout_file": str(stdout_path.relative_to(ROOT)),
        "stderr_file": str(stderr_path.relative_to(ROOT)),
        "runner_json": str(output_path.relative_to(ROOT)),
        "cleanup": None,
        "supervisor_status": "Failed",
        "exception": None,
    }

    command = [
        sys.executable,
        str(RUNNER),
        "--seed",
        str(seed),
        "--duration",
        str(duration),
        "--output",
        str(output_path),
    ]

    if inject_runner_exception:
        command.append(
            "--inject-runner-exception"
        )

    process = None

    try:

        if not RUNNER.is_file():
            raise FileNotFoundError(RUNNER)

        if output_path.exists():
            raise FileExistsError(output_path)

        stdout_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with stdout_path.open(
            "x",
            encoding="utf-8",
        ) as stdout_file:

            with stderr_path.open(
                "x",
                encoding="utf-8",
            ) as stderr_file:

                process = subprocess.Popen(
                    command,
                    cwd=ROOT,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    stdin=subprocess.DEVNULL,
                    creationflags=(
                        subprocess.CREATE_NEW_PROCESS_GROUP
                        if os.name == "nt"
                        else 0
                    ),
                )

                result["pid"] = process.pid

                try:
                    process.wait(
                        timeout=timeout_seconds
                    )

                except subprocess.TimeoutExpired:
                    result["timed_out"] = True

                # Always perform process cleanup and reaping.
                cleanup = terminate_process_tree(
                    process,
                    inject_cleanup_failure=(
                        inject_cleanup_failure
                    ),
                )

                result["cleanup"] = cleanup
                result["exit_code"] = process.returncode

        # Read the child runner's structured JSON result.
        if output_path.is_file():

            try:
                runner_result = json.loads(
                    output_path.read_text(
                        encoding="utf-8"
                    )
                )

                result["runner_output"] = {
                    "status": runner_result.get("status"),
                    "exception": runner_result.get("exception"),
                    "wall_clock_seconds": (
                        runner_result.get(
                            "wall_clock_seconds"
                        )
                    ),
                    "check_count": len(
                        runner_result.get("checks", [])
                    ),
                    "failed_checks": [
                        check["name"]
                        for check in runner_result.get(
                            "checks", []
                        )
                        if not check.get("passed", False)
                    ],
                }

                result["runner_status"] = (
                    runner_result.get(
                        "status",
                        "Unknown",
                    )
                )

            except Exception:
                result["runner_status"] = "InvalidJSON"

        if result["timed_out"]:

            result["supervisor_status"] = "Failed"

            result["exception"] = {
                "type": "TimeoutExpired",
                "message": (
                    f"Runner exceeded {timeout_seconds} seconds"
                ),
            }

        elif cleanup["status"] != "Passed":

            result["supervisor_status"] = "Failed"

        elif result["exit_code"] != 0:

            result["supervisor_status"] = "Failed"

        elif result["runner_status"] != "Passed":

            result["supervisor_status"] = "Failed"

        else:

            result["supervisor_status"] = "Passed"

    except BaseException as exc:

        result["exception"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }

        if process is not None:

            try:
                result["cleanup"] = terminate_process_tree(
                    process
                )

                result["exit_code"] = process.returncode

            except Exception:
                result["cleanup"] = {
                    "status": "Failed",
                    "errors": [
                        traceback.format_exc()
                    ],
                }

    finally:

        result["finished_at_utc"] = utc_now()

        result["supervisor_wall_clock_seconds"] = (
            time.monotonic() - wall_start
        )

    return result


def run_reliability(stamp: str) -> dict:

    runs = []

    for seed in SEEDS:

        output = (
            EVIDENCE_DIR
            / f"runner_seed{seed}_{stamp}.json"
        )

        print(
            f"Starting reliability run: seed={seed}"
        )

        run = launch_runner(
            seed=seed,
            duration=DURATION_SECONDS,
            output_path=output,
            timeout_seconds=WALL_TIMEOUT_SECONDS,
        )

        runs.append(run)

        print(
            f"Seed {seed}: "
            f"{run['supervisor_status']} "
            f"(exit={run['exit_code']}, "
            f"wall={run['supervisor_wall_clock_seconds']:.3f}s)"
        )

        # Continue with the next seed after an individual failure.

    all_passed = (
        len(runs) == 3
        and all(
            run["supervisor_status"] == "Passed"
            for run in runs
        )
    )

    return {
        "schema_version": 1,
        "test_case": "TC-REL-01",
        "mode": "reliability",
        "status": (
            "Passed" if all_passed else "Failed"
        ),
        "started_at_utc": (
            runs[0]["started_at_utc"]
            if runs
            else utc_now()
        ),
        "finished_at_utc": utc_now(),
        "approved_seeds": list(SEEDS),
        "duration_per_run_s": DURATION_SECONDS,
        "timeout_per_run_s": WALL_TIMEOUT_SECONDS,
        "continue_after_individual_failure": True,
        "runs": runs,
        "pass_rule": (
            "All three independent runs must pass."
        ),
    }


def run_negative_control(
    mode: str,
    stamp: str,
) -> dict:

    inject_exception = (
        mode == "negative-exception"
    )

    inject_cleanup_failure = (
        mode == "negative-cleanup"
    )

    output = (
        EVIDENCE_DIR
        / f"{mode}_{stamp}.json"
    )

    run = launch_runner(
        seed=42,
        duration=2.0,
        output_path=output,
        timeout_seconds=WALL_TIMEOUT_SECONDS,
        inject_runner_exception=inject_exception,
        inject_cleanup_failure=inject_cleanup_failure,
    )

    detected = False
    expected_observation = ""

    if inject_exception:

        detected = (
            run["exit_code"] == 1
            and run["runner_status"] == "Failed"
            and run["runner_output"] is not None
            and run["runner_output"]["exception"] is not None
            and run["cleanup"] is not None
            and run["cleanup"]["status"] == "Passed"
        )

        expected_observation = (
            "Injected runner exception was recorded, "
            "the child exited nonzero, and cleanup succeeded."
        )

    elif inject_cleanup_failure:

        detected = (
            run["runner_status"] == "Passed"
            and run["cleanup"] is not None
            and run["cleanup"]["status"] == "Failed"
            and any(
                "injected cleanup failure" in error
                for error in run["cleanup"]["errors"]
            )
        )

        expected_observation = (
            "Injected cleanup failure was detected "
            "and recorded by the supervisor."
        )

    return {
        "schema_version": 1,
        "test_case": "TC-REL-01",
        "mode": mode,
        "status": (
            "Passed" if detected else "Failed"
        ),
        "started_at_utc": run["started_at_utc"],
        "finished_at_utc": utc_now(),
        "expected_observation": expected_observation,
        "negative_control_detected": detected,
        "run": run,
        "note": (
            "Negative controls use a short 2-second simulation. "
            "They are not acceptance runs."
        ),
    }


def run_process_tree_test(stamp: str) -> dict:
    """
    Start a parent Python process which launches a sleeping
    descendant. Time out the parent and verify both are gone.
    """

    test_dir = (
        EVIDENCE_DIR
        / f"process_tree_{stamp}"
    )

    test_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    marker = test_dir / "descendant_pid.txt"

    stdout_path = test_dir / "parent.stdout.txt"
    stderr_path = test_dir / "parent.stderr.txt"

    child_code = (
        "import time; time.sleep(60)"
    )

    parent_code = (
        "import subprocess, sys, time\n"
        f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
        f"with open({str(marker)!r}, 'w', encoding='utf-8') as f:\n"
        "    f.write(str(child.pid))\n"
        "time.sleep(60)\n"
    )

    command = [
        sys.executable,
        "-c",
        parent_code,
    ]

    started_at = utc_now()
    wall_start = time.monotonic()

    result = {
        "schema_version": 1,
        "test_case": "TC-REL-01",
        "mode": "process-tree-test",
        "status": "Failed",
        "started_at_utc": started_at,
        "finished_at_utc": None,
        "parent_pid": None,
        "descendant_pid": None,
        "timeout_seconds": 2.0,
        "timed_out": False,
        "cleanup": None,
        "checks": [],
        "exception": None,
    }

    process = None

    try:

        with stdout_path.open(
            "x",
            encoding="utf-8",
        ) as stdout_file:

            with stderr_path.open(
                "x",
                encoding="utf-8",
            ) as stderr_file:

                process = subprocess.Popen(
                    command,
                    cwd=ROOT,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    stdin=subprocess.DEVNULL,
                    creationflags=(
                        subprocess.CREATE_NEW_PROCESS_GROUP
                        if os.name == "nt"
                        else 0
                    ),
                )

                result["parent_pid"] = process.pid

                # Wait for the descendant PID marker.
                marker_deadline = (
                    time.monotonic() + 10.0
                )

                while time.monotonic() < marker_deadline:

                    if marker.is_file():
                        break

                    if process.poll() is not None:
                        raise RuntimeError(
                            "Parent exited before creating child PID marker"
                        )

                    time.sleep(0.05)

                if not marker.is_file():
                    raise TimeoutError(
                        "Child PID marker was not created within 10 seconds"
                    )

                result["descendant_pid"] = int(
                    marker.read_text(
                        encoding="utf-8"
                    ).strip()
                )

                # Parent and descendant should still be alive.
                try:
                    process.wait(timeout=2.0)

                except subprocess.TimeoutExpired:
                    result["timed_out"] = True

                # Discover and terminate the actual process tree.
                cleanup = terminate_process_tree(
                    process
                )

                result["cleanup"] = cleanup

        descendant_pid = result["descendant_pid"]

        descendant_gone = (
            not psutil.pid_exists(descendant_pid)
        )

        parent_gone = (
            not psutil.pid_exists(process.pid)
        )

        discovered = (
            descendant_pid
            in cleanup["descendant_pids"]
        )

        checks = [
            {
                "name": "parent_timed_out",
                "expected": True,
                "actual": result["timed_out"],
                "passed": result["timed_out"],
            },
            {
                "name": "descendant_was_discovered",
                "expected": True,
                "actual": discovered,
                "passed": discovered,
            },
            {
                "name": "parent_reaped",
                "expected": True,
                "actual": cleanup["parent_reaped"],
                "passed": cleanup["parent_reaped"],
            },
            {
                "name": "parent_process_gone",
                "expected": True,
                "actual": parent_gone,
                "passed": parent_gone,
            },
            {
                "name": "descendant_process_gone",
                "expected": True,
                "actual": descendant_gone,
                "passed": descendant_gone,
            },
            {
                "name": "cleanup_status",
                "expected": "Passed",
                "actual": cleanup["status"],
                "passed": cleanup["status"] == "Passed",
            },
        ]

        result["checks"] = checks

        result["status"] = (
            "Passed"
            if all(item["passed"] for item in checks)
            else "Failed"
        )

    except BaseException as exc:

        result["exception"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }

        if process is not None:

            try:
                result["cleanup"] = terminate_process_tree(
                    process
                )

            except Exception:
                result["exception"]["cleanup_traceback"] = (
                    traceback.format_exc()
                )

    finally:

        result["finished_at_utc"] = utc_now()

        result["wall_clock_seconds"] = (
            time.monotonic() - wall_start
        )

    return result


def main() -> int:

    parser = argparse.ArgumentParser(
        description="TC-REL-01 process supervisor"
    )

    parser.add_argument(
        "--mode",
        choices=[
            "reliability",
            "negative-exception",
            "negative-cleanup",
            "process-tree-test",
        ],
        default="reliability",
    )

    args = parser.parse_args()

    if not RUNNER.is_file():
        parser.error(
            f"Child runner not found: {RUNNER}"
        )

    EVIDENCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = unique_stamp()

    if args.mode == "reliability":

        summary = run_reliability(stamp)

    elif args.mode == "process-tree-test":

        summary = run_process_tree_test(stamp)

    else:

        summary = run_negative_control(
            args.mode,
            stamp,
        )

    summary_path = (
        EVIDENCE_DIR
        / f"supervisor_{args.mode}_{stamp}.json"
    )

    write_json_new(
        summary_path,
        summary,
    )

    print()
    print("TC-REL-01 supervisor summary")
    print("----------------------------")
    print("Mode:", args.mode)
    print("Status:", summary["status"])
    print(
        "Evidence:",
        summary_path.relative_to(ROOT),
    )

    if args.mode == "process-tree-test":

        for check in summary.get("checks", []):
            print(
                f"{check['name']}: "
                f"{'PASS' if check['passed'] else 'FAIL'}"
            )

    return (
        0 if summary["status"] == "Passed" else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
