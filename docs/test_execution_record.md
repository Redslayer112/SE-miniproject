
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
- At this 2026-10-26 execution, the NFR baseline was still awaiting approval. The broad measurable-NFR decision was subsequently approved on 2026-10-27; the operational procedures for TC-REL-01, TC-UX-01, and TC-PORT-01 remain incomplete.
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

## Issue #12 current evidence update (2026-11-03)

- **Branch / HEAD:** `issue-12/4x-acceptance`, commit `5a64be2013aa80844f2909d02e04fe2e8aba67bf`; branch ref and local `origin/issue-12/4x-acceptance` matched at inspection. Instrumentation and regression-test changes in `measure_gui_fps.py`, `src/tms_sim/sim/engine.py`, `src/tms_sim/ui/app.py`, `tests/test_acceptance_scripts.py`, and `tests/test_ui_playback_controls.py` are uncommitted. Existing `artifacts/issue12/` JSON/profile files are untracked user evidence and were preserved.
- **Environment:** Windows 11 build 26300; CPython 3.13.7; pytest configuration from `pyproject.toml`; tests run with a unique worktree-local pytest base directory because the default sandbox Temp location failed to create pytest temporary directories.
- **Focused command:** PowerShell command `python -m pytest --basetemp $testTemp tests/test_acceptance_scripts.py tests/test_ui_playback_controls.py tests/test_engine.py -q`, where `$testTemp` was a newly created unique path under the worktree and removed after the run. **78 passed in 12.01s; process exit 0.**
- **Full-suite command:** PowerShell command `python -m pytest --basetemp $testTemp -q`, with a newly created unique worktree-local `$testTemp`, removed after the run. **452 passed in 53.47s; process exit 0.** A preceding full-suite invocation in this validation sequence also reported 452 passed but returned `-1073740791` (`0xC0000409`) after pytest completion; the final full-suite invocation exited normally. Assertions and process status are recorded separately.
- **Compilation:** `python -m py_compile measure_gui_fps.py src/tms_sim/ui/app.py src/tms_sim/sim/engine.py tests/test_acceptance_scripts.py tests/test_ui_playback_controls.py` — exit 0.
- **Diff validation:** `git diff --check` — exit 0.
- **Latest TC-PERF-01 result:** See `artifacts/issue12/tc_perf_01_full_run_pause_provenance_v1.json` and `artifacts/issue12/tc_perf_01_performance_report_2026-11-03.md`. Completed 3,600.1 simulated seconds at 1x and seed 42; 72,055 frames; full-run FPS 13.25 vs target >=15; process exit 0; no storage or cleanup errors; seven external mouse ingress records with uncertain native identity; acceptance ineligible. The engine log records start and normal completion only.
- **TC-DEM-02 / analyst workflow:** Existing `artifacts/issue12/system_checks.json` records identical seed-42 demand, 36,940 metric events and all metrics across two runs, plus the temporary-SQLite fixture workflow through persistence, comparison and CSV parse (20 rows). This is automated fixture integration, not manual user testing.
- **TC-REL-01 / TC-UX-01 / TC-PORT-01:** The broad measurable-NFR decision was approved on 2026-10-27. These cases remain blocked because operational procedures and evidence are incomplete: REL needs its exact repetition count, run mode, crash-handling checks, state-consistency checks, and error-handling procedure; UX needs a documented human evaluation procedure and participant evidence; PORT needs an explicit Windows installation matrix and clean-install verification. Existing test evidence and limits are detailed in `docs/issue12_acceptance.md`.
- **Remote actions:** No push, PR creation, merge, or issue close was performed. Branch changes remain local pending review.

### TC-PERF-01 eligibility guard follow-up (2026-11-03)

