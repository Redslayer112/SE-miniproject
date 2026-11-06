# TMS Branch Coverage Report

**Report ID:** TMS-TR-BCOV-01
**Date:** 6 November 2026
**Project:** Traffic Management System (Simulation), UE24CS341A, PES University
**Tool:** coverage.py 7.17.0, branch tracing enabled
**Measured source:** `src/tms_sim/`

## Overall result

The coverage-instrumented command was `python -m coverage run --branch --source=src/tms_sim -m pytest -q --basetemp .pytest-tmp-s3-coverage-53adad7fffd24c3f8cafbca7103352f1`. Pytest reported 457 passed in 35.88 seconds; the process exited `-1073740791` (`0xC0000409`) after the pytest summary. The coverage report command completed with exit 0.

Coverage.py recorded **1,151 of 1,580 branch arcs covered (72.85%)**, with **429 branch arcs missing** and **311 partially covered branch points**. Line statement coverage was 87.97%. Raw per-file missing branch locations are in `docs/coverage_data_issue34_2026-11-06.json`.

## Module branch coverage

| Module | Covered / total branch arcs | Branch coverage |
|---|---:|---:|
| `network/serialization.py` | 21 / 24 | 87.5% |
| `network/service.py` | 4 / 4 | 100% |
| `network/validation.py` | 59 / 62 | 95.2% |
| `reporting/comparison.py` | 41 / 52 | 78.8% |
| `reporting/export.py` | 49 / 56 | 87.5% |
| `reporting/history.py` | 23 / 26 | 88.5% |
| `reporting/metrics.py` | 50 / 68 | 73.5% |
| `signal/conflicts.py` | 8 / 10 | 80.0% |
| `signal/model.py` | 20 / 22 | 90.9% |
| `signal/serialization.py` | 4 / 6 | 66.7% |
| `signal/service.py` | 6 / 6 | 100% |
| `signal/validation.py` | 40 / 40 | 100% |
| `sim/demand.py` | 24 / 24 | 100% |
| `sim/engine.py` | 56 / 56 | 100% |
| `sim/scenario.py` | 27 / 30 | 90.0% |
| `sim/serialization.py` | 21 / 28 | 75.0% |
| `storage/store.py` | 25 / 30 | 83.3% |
| `ui/app.py` | 519 / 770 | 67.4% |
| `ui/charts.py` | 29 / 38 | 76.3% |
| `ui/comparison.py` | 53 / 102 | 52.0% |
| `ui/history.py` | 15 / 18 | 83.3% |
| `ui/library.py` | 17 / 24 | 70.8% |
| `ui/run_history.py` | 40 / 76 | 52.6% |

Files with no decision branches are omitted from this table; the raw JSON includes all 32 measured files. coverage.py treats an uncovered side of a conditional as a missing branch arc; it does not imply a branch defect.

## Important uncovered areas

The largest branch gaps are in UI comparison and run-history flows, followed by the main UI application and metrics edge cases. Recommended follow-up is to prioritize error/empty states, cancellation and dialog branches, incompatible or unavailable comparison metrics, storage failures, and lifecycle transitions. The CLI entry point has no branch coverage because the tests invoke application APIs rather than the package entry point. These are observations for test planning, not proof of incorrect behavior.

No branch-coverage target is defined by the source SRS/STP. The measured percentage is evidence, not a pass/fail acceptance threshold.
