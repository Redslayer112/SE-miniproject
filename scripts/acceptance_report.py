
"""Generate a preliminary acceptance report from load-test JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path("artifacts/load_test.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/acceptance_report.md")
    )
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Input report not found: {args.input}")

    data = json.loads(args.input.read_text(encoding="utf-8"))
    results = data.get("results", [])
    if not results:
        parser.error("The load-test report contains no run results.")

    first = results[0]
    count_keys = (
        "vehicles_generated",
        "vehicles_entered",
        "vehicles_completed",
        "vehicles_in_network",
    )
    repeatable = all(
        all(run.get(key) == first.get(key) for key in count_keys)
        for run in results
    )
    all_completed = all(
        run.get("vehicles_generated") == run.get("vehicles_completed")
        and run.get("vehicles_in_network") == 0
        for run in results
    )

    lines = [
        "# Preliminary Acceptance Test Report",
        "",
        f"- Generated (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"- Python version: {data.get('python_version', 'Not recorded')}",
        f"- Platform: {data.get('platform', 'Not recorded')}",
        f"- Scenario: {first.get('scenario', 'Not recorded')}",
        f"- Repeated runs: {len(results)}",
        "",
        "## Results",
        "",
        "| Run | Simulated seconds | Elapsed seconds | CPU seconds | Peak Python memory (bytes) | Generated | Completed | In network |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for run in results:
        lines.append(
            f"| {run.get('run', '?')} "
            f"| {run['simulated_seconds']:.2f} "
            f"| {run['elapsed_seconds']:.6f} "
            f"| {run.get('cpu_seconds', 0):.6f} "
            f"| {run.get('peak_python_memory_bytes', 0)} "
            f"| {run['vehicles_generated']} "
            f"| {run['vehicles_completed']} "
            f"| {run['vehicles_in_network']} |"
        )

    summary = data.get("summary", {})
    lines += [
        "",
        "## Resource summary",
        "",
        f"- Mean elapsed time: {summary.get('mean_elapsed_seconds', 'Not recorded')} seconds",
        f"- Mean CPU time: {summary.get('mean_cpu_seconds', 'Not recorded')} seconds",
        f"- Maximum traced Python memory: {summary.get('max_peak_python_memory_bytes', 'Not recorded')} bytes",
        "",
        "## Preliminary checks",
        "",
        f"- Repeatability of vehicle counts: {'PASS' if repeatable else 'FAIL'}",
        f"- All generated vehicles completed: {'PASS' if all_completed else 'FAIL'}",
        "- Headless load-test execution: COMPLETED",
        "- GUI frame-rate target (15 FPS): NOT MEASURED",
        "- Total process RAM: NOT MEASURED",
        "- CPU/memory acceptance thresholds: NOT SPECIFIED",
        "- Full SRS functional acceptance: NOT YET ESTABLISHED",
        "",
        "## Limitations and follow-up",
        "",
        "The run measures headless execution. Traced Python memory is not total process RAM. "
        "The scenario generated the recorded number of vehicles, which may differ from "
        "the nominal arrival-rate target. GUI FPS, approved resource thresholds, "
        "and remaining acceptance scenarios require separate evidence.",
        "",
        "## Sign-off",
        "",
        "- Tester: Pending",
        "- Reviewer: Pending",
        "- Final acceptance: Pending",
        "",
    ]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Acceptance report saved to: {args.output}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