- **Finding:** The preserved 30-second diagnostics `tc_perf_01_diagnostic_pause_provenance_30s.json` and `tc_perf_01_diagnostic_30s_fix_validation.json` each recorded `acceptance_eligible=true`. The artifact finalizer had checked completion of the requested duration and FPS but did not ensure that the requested run was at least 3,600 seconds at 1x. This was a genuine acceptance-labeling defect; the JSON files were not edited.
- **Fix:** The finalizer now requires the TC-PERF-01 run configuration (requested duration >=3,600 seconds, requested speed 1x, actual speed 1x) in addition to all existing acceptance conditions. When no duration override is provided, the worker records the actual scenario duration. The 15 FPS threshold and all existing checks remain unchanged.
- **Regression coverage:** Added final-artifact tests for a completed 30-second run, completed 0.5x/2x/4x runs, and a complete clean 1x one-hour candidate. No GUI benchmark was run.
- **Focused command:** `python -m pytest --basetemp $testTemp tests/test_acceptance_scripts.py tests/test_ui_playback_controls.py tests/test_engine.py -q`, with `$testTemp` a new worktree-local temporary path. **83 passed in 9.21s; exit 0.**
- **Full-suite command:** `python -m pytest --basetemp $testTemp -q`, with a new worktree-local temporary path. **457 passed in 28.06s; exit 0.**
- **Static checks:** `python -m py_compile measure_gui_fps.py src/tms_sim/ui/app.py src/tms_sim/sim/engine.py tests/test_acceptance_scripts.py tests/test_ui_playback_controls.py` — exit 0; `git diff --check` — exit 0.
- **Disposition:** Existing diagnostic and full-run artifacts remain untouched. The old 30-second files retain their historically written `acceptance_eligible=true` field; treat them strictly as diagnostic and use the current code/tests and documentation for future finalization. No full-hour run, push, PR, merge, or issue close was performed.

## Issue #12 continuation verification (2026-10-29)

- **Branch:** `issue-12/4x-acceptance` at base commit `7c072aa523e71617e8da159366efc0e030bdce92`; harness and regression-test edits were uncommitted at verification time.
- **Environment:** Windows 11 build 26300; Python 3.13.7.
- **Focused tests:** Existing evidence for `python -m pytest -q tests/test_ui_performance_charts.py tests/test_acceptance_scripts.py`: 20 passed, exit 0 (after adding three harness classification tests). This focused command was not repeated.
- **Full-suite attempt 1:** `python -X faulthandler -m pytest -q` could not set up `tmp_path`; pytest reported 406 setup errors because the sandbox Temp directory refused creation of pytest numbered temp directories. Tests did not execute.
- **Full-suite attempt 2 exact command:** `& 'C:\Users\vikhy\AppData\Local\Programs\Python\Python313\python.exe' -X faulthandler -m pytest -q --basetemp="C:\Users\vikhy\OneDrive\Documents\Desktop\sem-5\ALL-LAB\SE-LAB\SE-miniproject-main\issue12-4x-work\.pytest-issue12-verification"`. Pytest reported **406 passed in 44.57s**, then Python emitted `Fatal Python error: Aborted` and `Windows fatal exception: access violation`; process exit `-1073741819` (`0xC0000005`). No Python frame / traceback was available. Assertion success and process exit are reported separately.
- **GUI 4x reliability artifacts:** Seed 42 completed 3,600.1 simulated seconds and was not performance-acceptance-eligible. Seeds 43 and 44 each stopped after recorded mouse input with final status `Simulation paused`; they are interrupted attempts. Preserve all three JSON files.
- **Remote/PR status:** At this point commit `9073891e53a8ceec77cde6823e6c6d7bf284a71a` existed locally but had not been pushed; no PR had been created from this continuation branch. PR #23 is the previously merged system-acceptance PR.

### Shutdown diagnostic follow-up (2026-10-29)

- **Pytest config:** `pyproject.toml` sets `pythonpath = ["src"]` and `testpaths = ["tests"]`; no `addopts` is configured. `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` and autouse-isolates the default scenario store under pytest `tmp_path`.
- **Environment:** Windows-11-10.0.26300-SP0; CPython 3.13.7 (MSC v.1944, AMD64); pytest 9.1.0; PySide6 6.12.0; psutil 7.0.0.
- **Targeted command:** `& 'C:\Users\vikhy\AppData\Local\Programs\Python\Python313\python.exe' -X faulthandler -m pytest -q --basetemp="C:\Users\vikhy\OneDrive\Documents\Desktop\sem-5\ALL-LAB\SE-LAB\SE-miniproject-main\issue12-4x-work\.pytest-targeted-shutdown-4aa2e0f5709f43d28348ce759a83b1c6" tests/test_ui_performance_charts.py tests/test_acceptance_scripts.py`. **20 passed in 10.95s; process exit 0.** The worktree-local temporary directory was removed after the run.
- **Conclusion:** The native shutdown access violation was not reproduced by this short Qt/performance-focused run. The full-suite exit remains unresolved; no project-caused defect is established, so no product-code fix was made.
- **Connectivity:** `git ls-remote origin refs/heads/main refs/heads/issue-12/4x-acceptance` exited 128 (`getaddrinfo() thread failed to start`); `gh pr list --repo Redslayer112/SE-miniproject --head issue-12/4x-acceptance --state all --json number,state,url,title,baseRefName,headRefName,mergedAt` exited 1 (cannot connect to api.github.com). No push or PR creation was possible.

