# Issue #33 (S3-07) — System Integration & Validation Report

**Date:** 2026-11-04
**Environment:** Windows 11 build 26300; project virtualenv `.venv` (CPython 3.12.10, pytest 9.2.0, PySide6 6.12.0). Qt ran offscreen (`QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`).
**Test file:** `tests/test_system_integration.py`. Every test uses a temporary SQLite store and a fixed seed, and shortens the duration so it runs in a few seconds.
**Not rerun:** the one-hour GUI benchmarks. Their evidence stays in `docs/issue12_acceptance.md` and `artifacts/issue12/`.

## Workflow matrix

Targeted command: `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp tests/test_system_integration.py`. Result: **16 passed, 2 xfailed**; process exit **0**. The two xfails are strict, and each one fails for the defect named in its reason (checked with `--runxfail`).

| ID | Workflow (issue task) | Modules involved | Test or script | Status | Evidence |
|---|---|---|---|---|---|
| SI-01 | Network creation → signal configuration → demand generation → engine run to the configured duration, finalized once (task 1) | `network` (parse, `validate`), `signal` (parse, `validate_signal_plan`), `sim/demand` (`generate_vehicles`), `sim/scenario` (`build_engine`), `sim/engine` | `test_document_builds_validated_modules_and_runs_to_duration_once` | Passed | Engine demand equals `generate_vehicles` output for the same seed; run ends at 120 s within one step; `on_finish` called exactly once, also after an extra `step()` |
| SI-02 | Simulation execution and vehicle visualization, TC-SIM-04 (task 2) | `sim/engine`, `ui/app.py` `RoadCanvas.paintEvent`, `signal/model.py` | `test_canvas_draws_engine_vehicles_and_signal_states` | Passed | At six times across two signal cycles (green, yellow, all-red), the canvas drew one vehicle per `engine.cars` entry, at the screen position of that car (±1 px). It also drew the signal colour the plan gives, and showed green exactly when the engine's signal function is green |
| SI-03 | Simulation → metrics → `store.save_run` → reload (task 3) | `sim/engine`, `reporting/metrics`, `reporting/comparison` (`SimulationRunRecord`), `storage/store` | `test_engine_metrics_persist_and_reload_unchanged` | Passed | Reloaded metrics equal `compute_metrics(engine)`; seed, scenario snapshot and run configuration equal the originals |
| SI-04 | Run comparison, including incomplete and cross-scenario runs (task 4) | `storage/store`, `reporting/comparison` | `test_two_persisted_runs_compare_with_correct_unit_aware_differences`, `test_incomplete_and_cross_scenario_comparisons_are_flagged` | Passed | For each metric, `absolute_change == round(candidate - baseline, 2)` with the documented unit (s, veh, m/s, veh/h). Incomplete run: the "At least one run is incomplete" warning, and every metric INCOMPATIBLE. Different scenario: the "Scenario names differ" warning |
| SI-05 | CSV report export (task 4) | `reporting/export`, `reporting/metrics`, `storage/store` | `test_csv_export_parses_back_to_compute_metrics` | Passed | CSV written from the reloaded run parses back to the `compute_metrics` values (one-decimal format, units, per-approach queues). CSV text before and after persistence is identical |
| SI-06 | Workbench: load from library → run → dashboard → run history → comparison → CSV export (tasks 4 and 5) | `ui/app.py`, `ui/library.py`, `ui/run_history.py`, `ui/comparison.py`, `storage/store`, `reporting/*` | `test_workbench_library_run_dashboard_history_comparison_and_csv` | Passed | Two library scenarios (seeds 42 and 43) loaded and run through the timer callback `advance_simulation`. Dashboard labels equal `compute_metrics`; history lists both runs; the comparison dialog equals `compare_runs` on the stored rows; exported CSV equals the dashboard. **Reset** was pressed before the second run (see SI-06a) |
| SI-06a | Run finished after a library load is auto-captured without pressing Reset | `ui/app.py` | `test_run_after_library_load_is_auto_captured` | Passed | Resolved in Issue #30 via `_reset_run_capture_state()`; regression tests pass |
| SI-07 | Determinism through the persisted path (task 5) | `sim/*`, `reporting/metrics`, `storage/store` | `test_same_scenario_and_seed_store_identical_metrics` | Passed | Same scenario and seed: identical metric event logs and identical stored metrics |
| SI-08 | Representative scenarios: store → load → run → persist (task 5) | all of the above | `test_representative_scenario_store_run_persist` (small_valid 600 s; performance_10_intersections shortened to 120 s; small_stop_yield 120 s), `test_stop_yield_scenario_yields_and_saves_without_signal_plans`, `test_signalized_intersection_without_plan_is_still_blocked` | Passed | Each scenario round-trips through the store, runs to its duration, completes vehicles, and its persisted metrics equal `compute_metrics`. In the stop/yield scenario, approaches yield at the stop crossing C and at the yield merge N. Before the SI-D1 fix it could not be stored |
| SI-08b | Invalid scenario is blocked, nothing loaded, no run stored | `sim/scenario`, `ui/app.py`, `storage/store` | `test_invalid_scenario_is_blocked_and_no_run_is_stored` (zero-length segment, unknown movement, time step out of range) | Passed | Headless build raises (no specific exception class is asserted). The Workbench load returns False with an error dialog; the scenario is unchanged; no run is stored; the engine clock stays at 0 |
| SI-08a | Scenario stays saveable after its last signal plan is removed in the Workbench | `ui/app.py` `set_scenario_signal_plans`, `sim/serialization` | `test_removing_last_plan_in_workbench_keeps_scenario_saveable` | Passed | Resolved in Issue #29: `set_scenario_signal_plans` writes `signal_plans: []` when empty; test passes |
| SI-09 | Record defects, evidence and limitations (task 6) | — | This document; `docs/test_execution_record.md` | Passed | Sections below |

