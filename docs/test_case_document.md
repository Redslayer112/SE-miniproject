# Traffic Management System (TMS) — Test Case Document

**Document ID:** TMS-TCD-01
**Version:** 1.0
**Date:** 6 November 2026
**Project:** Traffic Management System (Simulation), UE24CS341A, PES University
**Status:** Updated for Sprint 3 review; planned procedures and execution evidence are distinguished below.

## 1. Purpose and objectives

This document expands the existing STP case catalogue into executable test procedures. It preserves the established IDs in `docs/test_catalogue.md`, adds supplemental integration, UI, error-handling and regression cases, and links cases to current automated test modules where a clear mapping exists. It does not change or approve requirements in the SRS, SAD or STP.

Objectives are to verify network and signal validation, seeded demand and engine behavior, UI workflows, reported metrics, storage and exports, error handling, deterministic repeatability, and the documented non-functional criteria. A pytest assertion result is component/integration evidence; it does not by itself establish a manual system-acceptance result.

## 2. Source documents and scope

Sources: The normative requirements and design baselines are SRS v0.2, SAD v1.0 and STP v1.0. Consolidated document editions are available as `docs/SRS_v1.1.docx`, `docs/SAD_v1.1.docx` and `docs/Test_Plan_v1.1.docx`, with corresponding PDF versions. The v1.1 package edition does not independently change or approve the normative requirements baseline. Other sources include `docs/test_catalogue.md`, `docs/RTM.csv` and the Issue #12 acceptance evidence.

The SRS/STP reference Windows 10/11, Python 3.11 and PySide6, with a stated reference system of Intel i5-11400H and 16 GB RAM. The latest local test run used Windows 11 build 26300, CPython 3.13.7, PySide6 6.12.0 and pytest 9.1.0; this is not the SRS reference CPU environment.

In scope: road networks, signal plans, demand, simulation and controls, UI/visualization, metrics, run/scenario persistence, comparison, reporting/export, integration, error/boundary behavior, regression, and NFR acceptance procedures. Out of scope per STP: field hardware, 3D, distributed simulation, advanced lane changing, field-data calibration, transit scheduling, and pedestrian/cyclist microsimulation.

## 3. Environment and prerequisites

- Python 3.11 or later, project dependencies from `pyproject.toml`, pytest and a supported PySide6 environment.
- Run from the repository root with `src/` importable; pytest configuration is in `pyproject.toml` (`testpaths = ["tests"]`).
- UI tests use the offscreen Qt platform. `tests/conftest.py` redirects the default scenario database into each test's `tmp_path`; storage tests use fixtures and temporary directories. Do not point tests at the user's normal scenario/run database.
- Use fixtures under `fixtures/valid/` and `fixtures/invalid/`; record any seed, duration, machine and platform version for system tests.
- Reference hardware and clean-install platform checks require access to the SRS-specified machine/OS. They were not available in the latest local test execution.

## 4. Numbering, execution fields and status rules

Existing IDs (`TC-NET-*`, `TC-SIG-*`, `TC-DEM-*`, `TC-SIM-*`, `TC-MET-*`, `TC-LIB-*`, and `TC-PERF/REL/UX/PORT-01`) are retained. Supplemental cases use `TC-SYS-*`, `TC-UI-*`, `TC-ERR-*`, and `TC-REG-*`. Each execution record must include date, commit/build, environment, command or manual steps, actual result, status, evidence, and defect reference.

Statuses: **Passed** or **Failed** only when the identified case was actually executed and its criterion evaluated; **Blocked** when required approval/environment/personnel is unavailable; **Not Run** otherwise. The 6 November full pytest runs reported 457 passed assertions, 0 failures and 0 skips, but both Python processes exited with `-1073740791` (`0xC0000409`) during/after shutdown. Therefore the automated assertions passed, while process-level suite completion is abnormal. Do not convert unexecuted manual procedures to Passed.

## 5. Functional, engine, UI and reporting cases

The Actual result/status column reports only directly available automation/evidence. “Automation assertions passed; process exited abnormally” refers to the full suite on 6 November, not a separate manual execution of the described procedure.

