# Issue #12 — Verification Defect and Blocker Log

## GUI long-run stall — unresolved

- **Evidence:** `tc_perf_01_full_run_retry1.json` (preserved, not overwritten).
- **Expected:** 3,600 simulated seconds complete while the visible 1x GUI benchmark renders continuously.
- **Observed:** Engine time last advanced at 2,123.6 seconds (wall elapsed 6,577.85 s). Canvas frame count last advanced at wall elapsed 6,591.83 s. The measurement harness stopped at elapsed 6,621.94 s after more than 30 seconds without a new paint. The last recorded window state was visible and not minimized. Incomplete full-interval FPS was 6.45, which is not an acceptance result.
- **Classification:** Unresolved run blocker; application defect not confirmed. The evidence does not establish why the engine stopped advancing. No speculative fix or retry was made.
- **Impact:** TC-PERF-01 and the GUI portion of TC-REL-01 remain incomplete. Preserve logs and reproduce under a controlled, interaction-free foreground session before changing rendering or simulation code.

## Full-suite Python shutdown — unresolved environment issue

- **Evidence:** Two `python -m pytest -q` invocations each reported `403 passed` and then returned `-1073740791` (`0xC0000409`).
- **Impact:** All pytest assertions passed, but a clean process exit was not confirmed for these two runs. Report both the pytest result and the nonzero process status; do not treat the shell command as a clean pass.


## Later GUI 4x attempts — interaction recorded; original 1x stall unresolved

- **Evidence:** `gui_4x_reliability_seed42.json`, `gui_4x_reliability_seed43.json`, and `gui_4x_reliability_seed44.json` (preserved).
- **Observed:** Seed 42 completed 3,600.1 simulated seconds at 4x. Seeds 43 and 44 recorded mouse presses followed by engine stop and final status `Simulation paused`; harness returned nonzero.
- **Classification:** The two later interruptions are consistent with a user/window pause and are not rendering-stall or crash evidence. The original 1x stall trace predates input and engine-state logging, so its cause remains undetermined. No application defect has been reproduced. The 4x artifacts are diagnostic; they cannot satisfy TC-PERF-01 and do not constitute three clean GUI reliability runs.

## Current full-suite process exit — unresolved native shutdown failure

- **Evidence:** On the continuation branch, pytest reported `406 passed in 44.57s`; after assertions completed, Python emitted `Fatal Python error: Aborted` and `Windows fatal exception: access violation`, with no Python frame. Exit code was `-1073741819` (`0xC0000005`). Loaded native modules included psutil and PySide6 QtCore/QtGui/QtWidgets.
- **Separate setup attempt:** A preceding invocation failed to create pytest `tmp_path` directories under the sandbox Temp path and reported 406 setup errors. The worktree-local `--basetemp` retry reached and passed all assertions.
- **Impact:** Full-suite assertions pass, but clean process termination is unresolved. Do not report the full command as an unqualified process-level pass.


### Targeted shutdown reproduction attempt (2026-10-29)

- **Command:** `python -X faulthandler -m pytest -q --basetemp=<worktree-local temp> tests/test_ui_performance_charts.py tests/test_acceptance_scripts.py`.
- **Environment:** Windows 11 build 26300, CPython 3.13.7 AMD64, pytest 9.1.0, PySide6 6.12.0, psutil 7.0.0; pytest configured through `pyproject.toml` (`pythonpath=["src"]`, `testpaths=["tests"]`) and `tests/conftest.py` (`QT_QPA_PLATFORM=offscreen`, isolated scenario store).
- **Result:** 20 passed in 10.95s; process exit 0. The full-suite shutdown fault did not reproduce in this targeted run.
- **Disposition:** Keep the full-suite native shutdown issue unresolved. No reproducible project defect or actionable traceback was found; no speculative code change was made.


## Latest complete 1x performance run — target missed; input identity uncertain (2026-11-03)

