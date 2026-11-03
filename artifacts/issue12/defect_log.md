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
