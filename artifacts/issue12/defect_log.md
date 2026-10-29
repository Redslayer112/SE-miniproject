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
