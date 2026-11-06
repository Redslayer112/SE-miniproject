# TMS Unit and Automated Test Report

**Report ID:** TMS-TR-UT-01
**Date:** 6 November 2026
**Project:** Traffic Management System (Simulation), UE24CS341A, PES University
**Environment:** Windows 11 build 26300; CPython 3.13.7; pytest 9.1.0; PySide6 6.12.0; coverage.py 7.17.0
**Scope:** The repository pytest suite under `tests/`, including unit, UI, integration and acceptance-script tests.

## Summary

| Run | Command | Pytest result | Duration | Process exit |
|---|---|---|---:|---:|
| Standard full suite | `python -m pytest -q --basetemp .pytest-tmp-s3-unit-53adad7fffd24c3f8cafbca7103352f1` | 457 passed; 0 failed; 0 skipped; no pytest error summary | 47.93 s | `-1073740791` (`0xC0000409`) |
| Coverage full suite | `COVERAGE_FILE=.coverage-s3-53adad7fffd24c3f8cafbca7103352f1`; `python -m coverage run --branch --source=src/tms_sim -m pytest -q --basetemp .pytest-tmp-s3-coverage-53adad7fffd24c3f8cafbca7103352f1` | 457 passed; 0 failed; 0 skipped; no pytest error summary | 35.88 s | `-1073740791` (`0xC0000409`) |

Both pytest summaries show all collected assertions passing. Both processes nevertheless terminated with a nonzero Windows status after the summary. Therefore the **assertion result is 457 passed**, while **clean process completion is not established**. No traceback was printed in the captured output; the root cause of the shutdown status remains undetermined. Do not report this as an unqualified process-level pass.

`tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` and uses pytest `tmp_path` to redirect the default scenario store for each test. UI/storage test fixtures use temporary paths. No user's normal scenario database was selected by the test configuration.

## Test coverage areas

The suite contains tests for network validation/editing, signal planning, demand generation, deterministic engine behavior, simulation lifecycle, metrics and incremental parity, scenario and run persistence, comparisons, CSV/HTML reporting, UI controls and visualization, scenario library, acceptance instrumentation, and error paths. The exact 457 collected test node IDs are not archived as a separate collection log; `docs/test_case_document.md` maps established STP cases to their corresponding test modules.

## Commands and supporting evidence

- Collection command: `python -m pytest --collect-only -q --basetemp=.pytest-tmp-s3-docs-collect` reported 457 tests collected in 10.91 seconds.
- Standard and coverage execution commands and exits are recorded above; all used unique worktree-local base directories.
- The coverage data from the instrumented execution is `docs/coverage_data_issue34_2026-11-06.json`.
- This report records only the executions performed on 6 November 2026. Earlier test totals in `docs/test_execution_record.md` are historical and are not substituted for these results.

## Limitations and disposition

The tests are automated and primarily use fixtures/offscreen Qt. They do not establish human usability, clean-install Windows portability, faculty sign-off, or the full performance criterion. The abnormal process exit is an unresolved environment/runtime issue; investigate native shutdown diagnostics separately without suppressing nonzero exits or weakening tests.

**Status:** Assertion-level suite result **PASS (457/457)**; command/process result **FAIL/UNRESOLVED** because exit code was nonzero. Full system acceptance remains incomplete.
