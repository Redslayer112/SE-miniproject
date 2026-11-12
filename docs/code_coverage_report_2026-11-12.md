# TMS Code Coverage Report

**Traffic Management System (Simulation)** · Software Engineering UE24CS341A · PES University

| Team member | SRN |
|---|---|
| Venkata Srivaibhav Nukaraju | PES2UG24CS579 |
| V Vyas | PES2UG24CS569 |
| Vikas N Naik | PES2UG24CS583 |
| Vikhyath Bharadwaj K S | PES2UG24CS586 |

**Report ID:** TMS-TR-COV-02 (supersedes TMS-TR-COV-01 of 6 November 2026)  
**Date:** 12 November 2026  
**Code measured:** `main` at commit `4366043` (merge of PR #47)


**Tool:** coverage.py 7.17.2 with branch tracing, run under pytest  
**Scope:** Python source under `src/tms_sim/`. Tests and scripts are not in the denominator.

## 1. Method

```bash
QT_QPA_PLATFORM=offscreen python -m coverage run --branch --source=src/tms_sim -m pytest -q
python -m coverage report -m
python -m coverage json --pretty-print -o docs/coverage_data_2026-11-12.json
```

Environment: Linux (Kali), CPython 3.14.8, pytest 9.2.0, PySide6 6.12.0, coverage.py 7.17.2, `QT_QPA_PLATFORM=offscreen`. Pytest reported 597 passed and exited 0; the coverage report and JSON commands also exited 0.

## 2. Result

| Measure | Result |
|---|---:|
| Source files measured | 32 (28 with executable statements) |
| Executable statements | 5,973 |
| Statements covered | 5,280 |
| Missing statements | 693 |
| **Statement coverage** | **88.40%** |
| coverage.py combined statement + branch figure | 85.54% |

The combined figure is what `coverage report` prints as "Cover"; it is not statement-only coverage. Branch coverage is reported separately in the Branch Coverage Report (74.94%).

## 3. Coverage by module

| Module (`src/tms_sim/`) | Statements covered / total | Statement coverage | Missing |
|---|---:|---:|---:|
| `__init__.py` | 0 / 0 | N/A (no executable statements) | 0 |
| `__main__.py` | 0 / 30 | 0.0% | 30 |
| `network/__init__.py` | 5 / 5 | 100.0% | 0 |
| `network/model.py` | 32 / 32 | 100.0% | 0 |
| `network/serialization.py` | 79 / 84 | 94.0% | 5 |
| `network/service.py` | 26 / 26 | 100.0% | 0 |
| `network/validation.py` | 101 / 104 | 97.1% | 3 |
| `reporting/__init__.py` | 4 / 4 | 100.0% | 0 |
| `reporting/comparison.py` | 133 / 141 | 94.3% | 8 |
| `reporting/export.py` | 172 / 179 | 96.1% | 7 |
| `reporting/history.py` | 74 / 74 | 100.0% | 0 |
| `reporting/metrics.py` | 158 / 171 | 92.4% | 13 |
| `signal/__init__.py` | 6 / 6 | 100.0% | 0 |
| `signal/conflicts.py` | 32 / 34 | 94.1% | 2 |
| `signal/model.py` | 56 / 58 | 96.6% | 2 |
| `signal/serialization.py` | 43 / 47 | 91.5% | 4 |
| `signal/service.py` | 35 / 35 | 100.0% | 0 |
| `signal/validation.py` | 63 / 63 | 100.0% | 0 |
| `sim/__init__.py` | 0 / 0 | N/A (no executable statements) | 0 |
| `sim/demand.py` | 54 / 54 | 100.0% | 0 |
| `sim/engine.py` | 179 / 179 | 100.0% | 0 |
| `sim/scenario.py` | 105 / 107 | 98.1% | 2 |
| `sim/serialization.py` | 77 / 82 | 93.9% | 5 |
| `storage/__init__.py` | 0 / 0 | N/A (no executable statements) | 0 |
| `storage/store.py` | 114 / 124 | 91.9% | 10 |
| `ui/__init__.py` | 0 / 0 | N/A (no executable statements) | 0 |
| `ui/app.py` | 2618 / 2999 | 87.3% | 381 |
| `ui/charts.py` | 244 / 256 | 95.3% | 12 |
| `ui/comparison.py` | 337 / 461 | 73.1% | 124 |
| `ui/history.py` | 56 / 61 | 91.8% | 5 |
| `ui/library.py` | 110 / 125 | 88.0% | 15 |
| `ui/run_history.py` | 367 / 432 | 85.0% | 65 |

## 4. Observations

- Modules with every statement covered: `network/__init__.py`, `network/model.py`, `network/service.py`, `reporting/__init__.py`, `reporting/history.py`, `signal/__init__.py`, `signal/service.py`, `signal/validation.py`, `sim/demand.py`, `sim/engine.py`.
- Lowest statement coverage: `__main__.py` (0.0%), `ui/comparison.py` (73.1%), `ui/run_history.py` (85.0%), `ui/app.py` (87.3%), `ui/library.py` (88.0%).
- Coverage by package: `sim/` 98.3% (415/422), `network/` 96.8% (243/251), `signal/` 96.7% (235/243), `reporting/` 95.1% (541/569), `storage/` 91.9% (114/124), `ui/` 86.1% (3732/4334).
- 602 of the 693 missing statements (87%) are in the desktop UI (`ui/`).
- `__main__.py` (the command-line entry point) is not executed by the pytest suite; `python -m tms_sim run` on the sample scenario was run manually and completed 30 vehicles.
- `__init__.py` files with no executable statements are listed as N/A and not counted as covered logic.

## 5. Change since 6 November 2026

| | 6 Nov (457 tests) | 12 November (597 tests) |
|---|---:|---:|
| Statements | 5,186 / 5,895 (87.97%) | 5,280 / 5,973 (88.40%) |

## 6. Interpretation and limits

Coverage shows which statements ran during the tests. It does not show that the behaviour is correct, that a requirement is satisfied, or that the tests would catch every defect; those claims rest on the requirement-level evidence in the System Validation Report and the RTM. Figures apply to commit `4366043` in the environment above. Raw per-file data, including exact missing lines, is in `docs/coverage_data_2026-11-12.json`.