## TC-PERF-01 controlled full-hour execution (2026-11-09)

- **Evidence:** `artifacts/issue12/tc_perf_01_full_run_controlled_retry2_2026-11-09.json`.
- **Environment:** Windows 11 build 26300; Python 3.13.7; recorded processor AMD64 Family 23 Model 160 Stepping 0, AuthenticAMD.
- **Scenario / seed:** `fixtures/valid/performance_10_intersections.json`; seed 42.
- **Run configuration:** requested duration 3,600 seconds; completed 3,600.1 simulated seconds; requested and actual playback speed 1.0x.
- **Measured result:** 72,008 frames over 4,510.687 seconds; full-run calculation `(72,008 - 1) / 4,510.687 = 15.96 FPS`, meeting the unchanged 15 FPS requirement.
- **Eligibility / process:** `acceptance_eligible=true`; all nine `acceptance_checks` are true; process exit code 0; cleanup succeeded; `unexpected_external_input=false`; input recording unambiguous; zero input events and storage errors.
- **Status:** TC-PERF-01 **PASS** for this controlled one-hour run. The earlier 13.25 FPS result and later failed/ineligible attempts remain preserved as historical evidence. This entry records benchmark execution; it does not record a new pytest run.
- **Other Issue #12 status:** TC-REL-01, TC-UX-01, and TC-PORT-01 remain blocked pending their required procedures and evidence. TC-DEM-02 and the analyst workflow retain their previously recorded automated pass evidence. Issue #12 remains open.
- **Historical note:** This status reflects the position before the approved TC-REL-01 execution recorded below; the later execution record supersedes it.

## TC-REL-01 approved reliability execution (2026-11-11)

- **Approved procedure:** `docs/issue12_tc_rel_01_procedure_proposal.md`. The project owner and collaborator approved three independent headless simulation-engine runs using seeds 42, 43, and 44; a 3,600-second simulated duration per run; a 60-second wall-clock timeout; continuation after individual failures; and runner-exception and cleanup-failure negative controls.
- **Supervisor implementation:** `scripts/issue12_tc_rel_01_supervisor.py`. Each run was launched as an independent child process. The supervisor recorded exit status, timeout status, runner result, cleanup result, and process IDs.
- **Runner implementation:** `scripts/issue12_tc_rel_01_runner.py`. Each official run passed all 20 validation checks, including engine completion, state consistency, vehicle accounting, finite metrics, and recorded-versus-recomputed metrics comparison.
- **Seed 42:** PASS; exit code 0; no timeout; supervisor wall-clock time 3.186 seconds; 20/20 checks passed; cleanup PASS; parent reaped; no remaining PIDs.
- **Seed 43:** PASS; exit code 0; no timeout; supervisor wall-clock time 3.179 seconds; 20/20 checks passed; cleanup PASS; parent reaped; no remaining PIDs.
- **Seed 44:** PASS; exit code 0; no timeout; supervisor wall-clock time 2.222 seconds; 20/20 checks passed; cleanup PASS; parent reaped; no remaining PIDs.
- **Combined result:** TC-REL-01 PASS. All three independent runs passed. Overall supervisor exit code 0.
- **Reliability evidence:** `artifacts/issue12/tc_rel_01/supervisor_reliability_20261111T120702_740960Z.json`, with individual runner JSON and stdout/stderr files referenced by the summary.
- **Negative control - runner exception:** PASS. The injected runner exception was recorded, the child exited nonzero, and cleanup succeeded. Evidence: `artifacts/issue12/tc_rel_01/supervisor_negative-exception_20261111T120254_219514Z.json`.
- **Negative control - cleanup failure:** PASS. The injected cleanup failure was detected and recorded by the supervisor. Evidence: `artifacts/issue12/tc_rel_01/supervisor_negative-cleanup_20261111T120300_129914Z.json`. This is a synthetic failure injection after the cleanup attempt; it verifies error recording, not a naturally occurring OS cleanup failure.
- **Real process-tree test:** PASS. The parent timed out, its child was discovered, both processes were terminated, the parent was reaped, and neither PID remained. All six checks passed; process exit code 0. Evidence: `artifacts/issue12/tc_rel_01/supervisor_process-tree-test_20261111T120631_004465Z.json`.
- **Scope limitation:** This evidence establishes headless simulation-engine reliability only. It does not establish GUI, Workbench, or operating-system reliability. The limitation is recorded in `DEVIATIONS.md`.
- **Other acceptance criteria:** TC-UX-01 remains blocked pending human participant evidence. TC-PORT-01 remains blocked pending an explicit Windows installation matrix and clean-install verification. Issue #12 remains open.

