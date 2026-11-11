# Issue #12 — System Acceptance Verification

**Verification update:** 2026-11-11

**Branch:** `issue-12/4x-acceptance`

**HEAD inspected:** `5a64be2013aa80844f2909d02e04fe2e8aba67bf` (source/test inspection recorded 2026-11-03; subsequent implementation and documentation changes remain subject to review)

**Latest benchmark environment:** Windows 11 build 26300; Python 3.13.7; seed 42

**Issue status:** Acceptance incomplete; keep Issue #12 open.

**NFR baseline:** The broad measurable-NFR decision was approved by all four teammates on 2026-10-27, as recorded in `docs/decisions/0001-baseline-proposal.md`. The TC-REL-01 operational procedure was subsequently approved by the project owner and collaborator in Issue #12. Three independently supervised headless simulation-engine runs using seeds 42, 43, and 44, each with a 3,600-second simulated duration and a 60-second wall-clock timeout, passed. The runner-exception and cleanup-failure negative controls were detected, and a real process-tree termination test passed. This establishes headless engine-level reliability only; GUI, Workbench, and operating-system reliability are not established. TC-UX-01 still requires human participant evidence, and TC-PORT-01 still requires an explicit Windows installation matrix and clean-install verification.

## Acceptance results

| Criterion | Status | Actual result and evidence |
|---|---|---|
| TC-PERF-01 — 10-intersection reference scenario, one simulated hour at 1x; average >=15 FPS | **PASS — acceptance-eligible** | Latest artifact `artifacts/issue12/tc_perf_01_full_run_controlled_retry2_2026-11-09.json`: finished 3,600.1 simulated seconds for a 3,600-second request at requested and actual 1.0x; 72,008 frames over 4,510.687 seconds; `(72,008 - 1) / 4,510.687 = 15.96 FPS`. `acceptance_eligible=true`; all nine acceptance checks are true; process exit 0; cleanup succeeded; zero input events, unexpected external input, storage errors, or ambiguous input records. The 2026-11-03 13.25 FPS run and other failed/ineligible attempts remain historical evidence, not the latest result. |
| TC-REL-01 — reliability | **PASS — headless engine reliability** | Approved procedure: `docs/issue12_tc_rel_01_procedure_proposal.md`. Three independent supervised child-process runs using seeds 42, 43, and 44 each simulated 3,600 seconds and passed all 20 runner checks; all exited 0 within the approved 60-second timeout. No failed checks or remaining child PIDs. Summary: `artifacts/issue12/tc_rel_01/supervisor_reliability_20261111T120702_740960Z.json`; individual runner JSON files are referenced in the summary. Runner-exception and cleanup-failure negative controls were detected, and the real process-tree test passed all six checks. This establishes headless engine-level reliability only, not GUI, Workbench, or operating-system reliability. |
| TC-UX-01 — usability | **BLOCKED — procedure and human evidence incomplete** | No new-user participants were tested. A documented human usability evaluation procedure and actual participant evidence are still required. The automated fixture workflow is not usability evidence. |
| TC-PORT-01 — Windows portability | **BLOCKED — installation matrix and evidence incomplete** | The benchmark and tests ran on the existing Windows 11 build 26300 host. There is no clean Windows installation evidence. An explicit Windows installation matrix and clean-install verification evidence are still required. |
| TC-DEM-02 — same scenario and seed produce identical demand and metrics | **PASS — automated evidence** | `artifacts/issue12/system_checks.json`: seed 42, two independent runs; demand, all 36,940 metric events, and all reported metrics matched; throughput, delay, and queue metrics were non-null. |
| Analyst workflow — network fixture setup, save/load, simulation, results, persistence, comparison, CSV | **PASS — automated fixture integration only** | `artifacts/issue12/system_checks.json`: a 2-intersection/2-segment fixture was saved, exported, imported, and reloaded; two Workbench runs were completed and persisted to a temporary SQLite database; stored runs were reloaded/compared, dashboard values checked, and CSV parsed as 20 rows. No manual network authoring or human usability is claimed. |
| Automated tests | **PASS — 457 passed, process exit 0 (historical verification)** | After adding the TC-PERF-01 one-hour/1x artifact-eligibility guard: full suite 457 passed in 28.06s, exit 0; focused acceptance/UI/engine suite 83 passed, exit 0. Compilation and diff checks passed at that verification. These are previously recorded results, not a new full-suite execution on 2026-11-11. Exact commands are recorded in `docs/test_execution_record.md`. |

## Metric definitions

