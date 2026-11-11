# TC-REL-01 — Approved Operational Procedure

**Status:** Operational procedure approved and executed. TC-REL-01 passed on 2026-11-11 for headless simulation-engine reliability only.

This document defines the approved operational procedure for TC-REL-01 reliability validation. It translates the approved NFR baseline and subsequent team decisions into repeatable execution steps and explicit evidence requirements. Approval of this procedure does not constitute a test pass.

## 1. Approved baseline and scope

The approved Issue #1 decision record, [0001-baseline-proposal.md](decisions/0001-baseline-proposal.md), states that measurable NFRs were accepted and that the reference scenario, crash check, usability procedure and Windows evidence were to be documented. It separately defines the one-hour reference-hardware FPS measurement for performance.

The approved requirements do not expressly require GUI-mode reliability runs. The team-approved scope for this TC-REL-01 procedure is **simulation-engine reliability validation using headless execution**.

Three independently supervised headless runs exercise the simulation engine's deterministic `start`/`step` execution and provide evidence of engine completion, exception handling and internal state consistency.

**Scope limitation:** These runs provide no evidence of GUI, Workbench or operating-system reliability. Those areas are not verified by this procedure. No broader reliability claim should be made from the results.

Three runs constitute a bounded deterministic scenario check. They do not support a statistical reliability claim.

## 2. Approved procedure

### 2.1 Test configuration

- **Execution mode:** Headless engine execution, without a Qt event loop, GUI timer or wall-clock playback.
- **Scenario:** `fixtures/valid/performance_10_intersections.json` (the 10-intersection performance scenario).
- **Acceptance runs:** Three independent child processes, using seeds 42, 43 and 44 respectively.
- **Requested simulation duration:** 3,600 simulated seconds for each run.
- **Time step:** Read and record the fixture's configured `simulation.time_step_s`. The current fixture specifies 0.1 seconds.
- **Process isolation:** Each acceptance run must execute in its own child process so that its operating-system exit status and failure evidence are attributable to that run.
- **Evidence preservation:** Use fresh filenames for all new evidence. Never overwrite `artifacts/issue12/system_checks.json` or any historical GUI/headless evidence.
- **Environment information:** Record the code revision, scenario path and SHA-256, Python version, operating system/platform, start/end timestamps and exact child-process command.

The engine may finish on the first simulation step at or beyond the requested duration. Record the actual final engine time and configured time step.

### 2.2 Process supervision and timeout

The following operational decisions were approved in the Issue #12 discussion:

- **Wall-clock timeout:** 60 seconds per child process, measured by the supervisor using a monotonic clock from process start.
- **Timeout handling:** On timeout, record the timeout timestamp and available partial stdout, stderr and result data. Send a graceful termination request and wait up to 5 seconds. If the child remains alive, force-kill it and wait up to another 5 seconds to reap it.
- **Process cleanup:** Record the action that ended the process, final exit status if available, whether the process was reaped, and any termination or cleanup errors.
- **Child-process supervision:** The supervisor must identify and clean up all child processes spawned by the runner, not merely terminate the direct child process. Verify that no runner-owned child processes remain after cleanup.
- **Resource cleanup:** Record cleanup for each child and supervisor-created resources, including pipes/handles, temporary directories and any sampler or helper process.
- **Cleanup failures:** Attempt remaining independent cleanup actions even if one fails. Retain every cleanup error alongside any primary simulation exception.
- **No false success:** Do not report successful cleanup if any runner-owned child process remains alive or cleanup cannot be confirmed.

The 60-second timeout is an operational hang-detection limit. It is not the simulation-duration limit, a performance criterion or an FPS threshold. Historical headless runs in `artifacts/issue12/system_checks.json` took approximately 0.61–0.76 wall-clock seconds for 3,600.1 simulated seconds, providing substantial headroom under the approved timeout.

### 2.3 Per-run execution and evidence

For each seed, record a separate run result containing:

1. Seed, scenario identity and SHA-256, requested duration and engine time step.
2. Child-process exit code and whether the child exited normally, timed out or was terminated by the supervisor.
3. Exception type, message and full traceback if an exception reaches the harness. If the child exits without a result record, set `result_missing=true`.
4. Engine completion flag/status, final simulated time and wall-clock runtime.
5. Cleanup result for the child process and all resources created by the harness.
6. Final engine state and individual consistency-check values/results.
7. Recorded metrics snapshot and independently re-evaluated metrics snapshot.
8. Structured errors if either metrics snapshot or any required state information cannot be produced.