## Issue #28 (S3-02) verification (2026-11-04)

- **Scope:** network, signal and scenario validation; scenario save/load and malformed input; demand issue shape; scenario-level validation before a run.
- **Environment:** Windows 11 build 26300; project virtualenv `.venv` with CPython 3.12.10, pytest 9.2.0, PySide6 6.12.0.
- **Note on interpreter:** the plain `python` on PATH (CPython 3.12.10 without PySide6) gave 17 collection errors and process exit 2, so every run below used the project virtualenv.
- **Baseline command (before any change):** `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp`. Pytest result: **470 passed in 15.27s**. Process exit: **0**.
- **Final command:** `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp`. Pytest result: **532 passed in 13.64s**. Process exit: **0**. The known native shutdown abort was not observed in these runs.
- **Static check:** `.venv\Scripts\python.exe -m compileall -q src tests`. Process exit: **0**.
- **New and changed tests:** `tests/test_scenario.py::test_only_configured_turning_movements_are_used_in_a_run`, `::test_control_types_survive_save_and_reload`; `tests/test_scenario_serialization.py::test_incomplete_or_malformed_document_is_rejected_and_not_saved` (20 cases), `::test_empty_or_non_object_json_file_is_rejected` (6 cases); `tests/test_store.py::test_incomplete_import_is_rejected_with_nothing_stored` (8 cases); `tests/test_demand.py::test_demand_issues_have_network_issue_shape`, `::test_ratio_sum_tolerance_is_1e_6`, `::test_invalid_duration_issue_code`, `::test_plain_string_errors_still_accepted`; `tests/test_scenario_validation.py` (new file). The previously shadowed `tests/test_network.py::test_empty_network_blocked` now runs; its same-named duplicate was renamed `test_empty_lists_network_blocked`.
- **Defects fixed:**
  1. `sim/serialization.py` `scenario_from_dict` checked that `simulation.seed`, `duration_s` and `time_step_s` were present but not their types, so a document with `"seed": "42"` or `"time_step_s": null` was saved to the Scenario Store and exported. It now rejects wrong types with `ScenarioFormatError`.
  2. `sim/scenario.py` `build_engine` reported unknown movements, a bad `time_step_s` and a bad `duration_s` one at a time, through different exceptions (`DemandError`, a bare `ValueError` raised after demand generation). It never checked that demand entry segments exist. The new `validate_scenario` reports every problem at once before any engine work. Blocking errors raise `DemandError` (a `ValueError`), so existing callers still catch them.
  3. `tests/test_network.py` defined `test_empty_network_blocked` twice, so the first test (which checks that `NetworkService.provide_network_state` blocks an empty network) never ran.
