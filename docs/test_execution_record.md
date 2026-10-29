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