The supervisor must continue collecting the remaining repetitions after an individual run fails, provided the supervisor and test environment remain healthy.

A failed repetition remains failed. Any retry must be recorded as an additional attempt and must not replace the original result. Exceptions, incomplete runs and cleanup failures must not be suppressed, filtered or reclassified.

### 2.4 State-consistency checks

Evaluate each check after the engine reports completion. Preserve actual values and individual pass/fail results rather than storing only one aggregate boolean.

| Check | Approved assertion |
|---|---|
| Completion state | `engine.finished` is true; computed metrics status is `Completed`; `engine.running` is false after completion. |
| Duration | `duration_s - 1e-6 <= engine.time <= duration_s + engine.p.dt + 1e-6`. Record actual `engine.p.dt` and final time. |
| Recorded and recomputed metrics | Compare every field. Require exact equality for status and integer counts; absolute difference <= `1e-6` for finite floating-point values; `None` must match `None`; dictionaries must have identical keys and satisfy the same numeric comparison per value. |
| Scheduled demand accounting | `vehicles_generated == total_scheduled == len(engine.vehicles)` at completion. |
| Spawn and completion accounting | Spawn IDs are unique; exit IDs are unique; every exit ID has a corresponding spawn ID; unique spawned IDs equal `vehicles_entered`; spawned IDs with exits equal `vehicles_completed`; `vehicles_in_network == len(engine.cars)`. |
| Vehicle conservation | `vehicles_entered == vehicles_completed + vehicles_in_network`; `len(engine.exited) == vehicles_completed`. |
| Active/exited vehicle state | Active vehicle IDs and exited vehicle IDs are individually unique and mutually disjoint. |
| Metrics validity | All reported numeric metrics are finite. Counts are nonnegative and do not exceed scheduled/entered totals as applicable. Legitimate optional values remain `None` rather than being silently replaced. |

#### Duration tolerance

The approved absolute tolerance is `1e-6` simulated seconds.

The current fixture specifies a time step of 0.1 seconds. Historical repeated-step completion differed from the expected 3,600.1 seconds by approximately 2.2e-9 seconds due to floating-point accumulation. The tolerance accommodates observed numeric drift while remaining substantially smaller than one simulation step.

The duration assertion therefore allows the engine to finish on the first step at or beyond the requested duration.

#### Metrics comparison

At completion, capture the recorded metrics snapshot and recompute metrics from the completed engine/event state.

Compare all fields, including status, simulated time, duration, counts, optional floating-point metrics and per-approach queue metrics.

This comparison checks snapshot freshness and serialization consistency. Reusing the same calculation does not independently prove algorithm correctness.

#### Accounting and vehicle IDs

Use the engine's lifecycle event records and final vehicle state to check spawn/exit accounting.

Record the actual ID counts and the results of uniqueness, orphan-exit, conservation and active/exited disjointness checks. Do not substitute aggregate counts for the required individual checks.

These assertions check internal accounting and finalization consistency. They do not prove that the traffic model is scientifically correct.

### 2.5 Failure and cleanup handling

- **Unexpected exception:** Capture exception class, message, full traceback, seed, execution stage and timestamp. Mark the run failed and return a nonzero child-process exit code.
- **Incomplete or abnormal termination:** If a process exits without `finished=true`, fails a consistency assertion, times out or is terminated, mark the repetition failed/incomplete. Retain partial state and logs when available.
- **Missing result:** If the child exits without producing a complete structured result, record `result_missing=true`. Never infer success from the process exit code alone.
- **Cleanup failure:** Record every cleanup action and exception separately. A cleanup failure makes the repetition unsuccessful even if the engine completed.
- **Primary and cleanup errors:** Preserve the primary simulation exception alongside cleanup errors. Attempt all remaining independent cleanup actions.
- **Run-level result:** All three repetitions must have separate attributable child-process exits with exit code 0, completed engines, all consistency assertions passing, no unexpected exceptions and successful cleanup.

Any missing record, exception, incomplete run, invariant failure, nonzero exit, timeout or cleanup failure means the TC-REL-01 procedure is not satisfied.

### 2.6 Separate harness negative controls

Run these two short negative controls separately from the three acceptance runs. They must use separate commands and artifact paths and must not launch the 3,600-second scenario.

**Negative control 1 — Injected runner exception**

Use a test-only child operation that raises a known exception at a named execution stage.

Verify that the supervisor records:

