# TMS Code Coverage Report

**Report ID:** TMS-TR-COV-01
**Date:** 6 November 2026
**Project:** Traffic Management System (Simulation), UE24CS341A, PES University
**Tool:** coverage.py 7.17.0 with C extension
**Scope:** Python source files under `src/tms_sim/`; tests and scripts are not included in the coverage denominator.

## Method and result

Coverage was measured with branch tracing during the complete pytest suite:

```powershell
$env:COVERAGE_FILE='.coverage-s3-53adad7fffd24c3f8cafbca7103352f1'
python -m coverage run --branch --source=src/tms_sim -m pytest -q --basetemp .pytest-tmp-s3-coverage-53adad7fffd24c3f8cafbca7103352f1
python -m coverage report -m
python -m coverage json --pretty-print -o docs/coverage_data_issue34_2026-11-06.json
```

Pytest reported 457 passed in 35.88 seconds, 0 failures and 0 skips, but the Python process exited `-1073740791` (`0xC0000409`). `coverage report -m` and JSON generation exited 0. The report was generated from the coverage data despite the abnormal pytest process exit; treat it as observed executed-line/branch evidence with that limitation.

| Measure | Result |
|---|---:|
| Executable statements | 5,895 |
| Statements covered | 5,186 |
| Statement coverage | **87.97% (88% rounded)** |
| Missing statements | 709 |
| Branch arcs | 1,580 |
| Branch arcs covered | 1,151 |
| Branch coverage | **72.85% (73% rounded)** |
| Missing branch arcs | 429 |
| Partially covered branch points | 311 |
| coverage.py combined statement + branch display | **84.78% (85% rounded)** |

The combined coverage.py “Cover” percentage is not statement-only coverage. Statement and branch percentages are stated separately above. The raw per-file result, including exact missing line/branch locations, is `docs/coverage_data_issue34_2026-11-06.json`.

## Module observations

Strong statement coverage includes simulation demand and engine (100% each), network model/service (100%), signal validation/service (100%), and reporting history (100%). Lower areas needing test attention include the CLI entry point (`src/tms_sim/__main__.py`, 0% statements), UI comparison (73.0% statements / 52.0% branches), UI run history (85.0% / 52.6%), UI application (87.1% / 67.4%), metrics (92.6% / 73.5%), and scenario serialization (84.0% / 75.0%). The entry point is not exercised by the current pytest suite; UI and error-handling paths account for many uncovered branches. The JSON file lists exact misses.

| Source module | Statements covered / total | Statement coverage |
|---|---:|---:|
| `__init__.py` | 0 / 0 | N/A (no executable statements; no measurable branches) |
| `__main__.py` | 0 / 30 | 0.0% |
| `network/__init__.py` | 5 / 5 | 100.0% |
| `network/model.py` | 32 / 32 | 100.0% |
| `network/serialization.py` | 79 / 84 | 94.0% |
| `network/service.py` | 26 / 26 | 100.0% |
| `network/validation.py` | 101 / 104 | 97.1% |
| `reporting/__init__.py` | 4 / 4 | 100.0% |
| `reporting/comparison.py` | 131 / 141 | 92.9% |
| `reporting/export.py` | 160 / 167 | 95.8% |
| `reporting/history.py` | 74 / 74 | 100.0% |
| `reporting/metrics.py` | 163 / 176 | 92.6% |
| `signal/__init__.py` | 6 / 6 | 100.0% |
| `signal/conflicts.py` | 32 / 34 | 94.1% |
| `signal/model.py` | 56 / 58 | 96.6% |
| `signal/serialization.py` | 43 / 47 | 91.5% |
| `signal/service.py` | 35 / 35 | 100.0% |
| `signal/validation.py` | 63 / 63 | 100.0% |
| `sim/__init__.py` | 0 / 0 | N/A (no executable statements) |
| `sim/demand.py` | 51 / 51 | 100.0% |
| `sim/engine.py` | 172 / 172 | 100.0% |
| `sim/scenario.py` | 67 / 72 | 93.1% |
| `sim/serialization.py` | 63 / 75 | 84.0% |
| `storage/__init__.py` | 0 / 0 | N/A (no executable statements) |
| `storage/store.py` | 114 / 124 | 91.9% |
| `ui/__init__.py` | 0 / 0 | N/A (no executable statements) |
| `ui/app.py` | 2,595 / 2,981 | 87.1% |
| `ui/charts.py` | 245 / 256 | 95.7% |
| `ui/comparison.py` | 336 / 460 | 73.0% |
| `ui/history.py` | 56 / 61 | 91.8% |
| `ui/library.py` | 110 / 125 | 88.0% |
| `ui/run_history.py` | 367 / 432 | 85.0% |

Coverage.py discovered 32 source files. The four files with no executable statements (`__init__.py`, `sim/__init__.py`, `storage/__init__.py`, and `ui/__init__.py`) are listed as N/A rather than counted as covered module logic; none has measurable branches.

## Interpretation and limits

Coverage quantifies executed Python lines and control-flow arcs, not correctness, requirement completion, mutation resistance, or acceptance. Generated statements/branches are measured for the current working tree and environment. The repository has no pytest-cov configuration; direct coverage.py instrumentation was used. Do not treat any percentage as a faculty-approved quality threshold unless one is separately approved.
