# TMS System Validation Report

**Report ID:** TMS-TR-SYS-01
**Date:** 6 November 2026
**Project:** Traffic Management System (Simulation), UE24CS341A, PES University
**Purpose:** Faculty/system-level validation summary for Sprint 3 reporting.

## Scope and evidence basis

This report summarizes available automated integration, repeatability, performance and platform evidence. It does not claim manual usability testing, clean-install testing, faculty approval, or performance acceptance where those were not evidenced. It uses the checked-in Issue #12 evidence and the 6 November pytest executions. The GitHub API/CLI in this execution environment did not provide access to Issue #34, so the report's title as the fourth requested report is based on the earlier Sprint 3 task specification supplied in this conversation, which named “System Validation Report.” Verify against the live Issue #34 text when GitHub access is restored.

## Validation summary

| Area | Evidence and observed result | Status |
|---|---|---|
| Automated suite | 457 passed, 0 failed, 0 skipped in the 6 November standard run; pytest reported 47.93 seconds. Process exited `-1073740791` (`0xC0000409`). Coverage-instrumented run also reported 457 passed in 35.88 seconds and the same abnormal exit. | Assertions passed; process completion unresolved |
| Headless reliability | `artifacts/issue12/system_checks.json`: seeds 42, 43, 44 each completed 3,600.1 simulated seconds without a recorded crash/exception. | Evidence exists; **TC-REL-01 remains blocked** pending approved acceptance interpretation and whether GUI repetitions are required |
| Determinism | Same seed-42 fixture: two runs; demand identical; all 36,940 metric event entries and reported metrics identical; required metrics non-null. | Automated evidence **Passed** for recorded check |
| Analyst workflow | Two-intersection fixture loaded; scenario save/export/import/reload; runs completed/persisted/reloaded; dashboard updated; compatible comparison; CSV parsed with 20 rows; database isolated in temporary directory. | Automated fixture integration **Passed**; not human UX evidence |
| TC-PERF-01 | `artifacts/issue12/tc_perf_01_full_run_pause_provenance_v1.json`: 3,600.1 seconds completed at 1x; 72,055 frames; 13.25 FPS vs >=15; process exit 0. Seven spontaneous external mouse ingress events had uncertain native identity; acceptance eligibility false. | **Failed target / not acceptance-eligible** |
| UI usability | No new-user participant protocol, task timing, assistance observation or participant results in reviewed evidence. | **Blocked / not performed** |
| Portability | Evidence is from existing Windows 11 build 26300 environment; no clean Windows 10/11 installation was run. | **Blocked / not performed** |
| Traceability and baseline | STP §13 omits some cases present elsewhere; `docs/rtm_draft.csv` labels several mappings draft. Issue #1 criteria are proposals pending approval. | **Open documentation/baseline dependency** |

## Performance detail

The latest completed 1x run achieved 13.25 FPS using `(72,055 - 1) / 5,437.181` wall seconds between first and last paint. It completed the simulated hour without storage errors and with successful application cleanup. Its FPS is under the 15 FPS criterion. External input identity is uncertain, so the run is also not eligible as a clean-input acceptance run. Historical runs and the 300-second diagnostic are described in `artifacts/issue12/tc_perf_01_performance_report_2026-11-03.md`; short/4x results do not substitute for the full-hour 1x requirement.

## Dependencies and limitations

- Issue #1 baseline decisions remain necessary for measurable TC-REL-01, TC-UX-01 and TC-PORT-01 protocols. Proposal values must not be represented as approved criteria.
- The SRS reference CPU is Intel i5-11400H and 16 GB RAM. The latest benchmark host metadata reports an AMD processor string and does not report RAM; it is not a verified reference-hardware result.
- The full-suite Python shutdown status remains unresolved. Test assertion summaries and process exit status are recorded separately in `docs/unit_test_report_2026-11-06.md`.
- No separate faculty instruction file or a retrievable live Issue #34 body was available in this execution environment. The STP lists test cases, execution results, defect reports, RTM updates and a Test Summary Report as deliverables.

## Overall disposition

Automated component and fixture-integration evidence is substantial, but **system acceptance is incomplete**. TC-PERF-01 is below target and ineligible; reliability criteria are awaiting approval; UX and clean-platform validation have not been performed. Do not close Issue #12 or mark the release accepted based on this report alone.