- Expected failure stage.
- Expected exception class and message.
- Full traceback.
- Nonzero child-process exit code.
- Failed run status.
- No false completion result.

**Negative control 2 — Injected cleanup failure**

Use a test-only cleanup action that raises a known cleanup exception after the child result is available.

Verify that:

- The primary run result remains present.
- The cleanup action and exception are separately recorded.
- Cleanup status is failed.
- The overall negative-control result is failed.

These controls validate evidence capture and failure reporting only. They do not demonstrate application recovery or a successful reliability run. No automatic recovery is claimed.

### 2.7 Evidence format and preservation

Use fresh evidence paths, for example:

- `artifacts/issue12/tc_rel_01_run_seed42_2026-11-11.json`
- `artifacts/issue12/tc_rel_01_run_seed43_2026-11-11.json`
- `artifacts/issue12/tc_rel_01_run_seed44_2026-11-11.json`
- `artifacts/issue12/tc_rel_01_summary_2026-11-11.json`
- `artifacts/issue12/tc_rel_01_negative_control_exception_2026-11-11.json`
- `artifacts/issue12/tc_rel_01_negative_control_cleanup_2026-11-11.json`

If a filename already exists, select a new unique filename. Never overwrite `artifacts/issue12/system_checks.json` or historical GUI/headless evidence.

#### Per-run JSON requirements

Each per-run JSON must include:

- Schema/version and run ID.
- Seed and scenario path/hash.
- Code revision, Python version and platform.
- Requested simulated duration, actual time step and wall-clock timeout.
- Exact process command, PID, start/end timestamps and wall-clock duration.
- Exit code, termination/timeout fields and stdout/stderr paths or captured text.
- Exception type, message, traceback and failure stage.
- Engine finished/running/status/final simulated time.
- Cleanup actions, status and errors.
- Recorded and recomputed metrics.
- Event/state counts.
- Spawn/exit ID uniqueness, orphan and disjoint-state check results.
- Every consistency assertion's expected value, actual value, tolerance where applicable, and pass/fail.
- Overall run status.

If a field cannot be collected, record it as unavailable with a reason. Missing data must never be treated as passing.

#### Summary JSON requirements

The summary must:

- Identify the three planned seeds and their per-run artifact paths.
- Count completed, failed and incomplete runs.
- List every failed check and error.
- Report whether all three runs satisfy the approved procedure.
- Include the two negative-control artifact references separately.
- Record the overall TC-REL-01 outcome.

Preserve successful and failed run records and all partial outputs. The summary must not turn missing data into a pass.

## 3. Existing evidence and implementation mapping

| Procedure element | Existing evidence or implementation | Remaining work or limitation |
|---|---|---|
| Three independent full-duration headless runs | `artifacts/issue12/system_checks.json` records seeds 42/43/44, each at 3,600.1 simulated seconds. `scripts/issue12_system_checks.py` currently loops over these seeds. | Historical evidence only; it was not produced under this approved supervised procedure. The existing script writes to `system_checks.json` and must not be rerun unchanged. |
| Completion and final duration | `src/tms_sim/sim/engine.py` finalizes at configured duration. `tests/test_engine.py::test_stops_at_duration_and_finalizes_once` checks duration completion and one-time finalization. | Unit test is short and does not test full-duration process supervision. |
| Pause/state reset behavior | `tests/test_engine.py::test_pause_step_reset`; GUI play/pause/resume behavior is covered in `tests/test_ui_playback_controls.py`. | These tests cover control behavior, not one-hour state integrity. |
| Same-seed repeatability | `tests/test_engine.py::test_runs_are_deterministic`; the system-check artifact compares two seed-42 runs, demand, metric-event logs and metrics. | Supporting repeatability evidence, distinct from multi-seed reliability and crash handling. |
| Metrics/accounting and ID-level invariants | `src/tms_sim/reporting/metrics.py::compute_metrics`; engine state and metric events expose counts and IDs in-process. | The dedicated child runner records the metrics comparison and individual ID-level checks in the per-run evidence. |
| Exceptions and cleanup paths | `tests/test_acceptance_scripts.py` covers simulated worker exceptions, cleanup after exceptions and process/storage/cleanup eligibility failures. | Existing tests concern benchmark-harness behavior, not the approved headless reliability process-supervision procedure. |
| GUI interruption diagnostics | `artifacts/issue12/gui_4x_reliability_seed42.json` completed at 4× with external input; seeds 43/44 stopped after recorded input. `artifacts/issue12/defect_log.md` classifies these as diagnostic interruptions. | These do not establish three clean GUI reliability runs and do not satisfy the approved headless procedure. |