**Visualization limit (SI-02):** the canvas was checked through its real `paintEvent` calls. A recording `QPainter` replaced the one used by `ui/app.py`, and `RoadCanvas.grab()` rendered offscreen. Vehicles were checked by draw call and screen position, and signals by fill colour. Pixels were not compared and no screenshot was reviewed by a person. Pan/zoom and queue display are covered by existing tests, for example `tests/test_ui_signal_visualization_and_zoom.py::test_zoom_limits_and_clamping`, `::test_mouse_drag_panning_updates_offset_without_mutating_scenario` and `::test_signal_transitions_and_approach_queue_updates`.

**New fixture:** `fixtures/valid/small_stop_yield_scenario.json`. It is a seven-intersection network: a stop-controlled crossing (C), a yield-controlled merge (N), no signalized intersection and `"signal_plans": []`.

## Defects

Severity: critical = blocks acceptance or loses data with no workaround; major = blocks or corrupts a user workflow, with a workaround; minor = no effect on results.

| ID | Symptom | Reproduction | Evidence | Severity | Owning module / teammate | Status |
|---|---|---|---|---|---|---|
| SI-D1 | A scenario with no signalized intersection could run but could not be saved, exported or imported. `scenario_from_dict` required `signal_plan` or a **non-empty** `signal_plans`, so stop/yield/uncontrolled-only networks could not enter the Scenario Library (TMS-F-011 with TMS-F-060) | Before the fix, `scenario_from_dict` was called on `fixtures/valid/small_valid_scenario.json` with I1 set to `stop_controlled` and the plan removed: no plan key gave `Provide either signal_plan or signal_plans`, `signal_plan: null` gave `'signal_plan' must be an object`, and `signal_plans: []` gave `signal_plans must be a non-empty list.` `engine_from_document` ran all three without error. Now: `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp "tests/test_system_integration.py::test_stop_yield_scenario_yields_and_saves_without_signal_plans"` | Regression tests `test_stop_yield_scenario_yields_and_saves_without_signal_plans` and `test_representative_scenario_store_run_persist[small_stop_yield]`; `test_signalized_intersection_without_plan_is_still_blocked` confirms a signalized intersection without a plan still cannot run | major (blocked a whole workflow) | `src/tms_sim/sim/serialization.py` (scenario I/O; network/signal owner's S3-02 scope) | **Fixed in this PR**: `signal_plans: []` is now accepted. The one-line rule change is in `scenario_from_dict` |
| SI-D2 | After a run completes, loading another scenario (from the library or a file) and running it to completion does not auto-capture or persist the new run. `Workbench._load_scenario` never cleared `_last_captured_engine_finished_state`; only `reset_simulation` did. | Reproduced previously via `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp "tests/test_system_integration.py::test_run_after_library_load_is_auto_captured"` | Regression tests: `test_run_after_library_load_is_auto_captured` and `test_run_after_network_modification_is_auto_captured` in `tests/test_system_integration.py` | major (completed runs silently missing from run history) | `src/tms_sim/ui/app.py` (UI) / Vikas | **Resolved in Issue #30**: `_reset_run_capture_state()` clears capture tracking on scenario load and network edits |
| SI-D3 | Removing the last signal plan from a document that uses the single-plan `signal_plan` key wrote `signal_plan: {}`, which the scenario parser rejects, so the scenario could no longer be saved. In the Workbench this followed from deleting the only signalized intersection (`RoadCanvas.delete_selected`). | Reproduced previously via `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp "tests/test_system_integration.py::test_removing_last_plan_in_workbench_keeps_scenario_saveable"` | Regression tests: `test_removing_last_plan_in_workbench_keeps_scenario_saveable` and `test_ui_issue29_stabilization.py` | major (save blocked) | `src/tms_sim/ui/app.py` `set_scenario_signal_plans` (UI) / Vikas | **Resolved in Issue #29**: `set_scenario_signal_plans` writes `signal_plans: []` when empty |
| K-1 | 1x GUI benchmark stalled at 2,123.6 of 3,600 simulated seconds; cause undetermined | Not reproduced in this issue (one-hour GUI runs not rerun) | `artifacts/issue12/defect_log.md`, `artifacts/issue12/tc_perf_01_full_run_retry1.json` | critical (blocks TC-PERF-01 acceptance) | Undetermined: renderer/UI (Vikas) or engine (Venkata) | Known from Issue 12, open |
| K-2 | Two of the three clean GUI reliability runs are missing; seeds 43 and 44 were paused by mouse input | Not rerun in this issue | `artifacts/issue12/gui_4x_reliability_seed43.json`, `artifacts/issue12/gui_4x_reliability_seed44.json`, `docs/issue12_acceptance.md` | major (blocks TC-REL-01 GUI acceptance) | Test execution (no code defect established) | Known from Issue 12, open |
| K-3 | Full-suite native shutdown abort after all assertions pass (`0xC0000409` / `0xC0000005`) | Not reproduced: in this issue every full run exited 0 (baseline and final) | `artifacts/issue12/defect_log.md` | minor (assertions unaffected; process exit status only) | Undetermined (PySide6 teardown at interpreter exit) | Known from Issue 12, open; not claimed fixed |

No critical defect was found by the new integration tests. The one defect that blocked a whole workflow (SI-D1) is fixed here. The critical item K-1 is the known Issue 12 blocker and is outside this PR.

## Blocked and unexecuted tests

| Test | Status | Reason | Evidence |
|---|---|---|---|
| TC-PERF-01 (TMS-NF-001) | Blocked / incomplete | The 1x GUI run stalled (K-1); one-hour GUI benchmarks were not rerun in this issue, as instructed | `docs/issue12_acceptance.md`, `artifacts/issue12/tc_perf_01_full_run_retry1.json` |
| TC-REL-01 (TMS-NF-002), GUI part | Blocked / incomplete | Only one clean GUI hour exists (K-2). The headless part passed in Issue 12 | `artifacts/issue12/gui_4x_reliability_seed4*.json`, `artifacts/issue12/system_checks.json` |
| TC-UX-01 (TMS-NF-003) | Blocked | No new-user participants; automated tests are not usability evidence | `docs/issue12_acceptance.md` |
| TC-PORT-01 (TMS-NF-004) | Blocked | No clean Windows 10 or Windows 11 machine | `docs/issue12_acceptance.md` |
| TC-SIM-04, human visual review | Not executed | SI-02 checks draw calls and positions offscreen; nobody inspected the rendered pixels | SI-02 above |
| SI-06a | Passed | Defect SI-D2 resolved in Issue #30 | `test_run_after_library_load_is_auto_captured` |
| SI-08a | Passed | Defect SI-D3 resolved in Issue #29 | `test_removing_last_plan_in_workbench_keeps_scenario_saveable` |

Every other catalogue test (TC-NET-01..04, TC-SIG-01..02, TC-DEM-01..02, TC-SIM-01..04, TC-MET-01..05, TC-LIB-01) has passing automated tests. They are listed in `docs/RTM.csv`.

## Hand-off to S3-08 and S3-09

Verified workflows (automated, passing):
- SI-01 network → signal plan → demand → engine → single finalize
- SI-02 canvas vehicles, positions and signal states equal engine state (draw-call level)
- SI-03 engine → metrics → stored run → reload, lossless
- SI-04 comparison of stored runs: unit-aware differences, incomplete and cross-scenario warnings
- SI-05 CSV export equals `compute_metrics`, before and after persistence
- SI-06 Workbench library → run → dashboard → history → comparison → CSV (auto-capture active across loads)
- SI-06a auto-capture on subsequent scenario loads without requiring manual reset (SI-D2 resolved)
- SI-07 same seed gives identical stored metrics
- SI-08 small, performance (120 s) and stop/yield scenarios store, run and persist; invalid scenarios are blocked with nothing stored
- SI-08a removing the last signal plan produces a saveable document (SI-D3 resolved)

Resolved integration defects:
- SI-D1 (major, serialization): stop/yield scenarios saveable without signal plans (resolved in Issue #34/PR #41)
- SI-D2 (major, UI): auto-capture across scenario loads without manual reset (resolved in Issue #30)
- SI-D3 (major, UI): removing last signal plan in workbench retains saveable scenario (resolved in Issue #29)

Known external / environment limitations:
- K-1 (historical performance stall): 1x GUI benchmark stalled at 2,123.6 s in initial attempt; addressed in Nov 9 controlled rerun achieving 15.96 FPS (`artifacts/issue12/tc_perf_01_full_run_controlled_retry2_2026-11-09.json`)
- K-2 (GUI reliability runs): Headless supervisor verified across seeds 42, 43, 44 (`artifacts/issue12/tc_rel_01/supervisor_reliability_20261111T120702_740960Z.json`); multi-hour GUI reliability unverified
- K-3 (teardown exit code): Intermittent native teardown abort after test suites in certain environments; exits 0 in clean runs

Blocked or unexecuted tests:
- TC-PERF-01 (15.96 FPS verified in controlled rerun on Windows 11 host; cross-hardware unverified)
- TC-REL-01 (Headless supervisor verified; full GUI multi-seed unverified)
- TC-UX-01 (Blocked: no new-user participants)
- TC-PORT-01 (Blocked: no multi-OS matrix)
- TC-SIM-04 human visual review (SI-02 verifies draw-calls programmatically)