| ID / requirement | Title | Preconditions and input | Steps | Expected result | Automation / actual result and status |
|---|---|---|---|---|---|
| TC-NET-01 / TMS-F-010 | Create, edit and round-trip network | Valid network/scenario fixture; isolated path | Create or edit intersections and directed segments; save; reload; compare IDs and attributes | Intersections, direction, lane count, length and speed limit persist unchanged | `tests/test_network.py`, `tests/test_ui_network_editing.py`, `tests/test_ui_scenario_management.py`; assertions passed in suite, process exit abnormal |
| TC-NET-02 / TMS-F-011 | Control type and permitted turns | Network with signalized and unsignalized nodes and valid approaches | Configure control type and permitted turns; inspect movements and validation | Only movements permitted by the configured network are available; invalid references are reported | `tests/test_network.py`, `tests/test_ui_network_editing.py`; assertions passed in suite, process exit abnormal |
| TC-NET-03 / TMS-F-012 | Invalid network rejection | Disconnected, zero-length, zero-lane and missing-receiver fixtures | Validate each input; attempt to start a run for invalid inputs | Each defect is identified and an invalid network cannot run | `tests/test_network.py`, `tests/signal/test_reference_fixtures.py`, `tests/test_ui_signal_visualization_and_zoom.py`; assertions passed in suite, process exit abnormal |
| TC-NET-04 / TMS-F-013 | Versioned JSON import/export | Valid versioned scenario; temporary destination | Export, import into clean path, compare full scenario; try unsupported version | Data round-trips and unsupported/malformed versions are rejected without partial storage | `tests/test_network.py`, `tests/test_store.py`, `tests/test_scenario_serialization.py`; assertions passed in suite, process exit abnormal |
| TC-SIG-01 / TMS-F-020 | Configure fixed-time phases | Signalized intersection and valid movements | Add/reorder phases; set green/yellow/all-red; save/reload | Phase order, movement IDs and timings are represented as configured | `tests/test_ui_signal_editor.py`, `tests/signal/test_signal_plan.py`; assertions passed in suite, process exit abnormal |
| TC-SIG-02 / TMS-F-022 | Reject invalid or conflicting plans | Matching network plus invalid timing/conflict fixtures | Validate malformed timing, unknown movements and conflicting greens | Invalid plans are blocked and actionable defects identify the affected phase/movement | `tests/signal/test_signal_plan.py`, `tests/test_ui_signal_editor.py`; assertions passed in suite, process exit abnormal |
| TC-DEM-01 / TMS-F-030 | Configure demand and turning ratios | Valid network and seeded demand input | Set arrival rates/ratios; run with fixed seed; inspect generated demand | Demand follows configured entries and ratios using documented model semantics | `tests/test_demand.py`, `tests/test_ui_demand_editor.py`; assertions passed in suite, process exit abnormal |
| TC-DEM-02 / TMS-F-032 | Deterministic repeated run | Same valid scenario and seed 42 | Execute two runs; compare demand, lifecycle/metric event logs and all reported metrics | Both runs are identical for same inputs | `tests/test_engine.py`; `artifacts/issue12/system_checks.json` reports two identical seed-42 runs, 36,940 metric events and identical metrics. Automated repeatability evidence: **Passed**. |
| TC-SIM-01 / TMS-F-040 | Fixed-step movement and signal interaction | Valid engine scenario with vehicles, leader and signal | Advance fixed steps through free movement, leader following, red and green phases | Time advances by the configured step; vehicles obey movement, gap and signal rules | `tests/test_engine.py`; assertions passed in suite, process exit abnormal |
| TC-SIM-02 / TMS-F-041 | Start, pause, step, reset and speed controls | Valid scenario and stopped engine | Start; pause; verify frozen state; single-step; reset; try supported speed multipliers and invalid value | Controls produce documented state changes; unsupported multipliers are rejected | `tests/test_engine.py`, `tests/test_ui_playback_controls.py`, `tests/test_ui_scenario_loading.py`; assertions passed in suite, process exit abnormal |
| TC-SIM-03 / TMS-F-042 | Stop at configured duration and finalize once | Short scenario with configured duration | Run to duration; observe completion and persisted result count | Engine stops within one simulation step of duration and final result is captured once | `tests/test_engine.py`, `tests/test_ui_results_dashboard.py`, `tests/test_ui_run_history.py`; assertions passed in suite, process exit abnormal |
| TC-SIM-04 / TMS-F-043 | 2D view follows engine state | Valid network with signals/vehicles | Advance, pause and reset; inspect canvas, pan and zoom | Rendered vehicles/signals follow authoritative state; view operations do not mutate scenario/engine | `tests/test_ui_signal_visualization_and_zoom.py`, `tests/test_ui_performance_charts.py`; assertions passed in suite, process exit abnormal |
| TC-MET-01 / TMS-F-050 | Compute metrics and boundaries | Completed, incomplete and empty event histories | Independently calculate travel time, delay, queue, throughput and speed; compare engine metrics | Metrics use documented formulas; unavailable differs from zero; incomplete trips do not enter completed-trip averages | `tests/test_metrics.py`; assertions passed in suite, process exit abnormal. Queue metric uses speed below 0.5 m/s; delay uses speed-limit free-flow time for completed trips only. |
| TC-MET-02 / TMS-F-051 | Display live and final metrics | Workbench with active and completed runs | Advance simulation; compare dashboard with engine results; inspect pause/reset/empty cases | Display updates and final metrics remain consistent with calculation | `tests/test_ui_results_dashboard.py`, `tests/test_ui_performance_charts.py`; assertions passed in suite, process exit abnormal |
| TC-MET-03 / TMS-F-052 | Persist completed run | Isolated SQLite store and completed run | Save run; close/reopen store; reload record and snapshot | Scenario, seed, configuration, metadata and metrics round-trip | `tests/test_store.py`, `tests/test_ui_run_history.py`; assertions passed in suite, process exit abnormal |
| TC-MET-04 / TMS-F-053 | Compare saved runs | Two saved runs including missing/incompatible metrics | Load and compare; inspect identities, units, deltas and compatibility | Correct differences and unavailable values are shown; incompatible snapshots are flagged | `tests/test_scenario_comparison.py`, `tests/test_ui_run_history.py`; assertions passed in suite, process exit abnormal |
| TC-MET-05 / TMS-F-054 | Export run and comparison CSV | Completed saved run(s) and temporary output path | Export; parse CSV; exercise invalid path and overwrite/cancel | Headers, units, values and statuses are stable; failures are reported safely | `tests/test_reporting_export.py`, `tests/test_ui_run_history.py`; assertions passed in suite, process exit abnormal |
| TC-LIB-01 / TMS-F-060 | Scenario library lifecycle | Temporary SQLite library and valid scenario | Save, list, load, rename, duplicate and delete | Operations persist correctly; errors do not corrupt current scenario/library | `tests/test_store.py`, `tests/test_ui_scenario_library.py`; assertions passed in suite, process exit abnormal |
| TC-SYS-01 / cross-cutting | Analyst integration workflow | Two-intersection fixture and isolated temporary database | Network setup; configure scenario; save/load; simulate; inspect results; persist; compare; export/parse CSV | All workflow steps agree on scenario/run identity and stored values | `artifacts/issue12/system_checks.json` reports this fixture workflow completed with isolated DB and 20 CSV rows; automated integration evidence: **Passed**. It is not human usability evidence. |
| TC-UI-01 / TMS-F-041, F-043 | UI interaction and minimum layout | Offscreen Qt; workbench fixture | Exercise controls, menus, dialogs, editing, zoom/pan, keyboard behavior and minimum supported layout | UI state is coherent; controls accessible; text editing does not trigger application shortcuts | `tests/test_ui_*.py`; assertions passed in suite, process exit abnormal |
| TC-ERR-01 / TMS-F-012, F-013 | Malformed and invalid input handling | Malformed JSON, invalid network/signal/demand and unsupported schema | Load/import each invalid input and inspect state/error | Invalid input is rejected with a useful error and does not replace valid active state or partially persist | `tests/test_network.py`, `tests/test_scenario_serialization.py`, `tests/test_ui_scenario_loading.py`, `tests/signal/test_reference_fixtures.py`; assertions passed in suite, process exit abnormal |
| TC-ERR-02 / TMS-F-052, F-054 | Storage and export failure handling | Invalid/unwritable test-only path; isolated temporary DB | Trigger read/write/open/export failure | Error is surfaced; current scenario/run data remains intact; connections/resources close | `tests/test_store.py`, `tests/test_reporting_export.py`, `tests/test_ui_scenario_library.py`, `tests/test_acceptance_scripts.py`; assertions passed in suite, process exit abnormal |
| TC-REG-01 / TMS-F-032, F-041, F-050 | Determinism, reset and metric regression | Fixed seed and real Engine | Run twice; reset a populated engine; compare incremental/recomputed metrics and empty history | Results repeat; reset clears prior run metrics; all fields match independent expectations | `tests/test_engine.py`, `tests/test_metrics.py`; assertions passed in suite, process exit abnormal |

