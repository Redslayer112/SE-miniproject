# TMS Branch Coverage Report

**Traffic Management System (Simulation)** · Software Engineering UE24CS341A · PES University

| Team member | SRN |
|---|---|
| Venkata Srivaibhav Nukaraju | PES2UG24CS579 |
| V Vyas | PES2UG24CS569 |
| Vikas N Naik | PES2UG24CS583 |
| Vikhyath Bharadwaj K S | PES2UG24CS586 |

**Report ID:** TMS-TR-BCOV-02 (supersedes TMS-TR-BCOV-01 of 6 November 2026)  
**Date:** 12 November 2026  
**Code measured:** `main` at commit `4366043` (merge of PR #47)


**Tool:** coverage.py 7.17.2 with branch tracing enabled (`--branch`)  
**Measured source:** `src/tms_sim/`

## 1. Method

```bash
QT_QPA_PLATFORM=offscreen python -m coverage run --branch --source=src/tms_sim -m pytest -q
python -m coverage report -m
python -m coverage json --pretty-print -o docs/coverage_data_2026-11-12.json
```

Environment: Linux (Kali), CPython 3.14.8, pytest 9.2.0, PySide6 6.12.0, coverage.py 7.17.2, `QT_QPA_PLATFORM=offscreen`. Pytest reported 597 passed and exited 0.

A branch arc is one possible direction from a decision point (for example the true and the false side of an `if`). A branch point is *partially covered* when at least one but not every arc from it was taken.

## 2. Overall result

| Measure | Result |
|---|---:|
| Branch arcs | 1,612 |
| Branch arcs covered | 1,208 |
| Missing branch arcs | 404 |
| **Branch coverage** | **74.94%** |
| Partially covered branch points | 292 |
| Statement coverage (for reference) | 88.40% |
| coverage.py combined statement + branch figure | 85.54% |

Outside the user interface, branch coverage is **89.9%** (527 of 586 arcs). In `ui/` it is **66.4%** (681 of 1026 arcs).

## 3. Branch coverage by module

| Module (`src/tms_sim/`) | Branch arcs covered / total | Branch coverage | Missing arcs | Partial points |
|---|---:|---:|---:|---:|
| `__main__.py` | 0 / 8 | 0.0% | 8 | 0 |
| `network/serialization.py` | 21 / 24 | 87.5% | 3 | 1 |
| `network/service.py` | 4 / 4 | 100.0% | 0 | 0 |
| `network/validation.py` | 59 / 62 | 95.2% | 3 | 3 |
| `reporting/comparison.py` | 44 / 52 | 84.6% | 8 | 8 |
| `reporting/export.py` | 55 / 62 | 88.7% | 7 | 5 |
| `reporting/history.py` | 23 / 26 | 88.5% | 3 | 3 |
| `reporting/metrics.py` | 51 / 64 | 79.7% | 13 | 7 |
| `signal/conflicts.py` | 8 / 10 | 80.0% | 2 | 2 |
| `signal/model.py` | 20 / 22 | 90.9% | 2 | 2 |
| `signal/serialization.py` | 4 / 6 | 66.7% | 2 | 0 |
| `signal/service.py` | 6 / 6 | 100.0% | 0 | 0 |
| `signal/validation.py` | 40 / 40 | 100.0% | 0 | 0 |
| `sim/demand.py` | 24 / 24 | 100.0% | 0 | 0 |
| `sim/engine.py` | 66 / 66 | 100.0% | 0 | 0 |
| `sim/scenario.py` | 45 / 46 | 97.8% | 1 | 1 |
| `sim/serialization.py` | 32 / 34 | 94.1% | 2 | 2 |
| `storage/store.py` | 25 / 30 | 83.3% | 5 | 5 |
| `ui/app.py` | 528 / 768 | 68.8% | 240 | 196 |
| `ui/charts.py` | 28 / 38 | 73.7% | 10 | 10 |
| `ui/comparison.py` | 53 / 102 | 52.0% | 49 | 21 |
| `ui/history.py` | 15 / 18 | 83.3% | 3 | 1 |
| `ui/library.py` | 17 / 24 | 70.8% | 7 | 7 |
| `ui/run_history.py` | 40 / 76 | 52.6% | 36 | 18 |

Files with no branches: `__init__.py`, `network/__init__.py`, `network/model.py`, `reporting/__init__.py`, `signal/__init__.py`, `sim/__init__.py`, `storage/__init__.py`, `ui/__init__.py`.

## 4. Observations

- Modules with every branch arc covered: `network/service.py`, `signal/service.py`, `signal/validation.py`, `sim/demand.py`, `sim/engine.py`.
- Lowest branch coverage: `__main__.py` (0.0%, 0/8), `ui/comparison.py` (52.0%, 53/102), `ui/run_history.py` (52.6%, 40/76), `signal/serialization.py` (66.7%, 4/6), `ui/app.py` (68.8%, 528/768).
- 345 of the 404 missing branch arcs (85%) are in the desktop UI (`ui/`); `ui/app.py` alone has 240.
- The command-line entry point `__main__.py` is not executed by the pytest suite and is reported at 0%.

## 5. Change since 6 November 2026

| | 6 Nov (457 tests) | 12 November (597 tests) |
|---|---:|---:|
| Branch arcs covered / total | 1,151 / 1,580 (72.85%) | 1,208 / 1,612 (74.94%) |
| Partially covered branch points | 311 | 292 |

## 6. Interpretation and limits

Branch coverage is stricter than statement coverage because it checks that both outcomes of each decision ran. It still does not prove the outcomes were checked by an assertion. Figures apply to commit `4366043` in the environment above. Exact missing arcs are in `docs/coverage_data_2026-11-12.json`.
