# Issue #12 — System Acceptance Verification

**Verification date:** 2026-10-29

**Branch:** `issue-12/system-acceptance`

**Base at verification start:** `4e512bf867efe861843e2342289d066c5650594c` (`origin/main`)

**Environment:** Windows 11 build 26300; Python 3.13.7

**Issue status:** Acceptance incomplete; keep Issue #12 open.

## Acceptance results

| Criterion | Status | Actual result and evidence |
|---|---|---|
| TC-PERF-01 — 10-intersection, 500-vehicle, one simulated hour at 1x; average >=15 FPS | **INCOMPLETE / BLOCKED** | `artifacts/issue12/tc_perf_01_full_run_retry1.json`: run stopped at 2,123.6/3,600 simulated seconds. The engine clock last advanced at 6,577.85 wall seconds. The final canvas frame was at 6,591.83 seconds; the harness ended at 6,621.94 seconds after more than 30 seconds without a new paint. Incomplete full-interval rate was 6.45 FPS; this is diagnostic only and is not a final pass/fail acceptance measurement. The last samples show the window visible and not minimized. No cause has been reproduced, so no speculative application change was made and no long retry was launched. The earlier invalid attempt is retained at `artifacts/issue12/tc_perf_01_full_run.json`. The short smoke at `artifacts/issue12/gui_smoke2.json` (5.1 simulated seconds) is not acceptance evidence. |
| TC-REL-01 — three seeded one-hour GUI runs without a crash | **INCOMPLETE / BLOCKED** | `artifacts/issue12/system_checks.json` has three completed headless runs of 3,600.1 simulated seconds at seeds 42, 43, and 44, without exceptions. The required long GUI runs were not completed; one GUI run stalled before its hour and the other two were not run. Headless results do not substitute for GUI reliability acceptance. |
| TC-UX-01 — at least 4/5 new users build and run a two-intersection network within 10 minutes | **BLOCKED — human testing not performed** | The automated workflow loaded a saved two-intersection fixture. No new-user participants were available; no human result is claimed. |
| TC-PORT-01 — install and run on clean Windows 10 and Windows 11 | **BLOCKED — clean environments unavailable** | Only the existing Windows 11 build 26300 environment was used. No clean Windows 10 or clean Windows 11 installation was available. |
| TC-DEM-02 — same scenario and seed produce identical demand and metrics | **PASS** | `artifacts/issue12/system_checks.json`: seed 42, two runs; demand, all 36,940 metric events, and computed metrics were identical. Required throughput, delay, and queue metrics were non-null. |
| Analyst workflow — load/setup, save/load, simulate, results, persist, compare, CSV | **PASS — automated fixture workflow** | `artifacts/issue12/system_checks.json`: a 2-intersection/2-segment scenario was saved, exported, imported, and reloaded; two runs were completed, persisted to a temporary SQLite database and reloaded; dashboard values and run comparison were checked; CSV export parsed 20 rows. This exercised the Workbench workflow using a fixture and does not claim manual authoring or usability testing. |
| Automated tests | **403 test cases passed; interpreter exit abnormal** | Focused command reported 17 passed with exit 0. Two full-suite invocations each reported 403 passed, then Python returned `-1073740791` (`0xC0000409`). The full-suite test assertions all passed, but the process exit was not clean. Exact attempts are in `docs/test_execution_record.md`. |

## Metric definitions

- Analytical queue length counts vehicles with measured speed **below 0.5 m/s**. The GUI queue overlay and vehicle highlighting use a separate **1.0 m/s** visual cue and are not the reported queue metric.
- Delay is the mean of `max(0, completed_trip_time - speed_limit_free_flow_time)`. Free-flow time uses route distance and each segment's speed limit. Only uniquely matched completed trips contribute; incomplete trips are excluded.
- The approved FPS measurement is `(total_frames - 1) / elapsed_wall_seconds` across the complete run. Rolling FPS, headless throughput, short smoke runs, and partial-run averages cannot establish TC-PERF-01.

## Database isolation and limits

`measure_gui_fps.py` assigns each benchmark a fresh `TemporaryDirectory` SQLite history database before simulation and removes it after exit. `scripts/issue12_system_checks.py` also uses a temporary SQLite database for the Workbench flow. Pytest uses isolated temporary storage fixtures. These checks did not use or modify existing user run-history data.

The long GUI attempt stalled at 2,123.6 simulated seconds while the window was visible and not minimized. Available evidence does not determine whether the cause was application state, user/window interaction, or the host environment. Reproduction under controlled interaction-free conditions is required before classifying a product defect. TC-PERF-01, TC-REL-01, TC-UX-01, and TC-PORT-01 remain unresolved; Issue #12 must remain open.