- Analytical queue length counts vehicles with measured speed **below 0.5 m/s**. The GUI queue overlay and vehicle highlighting use a separate **1.0 m/s** visual cue and are not the reported queue metric.
- Delay is the mean of `max(0, completed_trip_time - speed_limit_free_flow_time)`. Free-flow time uses route distance and each segment's speed limit. Only uniquely matched completed trips contribute; incomplete trips are excluded.
- The approved FPS measurement is `(total_frames - 1) / elapsed_wall_seconds` across the complete run. Rolling FPS, headless throughput, short smoke runs, and partial-run averages cannot establish TC-PERF-01.
- Older 30-second diagnostic artifacts (`tc_perf_01_diagnostic_pause_provenance_30s.json` and `tc_perf_01_diagnostic_30s_fix_validation.json`) were produced before the finalizer checked the TC-PERF-01 one-hour/1x configuration and contain a legacy `acceptance_eligible=true`. They are preserved unchanged and are not acceptance evidence. The current finalizer now requires at least 3,600 requested simulated seconds at exactly 1x; regression tests cover short and non-1x artifacts.

## Database isolation and limits

`measure_gui_fps.py` assigns each benchmark a fresh `TemporaryDirectory` SQLite history database before simulation and removes it after exit. `scripts/issue12_system_checks.py` also uses a temporary SQLite database for the Workbench flow. Pytest uses isolated temporary storage fixtures. These checks did not use or modify existing user run-history data.

The latest 1x run, recorded on 2026-11-09, passed TC-PERF-01 at 15.96 FPS with all eligibility checks true and no external input. The 2026-11-03 13.25 FPS result and subsequent below-target or ineligible attempts remain preserved as historical evidence; they are not substituted for the latest result. The earlier 4x seed-43/44 attempts remain interrupted evidence; 4x does not satisfy TC-PERF-01. The latest artifact records Windows 11 build 26300 and an AMD64 processor; conformance to any separately specified Intel reference hardware has not been established by this run.

## TC-REL-01 reliability evidence details

The approved operational procedure is documented in `docs/issue12_tc_rel_01_procedure_proposal.md`.

| Run | Seed | Result | Runner checks | Exit code | Supervisor wall time |
|---|---:|---|---:|---:|---:|
| 1 | 42 | PASS | 20/20 | 0 | 3.186 s |
| 2 | 43 | PASS | 20/20 | 0 | 3.179 s |
| 3 | 44 | PASS | 20/20 | 0 | 2.222 s |

All three runs:
- Simulated the approved 3,600-second duration.
- Completed without timing out against the 60-second wall-clock limit.
- Had zero failed runner checks.
- Completed process cleanup successfully.
- Reaped the parent process.
- Left no remaining child process IDs.

Additional supervisor validation:

- **Runner-exception negative control:** PASS. The injected runner exception was recorded, the child exited nonzero, and cleanup succeeded. Evidence: `artifacts/issue12/tc_rel_01/supervisor_negative-exception_20261111T120254_219514Z.json`.
- **Cleanup-failure negative control:** PASS. The injected cleanup failure was detected and recorded by the supervisor. Evidence: `artifacts/issue12/tc_rel_01/supervisor_negative-cleanup_20261111T120300_129914Z.json`. This is a synthetic failure injection after the cleanup attempt; it verifies error recording, not a naturally occurring operating-system cleanup failure.
- **Real process-tree test:** PASS. The parent timed out, its child was discovered, both processes were terminated, the parent was reaped, and neither PID remained. All six checks passed. Evidence: `artifacts/issue12/tc_rel_01/supervisor_process-tree-test_20261111T120631_004465Z.json`.

**Scope limitation:** TC-REL-01 establishes headless simulation-engine reliability only. It does not establish GUI, Workbench, or operating-system reliability. This deviation is recorded in `DEVIATIONS.md`.

## Acceptance disposition

The broad measurable-NFR decision is approved as recorded in `docs/decisions/0001-baseline-proposal.md`. The SRS/SAD/STP owners still need to incorporate the approved decisions into those documents.

- TC-PERF-01: **PASS**
- TC-REL-01: **PASS — headless engine reliability only**
- TC-DEM-02: **PASS — automated evidence**
- Analyst workflow: **PASS — automated fixture integration only**
- Automated tests: **PASS — 457 previously recorded full-suite passes**
- TC-UX-01: **BLOCKED — human evaluation and participant evidence outstanding**
- TC-PORT-01: **BLOCKED — Windows installation matrix and clean-install verification outstanding**

Issue #12 remains open because TC-UX-01 and TC-PORT-01 are unresolved. No files were pushed, no pull request was created, and no issue was closed by this verification update.

## Sign-off

- Tester: Pending
- Reviewer: Pending
- Final acceptance: Pending