- **Remaining limitations:**
  - The conflicting-movement check needs intersection positions. When a position the check needs is missing, the plan is blocked with `CONFLICT_CHECK_UNAVAILABLE` instead of being judged. At stop/yield intersections the engine assumes a conflict when geometry is missing.
  - OD matrix demand is not implemented. Turning ratios apply to the first movement only (DEVIATIONS #2).
  - Stop control is treated as yield, with no full stop before the gap check (DEVIATIONS #3).
  - "Network entry" is not defined in the baseline. `validate_scenario` treats a segment that no turning movement leads onto as an entry. Demand on any other existing segment is only a `NOT_NETWORK_ENTRY` warning, because no submitted document makes it blocking.
  - Warnings from `validate_scenario` are returned to callers but are not yet shown in the UI (UI is out of this issue's scope).

## Issue #33 (S3-07) verification (2026-11-04)

- **Scope:** system integration across network, signal, demand, engine, metrics, store, comparison, CSV reporting and the Workbench. Workflow matrix, defects and blocked tests: `docs/system_integration_report.md`.
- **Environment:** Windows 11 build 26300; project virtualenv `.venv` with CPython 3.12.10, pytest 9.2.0, PySide6 6.12.0.
- **Baseline command (before any change):** `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp`. Pytest result: **470 passed in 15.27s**. Process exit: **0**.
- **Targeted command:** `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp tests/test_system_integration.py`. Pytest result: **16 passed, 2 xfailed**. Process exit: **0**. The two strict xfails record open defects SI-D2 and SI-D3.
- **Final command:** `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp`. Pytest result: **548 passed, 2 xfailed**. Process exit: **0**. The known native shutdown abort (K-3) was not observed in these runs; it is not claimed fixed.
- **Static check:** `.venv\Scripts\python.exe -m compileall -q src tests`. Process exit: **0**.
- **Source change:** `src/tms_sim/sim/serialization.py` accepts an empty `signal_plans` list (defect SI-D1), with regression tests in `tests/test_system_integration.py`.
- **Not executed:** one-hour GUI benchmarks (TC-PERF-01, TC-REL-01 GUI part), TC-UX-01, TC-PORT-01, and a human visual review for TC-SIM-04.

## Issue #30 (S3-04) final integrated verification (2026-11-09)

- **Branch:** `issue-30/s3-04-metrics-persistence-csv-validation`.
- **HEAD commit:** `9e5d2af670d7ce0c869d6a384623817fffa6d769`.
- **Worktree state:** Verification was performed with the Issue #30 changes uncommitted.
- **Environment:** Windows; Python 3.13.7; pytest 9.1.0.
- **Command:** `python -m pytest tests/test_metrics.py tests/test_store.py tests/test_scenario_comparison.py tests/test_reporting_export.py tests/test_scenario_serialization.py tests/test_system_integration.py tests/test_ui_results_dashboard.py tests/test_ui_run_history.py tests/test_ui_performance_charts.py --basetemp=.pytest_cache/issue30-final-verification`
- **Result:** 186 tests collected; 185 passed, 1 xfailed, 0 failed. Process exit code: **0**. Duration: **16.86 seconds**.
- **Static check:** `git diff --check` passed.
- **Test modules:** `tests/test_metrics.py`, `tests/test_store.py`, `tests/test_scenario_comparison.py`, `tests/test_reporting_export.py`, `tests/test_scenario_serialization.py`, `tests/test_system_integration.py`, `tests/test_ui_results_dashboard.py`, `tests/test_ui_run_history.py`, and `tests/test_ui_performance_charts.py`.
- **Acceptance areas covered:** Metric formulas and boundaries (delay, queue, throughput, speed, and travel time); run persistence after reopening SQLite; scenario serialization and library workflows; run comparison; run-summary and comparison CSV headers, values, precision, unavailable and non-finite values; consecutive-run auto-capture; dashboard, history, and performance-chart behavior.
- **Expected failure / known limitation:** The single xfail is SI-D3, involving removal of the last signal plan. Saving the resulting scenario remains unsupported; the test is intentionally marked as an expected failure.
- **TC-MET-05 metric-key clarification:** The existing comparison CSV schema was preserved and no metric-key column was added. The SRS specifies run-summary CSV requirements, while the test catalogue mentions stable metric keys. Whether that key expectation applies to comparison CSV remains pending team agreement; this point is not marked conclusively passed or failed.
- **Evidence artifact:** No separate evidence artifact was created; this execution record captures the command and result.