## 6. Non-functional acceptance cases

| ID / requirement | Preconditions and procedure | Expected result | Actual result/status and evidence |
|---|---|---|---|
| TC-PERF-01 / TMS-NF-001 | `fixtures/valid/performance_10_intersections.json`, seed 42, 1x, full 3,600 simulated seconds; full-run FPS `(frames - 1) / wall seconds between first/last paint` | Complete run and average FPS >= 15 | **Failed target / not acceptance-eligible.** Latest full run completed 3,600.1 seconds, 72,055 frames, 13.25 FPS, process exit 0; seven external mouse ingress records have uncertain identity. See `artifacts/issue12/tc_perf_01_performance_report_2026-11-03.md`. |
| TC-REL-01 / TMS-NF-002 | Use an approved number/mode of seeded full-duration repetitions; collect crashes, exceptions and state integrity | Meets approved reliability criterion | **Blocked** pending measurable criterion approval/interpretation. Existing headless seeds 42/43/44 completed one hour without crashes in `artifacts/issue12/system_checks.json`; GUI 4x evidence does not establish three clean completed runs. |
| TC-UX-01 / TMS-NF-003 | Approved protocol with new users; measure task completion, time and assistance | Meets approved usability criterion | **Blocked.** No human usability session is evidenced; automated fixture workflow is not UX evidence. Issue #1 proposal is not treated as approved. |
| TC-PORT-01 / TMS-NF-004 | Install/run on required clean Windows versions and record environment | Installation and reference scenario work on each approved platform | **Blocked.** No clean Windows install test is evidenced; current local run is existing Windows 11 only. |

