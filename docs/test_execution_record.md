# Issue #11 — Test Execution Record

## Latest full-suite run

- **Date:** 2026-10-26
- **Branch:** `main`
- **Commit tested:** `b7c61175b61a3683990be502846eede40dfad2cf`
- **Command:** `python -m pytest -q`
- **Collected tests:** 165
- **Passed:** 165
- **Failed:** 0
- **Result:** Full automated test suite passed.

## Collection evidence

- **Command:** `python -m pytest --collect-only -q`
- **Collected:** 165 tests in the previously recorded collection run.

## Scope and limitations

This result applies to the automated tests collected by pytest at
the commit recorded above. It does not establish that every test case in
`docs/test_catalogue.md` has been executed or that every SRS requirement
is fully implemented.

In particular:

- Metrics computation, live dashboard metrics, completed-run persistence,
  run comparison, and CSV reporting require separate implementation and
  test verification.
- The five proposed STP §13 traceability entries remain pending team review.
- Non-functional acceptance criteria remain subject to baseline approval.
- RTM mappings marked as drafts are not approved traceability decisions.
- No individual catalogue test is marked Passed solely because the full
  suite passed.

## Execution status

The full automated test suite passed at the recorded commit.
Re-run the suite after subsequent changes and update this record with
the new commit and actual result.

## Issue #10 verification (2026-10-29)

- **Branch:** `fix/issue-10-metrics-reporting`
- **Base commit:** `7b41185` (changes were verified in the working tree before commit)
- **Targeted command:** `python -m pytest -q tests/test_engine.py tests/test_metrics.py tests/test_store.py tests/test_scenario_comparison.py tests/test_reporting_export.py tests/test_ui_results_dashboard.py tests/test_ui_run_history.py`
- **Targeted result:** 103 passed (repeat run exited 0; one prior repeat had an abnormal interpreter shutdown after reporting all tests passed).
- **Full-suite command:** `python -m pytest -q`
- **Full-suite result:** 402 passed.
- **Static checks:** `python -m compileall -q src tests` passed; `git diff --check` passed.
- Criterion-by-criterion evidence and metric semantics: `docs/issue10_acceptance.md`.

## Issue #12 system verification (2026-10-29)

- **Branch:** `issue-12/system-acceptance`
- **Commit tested:** `4e512bf867efe861843e2342289d066c5650594c` plus the existing uncommitted Issue #12 changes listed by `git status` at verification time.
- **Environment:** Windows 11 build 26300; Python 3.13.7.
- **Focused command:** `& 'C:\Users\vikhy\AppData\Local\Programs\Python\Python313\python.exe' -m pytest -q tests/test_ui_performance_charts.py tests/test_acceptance_scripts.py`
- **Focused result:** 17 passed in 11.81s; exit code 0.
- **Full-suite command:** `& 'C:\Users\vikhy\AppData\Local\Programs\Python\Python313\python.exe' -m pytest -q`
- **Full-suite result:** Two consecutive invocations each reported 403 passed (57.00s and 57.31s), then Python exited with `-1073740791` (`0xC0000409`). Test assertions passed; command process status was nonzero. See `artifacts/issue12/defect_log.md`.
- **Headless reliability/determinism and analyst workflow:** `python scripts/issue12_system_checks.py` exited 0 when originally run; three seeded 3,600.1-second headless runs completed, seed-42 demand, 36,940 metric events and metrics matched between two independent runs, and the temporary-store Workbench save/load/run/results/persist/compare/CSV workflow completed. Evidence: `artifacts/issue12/system_checks.json`.
- **GUI benchmark:** `measure_gui_fps.py --output artifacts/issue12/tc_perf_01_full_run_retry1.json` ended with exit code 1. It stopped at 2,123.6/3,600 simulated seconds after no canvas frames for more than 30 seconds. The incomplete full-interval rate was 6.45 FPS; no complete-run acceptance value was obtained. Earlier diagnostic attempts are preserved in `artifacts/issue12/tc_perf_01_full_run.json` and `artifacts/issue12/gui_smoke2.json`.
- **Source/test validation:** `git diff --check` passed at the time of this record. The focused and full automated suites passed all assertions; the full-suite interpreter exit remains anomalous.
- **Individual acceptance status:** `docs/issue12_acceptance.md` and the Non-functional test cases in `docs/test_catalogue.md` record TC-PERF-01, TC-REL-01, TC-UX-01, TC-PORT-01, TC-DEM-02, and the analyst workflow separately. Human usability and clean-platform installation were not performed.


## Issue #12 continuation verification (2026-10-29)

- **Branch:** `issue-12/4x-acceptance` at base commit `7c072aa523e71617e8da159366efc0e030bdce92`; harness and regression-test edits were uncommitted at verification time.
- **Environment:** Windows 11 build 26300; Python 3.13.7.
- **Focused tests:** Existing evidence for `python -m pytest -q tests/test_ui_performance_charts.py tests/test_acceptance_scripts.py`: 20 passed, exit 0 (after adding three harness classification tests). This focused command was not repeated.
- **Full-suite attempt 1:** `python -X faulthandler -m pytest -q` could not set up `tmp_path`; pytest reported 406 setup errors because the sandbox Temp directory refused creation of pytest numbered temp directories. Tests did not execute.
- **Full-suite attempt 2:** `python -X faulthandler -m pytest -q --basetemp=<worktree>/.pytest-issue12-verification`; result **406 passed in 44.57s**, then Python emitted `Fatal Python error: Aborted` and `Windows fatal exception: access violation`; process exit `-1073741819` (`0xC0000005`). No Python frame / traceback was available. Assertion success and process exit are reported separately.
- **GUI 4x reliability artifacts:** Seed 42 completed 3,600.1 simulated seconds and was not performance-acceptance-eligible. Seeds 43 and 44 each stopped after recorded mouse input with final status `Simulation paused`; they are interrupted attempts. Preserve all three JSON files.
- **Remote/PR status:** GitHub API lookup failed due network connectivity in this environment. Local feature branch has no new commit or PR; PR #23 remains the previously merged system-acceptance PR.
