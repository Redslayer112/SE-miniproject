# Preliminary System Acceptance Test Report

- Generated (UTC): 2026-10-29T06:06:07.797093+00:00
- Python version: 3.13.7
- Platform: Windows-11-10.0.26300-SP0
- GUI scenario: C:\Users\vikhy\OneDrive\Documents\Desktop\sem-5\ALL-LAB\SE-LAB\SE-miniproject\fixtures\valid\performance_10_intersections.json

## 1. Headless load-test results

| Run | Simulated seconds | Elapsed seconds | CPU seconds | Peak Python memory (bytes) | Generated | Completed | In network |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3600.10 | 2.337051 | 1.984375 | 371453 | 470 | 469 | 1 |
| 2 | 3600.10 | 1.574534 | 1.546875 | 227667 | 470 | 469 | 1 |
| 3 | 3600.10 | 1.597480 | 1.578125 | 226771 | 470 | 469 | 1 |

## 2. GUI performance measurement

- Simulation finished: **YES**
- Simulated duration: 3600.1 seconds
- Wall-clock measurement duration: 1130.5 seconds
- Vehicles generated: 470
- Vehicles remaining in network: 1
- Recorded FPS samples: 1130
- Mean sampled FPS: 15.98
- Median sampled FPS: 16.00
- Minimum sampled FPS: 0.30
- Maximum sampled FPS: 16.60
- Samples at or above 15 FPS: 1116
- Samples below 15 FPS: 14
- Percentage of samples at or above 15 FPS: 98.76%
- Final full-interval FPS: 9.66
- Final average frame-render time: 3.27 ms

## 3. Preliminary checks

- Headless vehicle-count repeatability: PASS
- GUI simulation reached finished state: OBSERVED
- GUI FPS acceptance: **NOT PASSED / NEEDS REVIEW**; final full-interval FPS must be reconciled with the agreed criterion.
- GUI mean sampled FPS is descriptive only and does not replace the agreed acceptance measurement.
- Total process RAM: NOT MEASURED
- TC-DEM-02 deterministic demand, event-log, and recorded-metric comparison: PASS for the fields checked
- TC-REL-01: **INCOMPLETE / BLOCKED** — one 4x GUI simulated-hour completed (seed 42); two attempts (seeds 43 and 44) ended after mouse input with `Simulation paused`. 4x evidence is diagnostic; three clean GUI runs are not established.
- TC-UX-01 and TC-PORT-01: **BLOCKED** — no new-user participants or clean Windows 10/11 installations were available.
- Full analyst workflow: **PASS — automated fixture workflow**; see `artifacts/issue12/system_checks.json`.


## 3. TC-DEM-02 - Deterministic repeatability

- Scenario: `fixtures/valid/performance_10_intersections.json`
- Seed: 42
- Independent runs compared: 2
- Generated demand: 470 vehicles
- Event count: 939 per run
- Scheduled demand identical: True
- Complete spawn/exit event logs identical: True
- Computed metrics identical: True
- Result for comparisons executed: **PASS**
- Evidence: `artifacts/dem_determinism_detail.json`

The same scenario and seed produced identical scheduled vehicle demand,
ordered spawn/exit events, and computed metrics in both independent runs.
This supports deterministic repeatability for the fields compared by the
verification script. It does not establish that unavailable metrics such as
throughput, delay, or queue length have been validated.

## 4. Limitations and follow-up

The headless load test and GUI performance test are separate measurements. Traced Python memory is not total process RAM. The scenario used a demand rate of 500 vehicles/hour but generated 470 vehicles in the observed runs. The GUI completed the configured simulation, with one vehicle remaining in the network. The broad measurable-NFR decision was approved on 2026-10-27. Apply the approved full-one-hour FPS criterion for sign-off; this preliminary report's full-interval result is not by itself a pass.


## 4. TC-REL-01 - Preliminary reliability runs

- Scenario: `fixtures/valid/performance_10_intersections.json`
- Environment: Windows-11-10.0.26300-SP0; Python 3.13.7
- Seed: 42 for all three runs
- Runs recorded: 3
- Runs reaching at least 3,600 simulated seconds: 3/3
- Crash reported by the test command: No
- Result: **PRELIMINARY RESULT — three headless runs completed; operational TC-REL-01 procedure and formal acceptance remain incomplete**
- Evidence: `artifacts/reliability_test.json`

| Run | Simulated seconds | Generated | Completed | Remaining in network |
|---:|---:|---:|---:|---:|
| 1 | 3600.10 | 470 | 469 | 1 |
| 2 | 3600.10 | 470 | 469 | 1 |
| 3 | 3600.10 | 470 | 469 | 1 |

