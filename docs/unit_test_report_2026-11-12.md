# TMS Unit and Automated Test Report

**Traffic Management System (Simulation)** · Software Engineering UE24CS341A · PES University

| Team member | SRN |
|---|---|
| Venkata Srivaibhav Nukaraju | PES2UG24CS579 |
| V Vyas | PES2UG24CS569 |
| Vikas N Naik | PES2UG24CS583 |
| Vikhyath Bharadwaj K S | PES2UG24CS586 |

**Report ID:** TMS-TR-UT-02 (supersedes TMS-TR-UT-01 of 6 November 2026)  
**Date:** 12 November 2026  
**Code measured:** `main` at commit `4366043` (merge of PR #47)


**Scope:** the complete pytest suite under `tests/` (unit, integration, offscreen UI and acceptance-script tests).

## 1. Result

| Run | Environment | Command | Result | Duration | Process exit |
|---|---|---|---|---:|---:|
| Collection | Linux (Kali), CPython 3.14.8, pytest 9.2.0, PySide6 6.12.0, coverage.py 7.17.2, `QT_QPA_PLATFORM=offscreen` | `python -m pytest --collect-only -q` | **597 tests collected** | 0.3 s | 0 |
| Full suite (coverage-instrumented) | Linux (Kali), CPython 3.14.8, pytest 9.2.0, PySide6 6.12.0, coverage.py 7.17.2, `QT_QPA_PLATFORM=offscreen` | `python -m coverage run --branch --source=src/tms_sim -m pytest -q --junitxml=junit.xml` | **597 passed; 0 failed; 0 skipped; 0 expected failures** | 17.4 s | **0** |
| Full suite on the target platform | GitHub Actions `windows-latest`, Python 3.11 (run [43161235305](https://github.com/Redslayer112/SE-miniproject/actions/runs/43161235305)) | `python -m pytest` | **597 passed** | 27.05 s | **0** (`PYTEST_PROCESS_EXIT_CODE=0`) |

**Status: PASS (597/597).** Both environments report all tests passing and a clean process exit. The result was produced on the same commit in two independent environments.

## 2. Tests by area

| Area | Test files | Test cases |
|---|---:|---:|
| Network model and validation | 1 | 33 |
| Signal plans and conflict detection | 2 | 82 |
| Vehicle demand generation | 1 | 22 |
| Simulation engine (IDM, signals, gap acceptance, controls) | 2 | 45 |
| Scenario assembly, validation and serialization | 3 | 63 |
| Scenario library and run storage (SQLite) | 1 | 29 |
| Metrics, comparison and CSV/HTML export | 3 | 61 |
| Desktop UI (editing, signals, playback, charts, history, comparison, library) | 14 | 197 |
| System integration (SI-01 to SI-08) | 1 | 19 |
| Acceptance and reliability scripts | 1 | 45 |
| Smoke | 1 | 1 |
| **Total** | **30** | **597** |

### Test cases per file

| File | Cases |
|---|---:|
| `tests/signal/test_reference_fixtures.py` | 9 |
| `tests/signal/test_signal_plan.py` | 73 |
| `tests/test_acceptance_scripts.py` | 45 |
| `tests/test_demand.py` | 22 |
| `tests/test_engine.py` | 18 |
| `tests/test_engine_regressions.py` | 27 |
| `tests/test_metrics.py` | 15 |
| `tests/test_network.py` | 33 |
| `tests/test_reporting_export.py` | 27 |
| `tests/test_scenario.py` | 10 |
| `tests/test_scenario_comparison.py` | 19 |
| `tests/test_scenario_serialization.py` | 36 |
| `tests/test_scenario_validation.py` | 17 |
| `tests/test_smoke.py` | 1 |
| `tests/test_store.py` | 29 |
| `tests/test_system_integration.py` | 19 |
| `tests/test_ui_demand_editor.py` | 10 |
| `tests/test_ui_issue29_stabilization.py` | 7 |
| `tests/test_ui_network_editing.py` | 18 |
| `tests/test_ui_performance_charts.py` | 15 |
| `tests/test_ui_playback_controls.py` | 26 |
| `tests/test_ui_polish.py` | 7 |
| `tests/test_ui_results_dashboard.py` | 14 |
| `tests/test_ui_run_history.py` | 13 |
| `tests/test_ui_scenario_library.py` | 9 |
| `tests/test_ui_scenario_loading.py` | 10 |
| `tests/test_ui_scenario_management.py` | 21 |
| `tests/test_ui_signal_editor.py` | 13 |
| `tests/test_ui_signal_visualization_and_zoom.py` | 15 |
| `tests/test_ui_undo_redo.py` | 19 |

## 3. What the tests check

- **Boundary and negative cases:** invalid networks (disconnected, zero-length or zero-lane segments, missing receiving lane), conflicting or invalid signal plans, invalid demand, malformed and wrong-version scenario files, unsupported speeds, non-JSON run data, and name clashes in the library. Each must be refused with an actionable message and nothing stored.
- **Engine behaviour:** hand-checked IDM values, no vehicle overlap and no negative speed at every step on both reference scenarios, red-signal holding and release, gap acceptance, pause/step/reset, stopping at the configured duration with a single finalization, and identical results for the same seed.
- **Persistence:** save, list, load, duplicate, rename and delete; restart persistence; export then import on a clean store; a run record that reloads after its scenario is deleted.
- **User interface (offscreen Qt):** editing tools with undo and redo, signal editor, demand editor, playback controls, charts and dashboard, run history, comparison, scenario library, zoom and pan.
- **Integration:** the eight system workflows SI-01 to SI-08 (see the System Validation Report).

## 4. Defects found by testing and the tests that now guard them

| Defect | Fixed in | Regression test |
|---|---|---|
| A car could cross a short segment in one step and run its red light | PR #38 | `test_short_segment_red_is_never_jumped` (9 cases) |
| One jammed entry stopped every other entry from spawning | PR #38 | `test_jammed_entry_does_not_hold_back_other_entries`, `test_spawn_stays_fifo_within_an_entry` |
| Simulated clock drifted (600 steps of 0.1 s ended at 60.00000000000058) | PR #38 | `test_clock_is_exact_and_stops_on_duration` (4 cases), `test_event_times_are_whole_steps` |
| Stop/yield-only scenarios could run but could not be saved or imported (SI-D1) | PR #40 | `test_stop_yield_scenario_yields_and_saves_without_signal_plans` |
| A run after loading another scenario was not captured in history (SI-D2) | Sprint 3 | `test_run_after_library_load_is_auto_captured` |
| Deleting the last signal plan made the scenario unsaveable (SI-D3) | Sprint 3 | `test_removing_last_plan_in_workbench_keeps_scenario_saveable` |
| Intermittent non-zero process exit after all tests passed on Windows CI (Qt objects destroyed after the application) | PR #25 | explicit teardown in `tests/conftest.py`; 20 of 20 consecutive CI reruns passed |

Test effectiveness: when PR #38 was prepared, the new engine regression tests were run against the previous engine; 13 of the 27 tests in `tests/test_engine_regressions.py` failed there and all pass now.

## 5. Changes since the report of 6 November 2026

- The suite grew from 457 to 597 tests.
- The 6 November local Windows runs ended with exit status `-1073740791` (`0xC0000409`) after the pytest summary. In the runs recorded here, on Linux and on the Windows CI runner, the exit status is 0. The residual native shutdown abort on some Windows hosts is listed as a known limitation in `docs/FINAL_PROJECT_OVERVIEW.md` (K-3).
- The two strict expected-failure tests (SI-06a, SI-08a) now pass, so the suite has no expected failures.

## 6. Limitations

- The user-interface tests drive the real widgets offscreen; they are not human usability evidence (TC-UX-01 was not performed).
- The suite was run here on Linux and on the Windows CI runner, not on clean Windows 10 or Windows 11 installations (TC-PORT-01 was not performed).
- Test counts apply to commit `4366043`.

Coverage figures for this run are in the Code Coverage and Branch Coverage Reports; the raw data is `docs/coverage_data_2026-11-12.json`.
