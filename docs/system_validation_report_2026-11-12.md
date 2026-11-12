# TMS System Validation Report

**Traffic Management System (Simulation)** · Software Engineering UE24CS341A · PES University

| Team member | SRN |
|---|---|
| Venkata Srivaibhav Nukaraju | PES2UG24CS579 |
| V Vyas | PES2UG24CS569 |
| Vikas N Naik | PES2UG24CS583 |
| Vikhyath Bharadwaj K S | PES2UG24CS586 |

**Report ID:** TMS-TR-SYS-02 (supersedes TMS-TR-SYS-01 of 6 November 2026)  
**Date:** 12 November 2026  
**Code measured:** `main` at commit `4366043` (merge of PR #47)


**Purpose:** system-level validation summary for Sprint 3: whether the built system meets the requirements in the SRS (v1.1), using the Test Plan (v1.1) cases.

## 1. Scope and evidence basis

This report combines (a) the automated suite on commit `4366043`, (b) the system integration tests SI-01 to SI-08, (c) the Issue #12 non-functional evidence in `artifacts/issue12/`, and (d) the final Requirements Traceability Matrix (`docs/RTM.csv`). It claims only what that evidence shows: it does not claim human usability testing, testing on clean Windows installations, or testing on the SRS reference hardware, because none was done.

## 2. Requirement-level result (RTM, 26 requirements)

| Status | Requirements |
|---|---:|
| Verified | 19 |
| Partially Verified | 1 |
| Blocked | 2 |
| Deferred | 2 |
| Retired | 2 |

| ID | Requirement | Final status |
|---|---|---|
| TMS-F-010 | Create/edit directed road network and preserve attributes | Verified |
| TMS-F-011 | Intersection control type configuration and permitted turns | Verified |
| TMS-F-012 | Validate network topology and block invalid runs | Verified |
| TMS-F-013 | Version-tagged JSON scenario import and export | Verified |
| TMS-F-020 | Define fixed-time signal phases and timing intervals | Verified |
| TMS-F-021 | Actuated signal control | Retired |
| TMS-F-022 | Detect and reject conflicting signal plan movements | Verified |
| TMS-F-030 | Configure vehicle arrival rates and turning ratios | Verified |
| TMS-F-031 | Multi-class vehicle classification | Retired |
| TMS-F-032 | Deterministic simulation repeatability | Verified |
| TMS-F-040 | Fixed-step microscopic traffic flow simulation | Verified |
| TMS-F-041 | Simulation playback controls and speed adjustment | Verified |
| TMS-F-042 | Simulation termination at configured duration and finalization | Verified |
| TMS-F-043 | 2D visualization of vehicles signals and queue states | Verified |
| TMS-F-050 | Compute traffic performance metrics | Verified |
| TMS-F-051 | Display live metrics during simulation execution | Verified |
| TMS-F-052 | Persist completed simulation run records | Verified |
| TMS-F-053 | Compare completed simulation runs side-by-side | Verified |
| TMS-F-054 | Export simulation results as CSV and HTML reports | Verified |
| TMS-F-060 | Scenario library management (SQLite) | Verified |
| TMS-F-061 | Multi-user scenario sharing across network/cloud | Deferred |
| TMS-SEC-001 | User authentication roles and access audit logs | Deferred |
| TMS-NF-001 | Performance: 10-intersection reference scenario >=15 FPS at 1x for 1 hour | Verified |
| TMS-NF-002 | Reliability: 1-hour simulation execution without crash or resource leak | Partially Verified |
| TMS-NF-003 | Usability: user evaluation of scenario setup and analysis workflows | Blocked |
| TMS-NF-004 | Windows portability: verified operation across Windows 10 and 11 | Blocked |

Deferred and retired requirements are team decisions recorded in `docs/decisions/0001-baseline-proposal.md` and `DEVIATIONS.md`.

## 3. System workflows (integration tests)

All eight workflows pass in `tests/test_system_integration.py` (19 test cases); details are in `docs/system_integration_report.md`.

| ID | Workflow | Result |
|---|---|---|
| SI-01 | Network creation, signal configuration and demand generation feed the engine | Passed |
| SI-02 | Simulation execution and vehicle visualization (TC-SIM-04, canvas paint calls against engine state) | Passed |
| SI-03 | Simulation, metrics, `save_run`, reload | Passed |
| SI-04 | Run comparison, including incomplete and cross-scenario runs | Passed |
| SI-05 | CSV report export parses back to the same metrics | Passed |
| SI-06 | Workbench: library load, run, dashboard, run history, comparison, CSV | Passed |
| SI-06a | A run finished after a library load is captured without pressing Reset (defect SI-D2, fixed) | Passed |
| SI-07 | Determinism through the persisted path | Passed |
| SI-08 | Representative scenarios (small signalized, 10-intersection, stop/yield) store, load, run, persist; invalid scenarios are blocked | Passed |
| SI-08a | Scenario stays saveable after its last signal plan is removed (defect SI-D3, fixed) | Passed |

Determinism evidence: two seed-42 runs of the reference scenario produced identical demand and identical metric event logs (36,940 events, SHA-256 `b7bca45d208e7a33…`), recorded in `artifacts/issue12/system_checks.json`.

## 4. Non-functional validation

| Test | Requirement | Result |
|---|---|---|
| TC-PERF-01 | TMS-NF-001 | **Passed** (controlled rerun, 9 Nov 2026), reference hardware not verified |
| TC-REL-01 | TMS-NF-002 | **Partially verified**: headless engine passed 3 of 3; GUI reliability not established |
| TC-UX-01 | TMS-NF-003 | **Blocked: not performed** |
| TC-PORT-01 | TMS-NF-004 | **Blocked: not performed on clean machines** |

### 4.1 TC-PERF-01 (performance)

Requirement: at least 15 FPS over a one-hour run at 1× on the 10-intersection reference scenario.

| Item | Value |
|---|---|
| Scenario / seed / speed | `performance_10_intersections.json`, seed 42, 1× |
| Simulated time | 3,600.1 s (470 vehicles generated) |
| Frames / wall time | 72,008 frames in 4,510.7 s |
| **Full-run FPS** | **15.96** (criterion ≥ 15) |
| Average frame time | 3.15 ms |
| Peak memory / CPU time | 145.5 MiB / 636.5 s |
| Process exit / cleanup / storage errors | 0 / ok / none |
| Unexpected external input | none recorded; all acceptance checks true |
| Host | Windows-11-10.0.26300-SP0, Python 3.13.7, AMD64 (AMD processor) |
| Evidence | `artifacts/issue12/tc_perf_01_full_run_controlled_retry2_2026-11-09.json` |

Limits: the SRS reference CPU is an Intel i5-11400H with 16 GB RAM; this host is different, so conformance to the reference hardware is unverified (`DEVIATIONS.md` row 8). Earlier attempts are kept as history: a one-hour 1× run stalled at 2,123.6 s, and a later completed run measured 13.25 FPS but was ineligible because of uncertain external mouse input. For scale, the headless one-hour engine runs in section 4.2 each took 2 to 3 seconds of wall time, so the frame-rate requirement concerns the GUI, not the engine.

### 4.2 TC-REL-01 (reliability)

Approved procedure (team approval on Issue #12): three independent one-hour runs with seeds 42, 43 and 44; 60 s wall-clock timeout per run; all runs are executed and recorded even after a failure; the test passes only if all three pass; separate negative controls for a runner exception and a cleanup failure; supervision of child processes during cleanup.

| Seed | Simulated time | Timeout | Wall time | Exit | Timed out | Result |
|---:|---:|---:|---:|---:|---|---|
| 42 | 3600 s | 60 s | 3.2 s | 0 | no | Passed |
| 43 | 3600 s | 60 s | 3.2 s | 0 | no | Passed |
| 44 | 3600 s | 60 s | 2.2 s | 0 | no | Passed |

Overall status **Passed** (`artifacts/issue12/tc_rel_01/supervisor_reliability_20261111T120702_740960Z.json`). Both negative controls and the process-tree check also passed, and no process was left running. Scope: the headless simulation engine. The GUI version of the test is not established (an earlier GUI attempt had 1 of 3 clean runs, with the others paused by mouse input), so the requirement stays *partially verified* (`DEVIATIONS.md` row 9).

### 4.3 TC-UX-01 (usability) and TC-PORT-01 (portability)

- **TC-UX-01 was not performed.** No new-user participants were available in the project window. The automated Qt tests exercise the workflows but are not usability evidence (`DEVIATIONS.md` row 10).
- **TC-PORT-01 was not performed on clean machines.** Evidence that exists: the Windows 11 host used for the performance and reliability runs; the GitHub Actions `windows-latest` runner (Python 3.11), where the same commit passes 597 tests with exit code 0 ([run 43161235305](https://github.com/Redslayer112/SE-miniproject/actions/runs/43161235305)); and a local Linux run of the same 597 tests. These show the software runs on those environments; they do not replace clean Windows 10 and Windows 11 installations (`DEVIATIONS.md` row 11).

## 5. Defects found during validation

| Defect | Status |
|---|---|
| Red light skipped on a short segment; one jammed entry blocked all others; clock drift (PR #38) | Fixed, with regression tests |
| SI-D1: stop/yield scenarios unsaveable (PR #40) | Fixed |
| SI-D2: run not captured after a scenario load | Fixed |
| SI-D3: scenario unsaveable after deleting the last signal plan | Fixed |
| Intermittent non-zero exit after all tests passed on Windows CI (PR #25) | Fixed in CI; a residual native shutdown abort on some Windows hosts is a documented limitation |

## 6. Known limitations

- No usability study and no clean-machine portability test (section 4.3).
- Performance was met once, in a controlled run on a non-reference host (section 4.1).
- GUI reliability over an hour is not established; the engine's is (section 4.2).
- Model scope: one vehicle type, no lane changing, stop control treated as yield, left-hand traffic. Demand is by arrival rate and turning ratios; there is no OD matrix. No accounts, roles or scenario sharing (deferred).
- All deviations from the SRS, SAD and Test Plan are listed in `DEVIATIONS.md`.

## 7. Overall disposition

All functional requirements that remain in scope are verified (19 of 26 requirements verified; 2 deferred and 2 retired by team decision). The system workflows pass end to end. Of the four non-functional requirements, performance is verified, reliability is verified for the headless engine, and usability and portability are not verified; these gaps are disclosed and recorded as deviations rather than claimed as passed.