- **Evidence:** `tc_perf_01_full_run_pause_provenance_v1.json`; detailed report `tc_perf_01_performance_report_2026-11-03.md`.
- **Observed:** The visible benchmark completed 3,600.1/3,600 simulated seconds at 1x, seed 42, and generated 72,055 frames. The approved full-run calculation `(72,055 - 1) / 5,437.181` is 13.25 FPS, below the 15 FPS requirement. The benchmark process exited 0; no execution error, SQLite/storage error, or cleanup error was recorded.
- **Input audit:** Seven spontaneous external mouse ingress records were captured, with 40 target-delivery traces. Qt reports a generic core pointer and `MouseEventSource.MouseEventNotSynthesized`; these fields do not establish a human operator or native input identity. The artifact correctly marks input recording ambiguous and acceptance ineligible.
- **Engine state:** Only stopped-to-running (`start`) and running-to-stopped (`completion`) transitions were recorded. There is no intermediate pause in this run. The earlier 4x seed-43/44 interruptions after mouse input remain separate evidence and are not evidence of this 1x run stopping.
- **Classification / impact:** TC-PERF-01 measured below target; this is a confirmed acceptance miss on the recorded host. A performance code regression or causal link between the seven mouse inputs and FPS has not been established. The artifact also reports an AMD64 processor string rather than the SRS Intel i5-11400H reference hardware and does not report RAM, so reference-hardware compliance is unverified.
- **Disposition:** Preserve the artifact and all earlier run files. Do not replace the 1x one-hour criterion with 4x or short-run data. Any further full-hour run requires an explicitly controlled plan and a new artifact path; no rerun was started here.


## Short-diagnostic acceptance flag — corrected (2026-11-03)

- **Evidence:** Preserved `tc_perf_01_diagnostic_pause_provenance_30s.json` and `tc_perf_01_diagnostic_30s_fix_validation.json` both say `acceptance_eligible=true` despite requesting only 30 seconds. These files were created before this correction and remain unmodified.
- **Root cause:** Finalization required that the requested run finish and meet FPS/input/storage/process criteria, but did not constrain the run configuration to TC-PERF-01's one-hour duration and 1x speed. A short completed run could therefore be labeled eligible for its own requested duration.
- **Fix:** The current finalizer adds a separate `tc_perf_01_run_configuration` check for a requested duration of at least 3,600 simulated seconds and both requested and actual playback at 1x. Existing eligibility conditions and the 15 FPS threshold remain in force. The worker records the loaded scenario's duration when no override was specified.
- **Regression evidence:** `tests/test_acceptance_scripts.py` now verifies short-duration and non-1x artifacts stay ineligible and a clean one-hour 1x candidate can qualify. Focused tests: 83 passed, exit 0. Full suite: 457 passed, exit 0. `py_compile` and `git diff --check` passed. No long benchmark was run.
- **Disposition:** Fixed in the uncommitted branch worktree. Historical diagnostic artifacts retain their misleading legacy flag; classify them as diagnostic only. No push, PR, merge, or issue close was performed.


## Approved NFR baseline and incomplete operational procedures

- **Baseline status:** `docs/decisions/0001-baseline-proposal.md` records that all four teammates approved the broad measurable-NFR decision on 2026-10-27. Approval does not mean every operational acceptance procedure is fully specified.
- **TC-REL-01:** Document the exact repetition count, run mode, crash-handling checks, state-consistency checks, and error-handling procedure.
- **TC-UX-01:** Document the human usability evaluation procedure and collect actual participant evidence.
- **TC-PORT-01:** Define the explicit Windows installation matrix and collect clean-install verification evidence.
- **Status:** These criteria remain blocked until their operational procedures and required evidence are complete. No approval threshold or test outcome is inferred by this log entry.


## TC-PERF-01 controlled full-hour run — PASS (2026-11-09)

- **Evidence:** `tc_perf_01_full_run_controlled_retry2_2026-11-09.json`.
- **Configuration:** `performance_10_intersections.json`, seed 42, requested duration 3,600 seconds, requested and actual playback speed 1.0x.
- **Observed:** Simulation finished at 3,600.1 seconds; 72,008 frames over 4,510.687 seconds; full-run FPS was 15.96, meeting the unchanged 15 FPS requirement.
- **Eligibility:** `acceptance_eligible=true`; all nine acceptance checks were true. There were no input events, unexpected external input, ambiguous input records, or storage errors. Process exit code was 0 and cleanup succeeded.
- **Classification / impact:** This is the latest successful TC-PERF-01 acceptance result for the recorded run environment. Earlier below-target or ineligible benchmark entries above are retained as historical evidence and have not been deleted or rewritten. The artifact records an AMD64 Windows 11 host; any separate Intel reference-hardware conformance remains unverified.
- **Issue status:** TC-REL-01, TC-UX-01, and TC-PORT-01 remain blocked pending their operational procedures and evidence. Existing TC-DEM-02 and analyst workflow evidence is unchanged. Issue #12 remains open.
