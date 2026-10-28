
"""Generate a preliminary acceptance report from a load-test JSON file."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("artifacts/load_test.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/acceptance_report.md"),
    )
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Input report not found: {args.input}")

    data = json.loads(args.input.read_text(encoding="utf-8"))
    results = data.get("results", [])

    if not results:
        parser.error("The load-test report contains no run results.")

    repeatable = all(
        (
            run["vehicles_generated"],
            run["vehicles_entered"],
            run["vehicles_completed"],
            run["vehicles_in_network"],
        )
        == (
            results[0]["vehicles_generated"],
            results[0]["vehicles_entered"],
            results[0]["vehicles_completed"],
            results[0]["vehicles_in_network"],
        )
        for run in results
    )

    all_completed = all(
        run["vehicles_generated"] == run["vehicles_completed"]
        and run["vehicles_in_network"] == 0
        for run in results
    )

    lines = [
        "# Preliminary Acceptance Test Report",
        "",
        f"- Generated (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"- Python version: {data.get('python_version', 'Not recorded')}",
        f"- Platform: {data.get('platform', 'Not recorded')}",
        f"- Scenario: {results[0].get('scenario', 'Not recorded')}",
        f"- Repeated runs: {len(results)}",
        "",
        "## Results",
        "",
        "| Run | Simulated seconds | Elapsed seconds | Generated | Completed | In network |",
        "|---:|---:|---:|---:|---:|---:|",
    ]

    for run in results:
        lines.append(
            f"| {run['run']} | {run['simulated_seconds']:.2f} "
            f"| {run['elapsed_seconds']:.6f} "
            f"| {run['vehicles_generated']} "
            f"| {run['vehicles_completed']} "
            f"| {run['vehicles_in_network']} |"
        )

    lines += [
        "",
        "## Preliminary checks",
        "",
        f"- Repeatability of vehicle counts: {'PASS' if repeatable else 'FAIL'}",
        f"- All generated vehicles completed: {'PASS' if all_completed else 'FAIL'}",
        "- Headless load-test execution: COMPLETED",
        "- GUI frame-rate target: NOT MEASURED",
        "- CPU and memory acceptance thresholds: NOT MEASURED",
        "- Full SRS functional acceptance: NOT YET ESTABLISHED",
        "",
        "## Limitations and follow-up",
        "",
        "These results cover only the scenario and environment recorded above. "
        "Headless execution time is not GUI FPS. CPU/memory measurements, "
        "approved SRS thresholds, larger-load tests, error-handling checks, "
        "and required sign-off must be completed before final acceptance.",
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