## 7. Execution summary and traceability

On 6 November 2026, `python -m pytest -q --basetemp .pytest-tmp-s3-unit-53adad7fffd24c3f8cafbca7103352f1` reported 457 passed in 47.93 seconds, with process exit `-1073740791` (`0xC0000409`). The coverage-instrumented full run reported 457 passed in 35.88 seconds and the same process exit. These are test-suite assertion results, not clean process-level completion; see `docs/unit_test_report_2026-11-06.md`.

| Requirement group | Test cases | Main automated evidence |
|---|---|---|
| TMS-F-010..013 | TC-NET-01..04, TC-ERR-01 | `tests/test_network.py`, `tests/test_ui_network_editing.py`, `tests/test_store.py`, serialization and fixture tests |
| TMS-F-020, F-022 | TC-SIG-01..02 | `tests/test_ui_signal_editor.py`, `tests/signal/test_signal_plan.py` |
| TMS-F-030, F-032 | TC-DEM-01..02 | `tests/test_demand.py`, `tests/test_engine.py` |
| TMS-F-040..043 | TC-SIM-01..04, TC-UI-01 | engine, playback, visualization, dashboard and chart tests |
| TMS-F-050..054 | TC-MET-01..05, TC-ERR-02 | metrics, storage, comparison, export, results and history tests |
| TMS-F-060 | TC-LIB-01 | `tests/test_store.py`, `tests/test_ui_scenario_library.py` |
| TMS-NF-001..004 | TC-PERF/REL/UX/PORT-01 | Issue #12 benchmark/evidence; criteria and manual/platform blockers remain explicit |

This document supplements, rather than replaces, `docs/test_catalogue.md` and `docs/RTM.csv`. Requirement and NFR baseline conflicts remain subject to Issue #1 decisions. No unsupported requirement or unexecuted manual pass has been introduced.