All three headless runs reached the configured simulated duration. Each
generated 470 vehicles, completed 469, and retained one vehicle at the
simulation cutoff. This records successful execution, not proof that all
vehicles completed their journeys. The broad measurable-NFR decision was
approved on 2026-10-27. The exact TC-REL-01 repetition count, run mode,
crash-handling checks, state-consistency checks, and error-handling procedure
still need to be documented, so formal TC-REL-01 acceptance remains pending.


## 5. Sign-off

- Tester: Pending
- Reviewer: Pending
- Final acceptance: Pending


## Issue #12 verification update (2026-10-29)

This section supersedes preliminary Issue #12 observations above where they conflict. All existing evidence files have been preserved.

| Criterion | Status | Verified result |
|---|---|---|
| TC-PERF-01 | **INCOMPLETE / BLOCKED** | The latest 1x GUI run stopped at 2,123.6/3,600 simulated seconds. It stopped producing canvas frames and the harness exited 1. The partial interval reports 6.45 FPS but is not a complete-run acceptance value. See `artifacts/issue12/tc_perf_01_full_run_retry1.json`. No further long benchmark was launched. |
| TC-REL-01 | **INCOMPLETE / BLOCKED** | Three headless one-hour simulations completed. Of the new 4x GUI attempts, seed 42 completed one hour; seeds 43 and 44 paused after recorded mouse presses. These do not establish three clean interaction-free GUI runs. See `artifacts/issue12/system_checks.json` and `artifacts/issue12/gui_4x_reliability_seed4*.json`. |
| TC-UX-01 | **BLOCKED** | No new-user participants were tested. Automated fixture workflow is not human usability evidence. |
| TC-PORT-01 | **BLOCKED** | Clean Windows 10 and Windows 11 installations were unavailable; testing occurred on the existing Windows 11 build 26300 host. |
| TC-DEM-02 | **PASS** | Two independent seed-42 runs produced identical demand, all 36,940 metric events, and all reported metrics. Required throughput, delay, and queue metrics were non-null. |
| Analyst workflow | **PASS — automated fixture path** | The Workbench loaded a two-intersection/two-segment scenario; saved/exported/imported/reloaded it; completed and persisted two runs to temporary SQLite; reloaded and compared them; updated results; and exported CSV which parsed as 20 rows. No manual network authoring is claimed. |
| Focused automated tests | **PASS** | 17 passed in 11.81s; process exit 0. |
| Full automated suite | **406 assertions passed; process exit abnormal** | On the continuation branch, pytest reported 406 passed in 44.57s; Python then emitted a fatal shutdown abort / Windows access violation and exited `-1073741819` (`0xC0000005`). Assertions passed, process exit was nonzero. |

The queue metric definition remains speed **below 0.5 m/s**. Delay remains the completed-trip mean against speed-limit-based free-flow time; incomplete trips are excluded. The benchmark and workflow used temporary run-history databases; existing user records were not touched. Seed-42 4x GUI completed one simulated hour; seeds 43 and 44 paused after recorded mouse presses and are interrupted attempts. 4x is diagnostic and does not satisfy the 1x performance requirement. Detailed evidence and risks are recorded in `docs/issue12_acceptance.md`, `docs/test_execution_record.md`, and `artifacts/issue12/defect_log.md`. Issue #12 remains open because TC-PERF-01, TC-REL-01, TC-UX-01, and TC-PORT-01 are unresolved.


## Issue #12 latest evidence addendum (2026-11-03)

This addendum supersedes the Issue #12 criterion statuses and latest-run description above. Earlier measurements and test outputs in this report are retained as historical evidence.

| Criterion | Current status | Latest verified evidence |
|---|---|---|
| TC-PERF-01 | **FAIL — below FPS target; not acceptance-eligible** | Latest artifact completed 3,600.1 simulated seconds at 1x, 72,055 frames, 13.25 FPS (target >=15), process exit 0. Seven external mouse inputs have uncertain identity; storage and application cleanup succeeded. See `artifacts/issue12/tc_perf_01_performance_report_2026-11-03.md`. |
| TC-REL-01 | **BLOCKED — operational procedure incomplete** | Three headless one-hour runs for seeds 42/43/44 completed without a recorded crash. GUI runs are not three clean one-hour repetitions. The broad NFR decision was approved on 2026-10-27; exact repetition count, run mode, crash-handling checks, state-consistency checks, and error-handling procedure remain to be documented. |
| TC-UX-01 | **BLOCKED — procedure and participant evidence missing** | No human usability evaluation was conducted. The broad NFR decision was approved on 2026-10-27; the evaluation procedure and participant evidence remain outstanding. Automated fixture workflow is not usability testing. |
| TC-PORT-01 | **BLOCKED — matrix and clean-install evidence missing** | No clean Windows installation was tested; only the existing Windows 11 host is evidenced. The broad NFR decision was approved on 2026-10-27; the explicit Windows installation matrix and clean-install verification remain outstanding. |
| TC-DEM-02 | **PASS — automated** | Same seed/scenario produced identical demand, all 36,940 metric events, and all metrics in two runs. |
| Analyst workflow | **PASS — automated fixture integration only** | Save/import/load, two completed and persisted runs, reload/compare, dashboard check and CSV parse (20 rows) passed using temporary SQLite. No human authoring or UX result is claimed. |
| Automated tests | **PASS** | After adding a TC-PERF-01 one-hour/1x eligibility guard, the local full suite reported 457 passed in 28.06s, exit 0; focused acceptance/UI/engine suite reported 83 passed, exit 0. See `docs/test_execution_record.md`. |