### Existing system-check script limitation

The current `scripts/issue12_system_checks.py` does not provide per-run child-process exit status or exception traceback.

Its `crash_or_exception` field is set to `false` only after `run_engine()` returns. An exception can abort the outer script instead of being recorded as a failed seed.

It also writes directly to `artifacts/issue12/system_checks.json` and does not provide:

- Approved per-run timeout supervision.
- Separate child-process execution.
- Runner-owned child-process cleanup verification.
- Separate negative controls.
- Per-ID consistency checks.
- Fresh per-run evidence files.

Therefore, this script alone is insufficient to produce the evidence required by the approved procedure.

A dedicated child runner and supervisor were implemented. They write only to new evidence paths and capture each child result without overwriting historical evidence.

## 4. Approval record and implementation status

The following operational decisions were confirmed in the Issue #12 discussion by the project owner, @Redslayer112, and collaborator @hashvyas:

1. **Scope:** Headless simulation-engine reliability only. GUI, Workbench and operating-system reliability are not established by this procedure.
2. **Independent repetitions:** Three runs using seeds 42, 43 and 44.
3. **Simulation duration:** 3,600 simulated seconds per run.
4. **Wall-clock timeout:** 60 seconds per child process.
5. **Failure handling:** Continue with all remaining independent runs after an individual failure, provided the supervisor and environment remain healthy. All three runs must pass.
6. **Negative controls:** Injected runner exception and injected cleanup failure.
7. **Process supervision:** Separate child processes with runner-owned child-process cleanup and verification.
8. **Recovery claims:** No automatic recovery is claimed by this procedure.

The technical procedure and internal consistency checks are included in the approved operational scope. The procedure does not change the approved Issue #1 NFR baseline or the one-hour FPS performance criterion.

### Implementation status

| Item | Status |
|---|---|
| Team approval of operational procedure | Approved by @Redslayer112 and @hashvyas |
| Dedicated child runner | Implemented |
| Parent process supervisor | Implemented using independent child processes |
| Per-run timeout and cleanup verification | Passed; 60-second timeout and process cleanup checks recorded |
| Engine consistency checks | Passed; 20/20 checks for each acceptance run |
| Injected runner-exception negative control | Passed; exception, traceback and nonzero exit recorded |
| Injected cleanup-failure negative control | Passed; synthetic cleanup failure correctly recorded |
| Three independent acceptance runs | Passed; seeds 42, 43 and 44 |
| Per-run JSON and summary evidence | Generated and preserved |
| Process-tree supervision test | Passed; child process cleanup and reaping verified |
| `DEVIATIONS.md` row documenting headless-only scope | Updated (row 8) |
| RTM and acceptance report updates | Updated |

### Execution results - 2026-11-11

| Seed | Result | Wall-clock time | Consistency checks |
|---|---|---:|---:|
| 42 | Passed | 3.186 seconds | 20/20 |
| 43 | Passed | 3.179 seconds | 20/20 |
| 44 | Passed | 2.222 seconds | 20/20 |

All three acceptance runs completed 3,600 simulated seconds, returned exit code 0, stayed within the 60-second timeout, and passed process cleanup verification. No runner-owned child processes remained after cleanup.

**Primary summary evidence:**
`artifacts/issue12/tc_rel_01/supervisor_reliability_20261111T120702_740960Z.json`

**Negative-control evidence:**
- `artifacts/issue12/tc_rel_01/supervisor_negative-exception_20261111T120254_219514Z.json`
- `artifacts/issue12/tc_rel_01/supervisor_negative-cleanup_20261111T120300_129914Z.json`

**Process-tree evidence:**
`artifacts/issue12/tc_rel_01/supervisor_process-tree-test_20261111T120631_004465Z.json`

The injected cleanup-failure control verifies that a synthetic cleanup error is detected and reported. It does not establish that a naturally occurring operating-system cleanup failure was observed.

### Acceptance status

**TC-REL-01: PASS - headless simulation-engine reliability only.**

The evidence establishes the approved three-run headless engine procedure, its consistency checks, exception reporting and process cleanup behavior.

**Scope limitation:** GUI, Workbench and operating-system reliability remain unverified. These results do not establish a statistical reliability claim or scientific correctness of the traffic model.

TC-UX-01 and TC-PORT-01 remain blocked pending their required evidence. Issue #12 must remain open until those acceptance requirements are addressed.

No historical evidence is overwritten or deleted.
