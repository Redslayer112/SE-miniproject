
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_load_test_script_creates_report(tmp_path):
    output = tmp_path / "load_test.json"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_load_test.py"),
            "--repeat", "2",
            "--output", str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(report["results"]) == 2
    assert all(r["vehicles_generated"] == 30 for r in report["results"])
    assert all(r["vehicles_completed"] == 30 for r in report["results"])


def test_acceptance_report_script_creates_markdown(tmp_path):
    source = tmp_path / "load_test.json"
    output = tmp_path / "acceptance_report.md"

    source.write_text(
        json.dumps({
            "python_version": "3.13.7",
            "platform": "Test platform",
            "results": [
                {
                    "run": i,
                    "scenario": "sample.json",
                    "simulated_seconds": 600.0,
                    "elapsed_seconds": 0.05,
                    "vehicles_generated": 30,
                    "vehicles_entered": 30,
                    "vehicles_completed": 30,
                    "vehicles_in_network": 0,
                }
                for i in (1, 2)
            ],
        }),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "acceptance_report.py"),
            "--input", str(source),
            "--output", str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    report = output.read_text(encoding="utf-8")
    assert "Repeatability of vehicle counts: PASS" in report
    assert "All generated vehicles completed: PASS" in report
    assert "GUI frame-rate target: NOT MEASURED" in report
    assert "Final acceptance: Pending" in report