The 0.5 m/s analytical queue threshold and speed-limit free-flow completed-trip delay definition are unchanged. Issue #12 remains open; no push, pull request, merge, or issue close was performed.

The old 30-second diagnostic artifacts remain preserved with their original `acceptance_eligible=true` values. Inspection found that the earlier finalizer did not enforce the TC-PERF-01 one-hour/1x run configuration. The finalizer now checks that configuration, with regressions covering short and non-1x results. Those historical short-run flags must not be interpreted as acceptance evidence.


## Issue #12 latest evidence addendum (2026-11-09)

This addendum supersedes the prior TC-PERF-01 status and latest-run description above. Earlier runs and their results remain preserved as historical evidence.

| Criterion | Current status | Latest verified evidence |
|---|---|---|
| TC-PERF-01 | **PASS — acceptance-eligible** | `artifacts/issue12/tc_perf_01_full_run_controlled_retry2_2026-11-09.json`: the 10-intersection reference fixture, seed 42, requested/actual 1.0x, 3,600-second request; finished at 3,600.1 simulated seconds. 72,008 frames over 4,510.687 seconds gives 15.96 FPS. All nine acceptance checks are true; process exit 0; cleanup succeeded; zero input events, unexpected external input, ambiguous input records, or storage errors. |
| TC-REL-01 | **BLOCKED — operational procedure incomplete** | Broad NFR decision approved 2026-10-27. Exact repetition count, run mode, crash-handling checks, state-consistency checks, and error-handling procedure remain outstanding. |
| TC-UX-01 | **BLOCKED — procedure and participant evidence missing** | A human usability evaluation procedure and actual participant evidence remain outstanding. |
| TC-PORT-01 | **BLOCKED — matrix and clean-install evidence missing** | An explicit Windows installation matrix and clean-install verification evidence remain outstanding. |
| TC-DEM-02 | **PASS — automated** | Existing deterministic seed-42 evidence is unchanged. |
| Analyst workflow | **PASS — automated fixture integration only** | Existing save/load, persistence, comparison, dashboard, and CSV fixture evidence is unchanged; no manual authoring or human usability result is claimed. |

The November 9 run supersedes the November 3 13.25 FPS run as the latest TC-PERF-01 result. The November 3 result and subsequent below-target or ineligible attempts remain historical and are not overwritten. The November 9 artifact records an AMD64 Windows 11 host; any separate Intel reference-hardware conformance remains unverified. The 15 FPS threshold is unchanged. Issue #12 remains open because TC-REL-01, TC-UX-01, and TC-PORT-01 are unresolved. No new automated test-suite execution is claimed by this documentation update.

## Issue #12 reliability acceptance addendum (2026-11-11)

This addendum supersedes the previous TC-REL-01 blocked status. Historical results above remain preserved.

| Criterion | Current status | Latest verified evidence |
|---|---|---|
| TC-REL-01 | **PASS - headless engine reliability** | Three independently supervised runs using seeds 42, 43, and 44 each completed 3,600 simulated seconds, passed all 20 runner checks, exited 0, and completed cleanup without remaining child processes. All three finished within the approved 60-second wall-clock timeout. Summary: `artifacts/issue12/tc_rel_01/supervisor_reliability_20261111T120702_740960Z.json`. Runner-exception and cleanup-failure negative controls were detected. The real process-tree test passed all six checks. |
| TC-UX-01 | **BLOCKED** | No new-user participant evidence has been supplied. Human usability evaluation remains outstanding. |
| TC-PORT-01 | **BLOCKED** | Clean-install evidence and the explicit Windows installation matrix remain outstanding. |

The TC-REL-01 operational procedure was approved by the project owner and collaborator in Issue #12. The reliability test covers the headless simulation engine only; it does not establish GUI, Workbench, or operating-system reliability. This limitation is recorded in `DEVIATIONS.md`.

TC-REL-01 is accepted as PASS within that scope. Issue #12 remains open because TC-UX-01 and TC-PORT-01 remain unresolved. No push, pull request, merge, or issue close is recorded by this addendum.
