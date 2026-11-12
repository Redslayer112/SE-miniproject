"""Scorecards for the CI/CD run page (.github/workflows/ci.yml).

Each pipeline stage calls one sub-command. It appends a Markdown table to the job summary
($GITHUB_STEP_SUMMARY, shown under the pipeline graph) and writes key=value scores to
$GITHUB_OUTPUT so the final Scorecard job can combine them. Run without those variables
(locally) and it just prints. Standard library only.

  python scripts/ci_report.py lint CRITICAL.json ALL.json src tests scripts
  python scripts/ci_report.py test junit.xml coverage.json
  python scripts/ci_report.py build smoke.txt dist
  python scripts/ci_report.py scorecard        (reads the scores from environment variables)
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

COVERAGE_GATE = 80.0


def emit(markdown: str, outputs: dict[str, object]) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")
    else:
        print(markdown)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.writelines(f"{k}={v}\n" for k, v in outputs.items())
    else:
        print(outputs)


def mark(ok: bool) -> str:
    return "✅ Pass" if ok else "❌ Fail"


def lint(critical_json: str, all_json: str, *dirs: str) -> None:
    critical = json.loads(Path(critical_json).read_text(encoding="utf-8") or "[]")
    style = json.loads(Path(all_json).read_text(encoding="utf-8") or "[]")
    files = sorted(str(p) for d in dirs for p in Path(d).rglob("*.py"))
    dirty = {Path(v["filename"]).resolve() for v in style}
    clean = sum(Path(f).resolve() not in dirty for f in files)
    score = 100.0 * clean / len(files) if files else 100.0
    rules: dict[str, int] = {}
    for v in style:
        rules[v["code"]] = rules.get(v["code"], 0) + 1
    top = ", ".join(f"`{c}` ×{n}" for c, n in sorted(rules.items(), key=lambda kv: -kv[1])[:5]) or "none"
    # Pylint's scoring formula: 10 - 10 * (5 * errors + warnings) / statements, floored at 0.
    statements = sum(isinstance(n, ast.stmt) for f in files
                     for n in ast.walk(ast.parse(Path(f).read_text(encoding="utf-8-sig"))))
    rating = max(0.0, 10.0 - 10.0 * (5 * len(critical) + len(style)) / statements) if statements else 10.0
    emit(
        "## 1 · Lint\n\n"
        "| Check | Result |\n|---|---|\n"
        f"| **Lint score** (pylint formula) | **{rating:.2f} / 10** |\n"
        f"| Python files / statements checked | {len(files)} / {statements} |\n"
        f"| Blocking errors (syntax, undefined names) | **{len(critical)}** · {mark(not critical)} |\n"
        f"| Code warnings (pyflakes: unused imports and variables, non-blocking) | {len(style)} |\n"
        f"| Files with no warnings | {clean}/{len(files)} (**{score:.1f}%**) |\n"
        f"| Most frequent warnings | {top} |\n",
        {"lint_errors": len(critical), "lint_warnings": len(style), "lint_files": len(files),
         "lint_clean_pct": f"{score:.1f}", "lint_score": f"{rating:.2f}"},
    )


def test(junit_xml: str, coverage_json: str) -> None:
    root = ET.parse(junit_xml).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = sum(int(s.get("tests", 0)) for s in suites)
    failed = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    seconds = sum(float(s.get("time", 0)) for s in suites)
    passed = total - failed - errors - skipped
    executed = total - skipped
    rate = 100.0 * passed / executed if executed else 0.0

    t = json.loads(Path(coverage_json).read_text(encoding="utf-8"))["totals"]
    stmt = 100.0 * t["covered_lines"] / t["num_statements"] if t["num_statements"] else 100.0
    branch = 100.0 * t["covered_branches"] / t["num_branches"] if t.get("num_branches") else 100.0
    combined = float(t["percent_covered"])
    emit(
        "## 2 · Test (Windows, Python 3.11)\n\n"
        "| Metric | Result |\n|---|---|\n"
        f"| Tests run | {total} |\n"
        f"| Passed | **{passed}** |\n"
        f"| Failed / errors | {failed} / {errors} |\n"
        f"| Skipped or expected failures | {skipped} |\n"
        f"| Pass rate | **{rate:.1f}%** · {mark(failed == 0 and errors == 0)} |\n"
        f"| Duration | {seconds:.1f} s |\n"
        f"| Statement coverage | {stmt:.1f}% ({t['covered_lines']}/{t['num_statements']}) |\n"
        f"| Branch coverage | {branch:.1f}% ({t.get('covered_branches', 0)}/{t.get('num_branches', 0)}) |\n"
        f"| Combined coverage (gate ≥ {COVERAGE_GATE:.0f}%) | **{combined:.1f}%** · {mark(combined >= COVERAGE_GATE)} |\n",
        {"tests_total": total, "tests_passed": passed, "tests_failed": failed + errors,
         "tests_skipped": skipped, "pass_rate": f"{rate:.1f}", "cov_stmt": f"{stmt:.1f}",
         "cov_branch": f"{branch:.1f}", "cov_combined": f"{combined:.1f}"},
    )


def build(smoke_txt: str, dist_dir: str) -> None:
    text = Path(smoke_txt).read_text(encoding="utf-8")
    m = re.search(r"completed (\d+)", text)
    completed = int(m.group(1)) if m else 0
    m = re.search(r"mean travel time ([\d.]+) s", text)
    travel = m.group(1) if m else "n/a"
    rows = "".join(f"| `{p.name}` | {p.stat().st_size / 1024:.1f} KB |\n" for p in sorted(Path(dist_dir).iterdir()))
    emit(
        "## 3 · Build & smoke test\n\n"
        "| Artifact | Size |\n|---|---|\n" + rows +
        "\n| Smoke test (installed wheel, clean venv) | Result |\n|---|---|\n"
        f"| Sample scenario vehicles completed (expected 30) | **{completed}** · {mark(completed == 30)} |\n"
        f"| Mean travel time | {travel} s |\n",
        {"smoke_completed": completed, "smoke_travel": travel},
    )


def scorecard() -> None:
    e = os.environ.get
    def status(result: str) -> str:
        return {"success": "✅", "failure": "❌", "cancelled": "⚪", "skipped": "⏭️"}.get(result or "", "❔")
    emit(
        "# 🚦 Pipeline scorecard\n\n"
        "| Stage | Status | Score |\n|---|---|---|\n"
        f"| 1 · Lint | {status(e('LINT_RESULT'))} | **{e('LINT_SCORE', '?')} / 10** · "
        f"{e('LINT_ERRORS', '?')} blocking errors · "
        f"{e('LINT_CLEAN', '?')}% files warning-free ({e('LINT_WARNINGS', '?')} code warnings) |\n"
        f"| 2 · Test | {status(e('TEST_RESULT'))} | {e('TESTS_PASSED', '?')}/{e('TESTS_TOTAL', '?')} passed "
        f"(**{e('PASS_RATE', '?')}%**) · {e('TESTS_FAILED', '?')} failed |\n"
        f"| 2 · Coverage | {status(e('TEST_RESULT'))} | **{e('COV_COMBINED', '?')}%** combined "
        f"(statements {e('COV_STMT', '?')}%, branches {e('COV_BRANCH', '?')}%) · gate ≥ {COVERAGE_GATE:.0f}% |\n"
        f"| 3 · Build & smoke test | {status(e('BUILD_RESULT'))} | wheel + sdist built · "
        f"{e('SMOKE_COMPLETED', '?')}/30 vehicles · {e('SMOKE_TRAVEL', '?')} s mean travel time |\n"
        f"| 4 · Release | {'runs on `v*` tags' if e('IS_TAG') != 'true' else status(e('RELEASE_RESULT'))} | "
        "GitHub Release with wheel, sdist and SRS/SAD/Test Plan v1.1 |\n",
        {},
    )


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    {"lint": lint, "test": test, "build": build, "scorecard": scorecard}[command](*args)
