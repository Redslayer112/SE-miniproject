# Final Submission Checklist (S3-10, #36)

Status as of 5 Nov 2026, the day before the 6 Nov deadline. A box is ticked only when the evidence named next to it exists in the repository or in a CI run.

## 1. Setup and execution verified on a clean environment

Verified on 5 Nov 2026 by a fresh `git clone` of `main` (`cf9d928`) into an empty directory, with the README steps followed exactly:

| Step (README) | Result |
|---|---|
| `python -m venv .venv`, then `python -m pip install -e ".[dev]"` | Installed with no errors (Linux, Python 3.14) |
| `python -m tms_sim run tests/data/scenario/small_valid_scenario.json` | `simulated 600.0 s \| generated 30 \| entered 30 \| completed 30 \| in network 0`, `mean travel time 16.4 s`, exit 0. Matches the README example exactly |
| `python -m tms_sim` (GUI) | Workbench started and was still running after 8 s, with no error output |
| `python -m pytest` | 548 passed, 2 xfailed (SI-D2 and SI-D3 at this 5 Nov baseline run; SI-D2 was subsequently addressed in Issue #30, see §5) |
| GitHub Actions on `main` (Windows, Python 3.11) | Green after the #40 merge |

Not covered: clean Windows 10 and Windows 11 machines (DEVIATIONS row 11).

## 2. Demonstration scenario and script

| Scenario | Use in the demo |
|---|---|
| `fixtures/valid/small_valid_scenario.json` | Main demo. It is the same file as `tests/data/scenario/small_valid_scenario.json`. Signalized intersection, 600 s, seed 42, a known result (30 completed, 16.4 s mean travel time) |
| `fixtures/valid/small_stop_yield_scenario.json` | Stop and yield control with no signal plan |
| `fixtures/valid/performance_10_intersections.json` | Scale: 10 intersections (NFR reference scenario) |

Suggested order for the recording (about 2 minutes):

1. **Open the scenario.** Use File → Open Scenario… and choose `small_valid_scenario.json`. *(TMS-F-013)*
2. **Network.** Show the network on the canvas, then select a segment and a turning movement. Optionally add a road with Draw road and show that validation flags it. *(TMS-F-010/011/012)*
3. **Signals.** Open the signal plan and show its phases, then Apply Phase. *(TMS-F-020)*
4. **Run.** Press ▶ Play, change the speed (0.5×, 1×, 2× or 4×), then Pause and Step, and show vehicles stopping on red. *(TMS-F-040/041)*
5. **Metrics.** Let the run finish and show the live and final metrics: travel time, delay, queue, throughput and speed. *(TMS-F-042/050/051)*
6. **Second run.** Press ↺ Reset, change the seed or the signal timing, and run again.
7. **Compare.** Open 📜 Run History… and then ⚖ Compare Runs…, and select both runs. *(TMS-F-052/053)*
8. **Export.** Use 📄 Export CSV and 🌐 Export HTML, then open the CSV. *(TMS-F-054)*
9. **Library.** Press Ctrl+L to open the Scenario Library, then save, duplicate and load a scenario. *(TMS-F-060)*

Avoid one thing during the recording:

- **Usability note:** Press ↺ Reset before starting another run to reset the live simulation timeline and vehicle state cleanly. SI-D2 (run auto-capture after scenario load) and SI-D3 (scenario saving after deleting the only signal plan) are both resolved in code.

## 3. Testing reports under `docs/` (owner: #34)

- [x] Unit Test Report (`docs/unit_test_report_2026-11-12.md`)
- [x] System Validation Report (`docs/system_validation_report_2026-11-12.md`)
- [x] Code Coverage Report (`docs/code_coverage_report_2026-11-12.md`)
- [x] Branch Coverage Report (`docs/branch_coverage_report_2026-11-12.md`)

Evidence already in the repo: `docs/test_execution_record.md`, `docs/test_catalogue.md`, `docs/issue10_acceptance.md`, `docs/issue12_acceptance.md` and `docs/system_integration_report.md`. The engine unit and regression results are in the description of PR #38.

## 4. Documentation (owner: #35)

- [x] Baseline decisions approved: `docs/decisions/0001-baseline-proposal.md` (#1)
- [x] SRS/SAD/STP amendment: `docs/baseline_amendment_v1.1.md` (#26)
- [x] Deviations from SRS/SAD/STP: `DEVIATIONS.md`
- [x] `docs/FINAL_PROJECT_OVERVIEW.md`
- [x] RTM final pass: `docs/RTM.csv` (supersedes `rtm_draft.csv`)
- [x] README "Development status" note updated to reflect implemented status

## 5. Known limitations and unresolved defects (disclosed)

| Item | Status | Where documented |
|---|---|---|
| SI-D2: a run after a scenario load is not auto-captured | Resolved (Issue #30); verified in `test_system_integration.py` | `src/tms_sim/ui/app.py` `_reset_run_capture_state()`; `docs/test_execution_record.md` |
| SI-D3: removing the last single-key signal plan blocks saving | Resolved (UI, #29); verified in `test_system_integration.py` & `test_ui_issue29_stabilization.py` | `src/tms_sim/ui/app.py` `set_scenario_signal_plans()`; `docs/system_integration_report.md` |
| TC-PERF-01: 15 FPS over a one-hour run at 1× | Accepted via controlled rerun on 2026-11-09 (15.96 FPS, acceptance_eligible=true) | `artifacts/issue12/tc_perf_01_full_run_controlled_retry2_2026-11-09.json`; `docs/issue12_acceptance.md` |
| TC-REL-01: three clean one-hour runs | Verified for headless engine reliability (3 runs: seeds 42, 43, 44; 3,600s each, exit 0) | `artifacts/issue12/tc_rel_01/supervisor_reliability_20261111T120702_740960Z.json`; `docs/issue12_acceptance.md` |
| TC-UX-01: usability test | Not performed (no new-user participants available) | DEVIATIONS row 10, #12 |
| TC-PORT-01: clean Windows 10/11 machines | Verified on Windows 11 host and CI runner; clean multi-version matrix unperformed | DEVIATIONS row 11, #12 |
| Scope cuts: accounts and roles, sharing, 8× and unbounded speed, OD matrix, F-021 and F-031 | Deferred or retired by team decision | DEVIATIONS rows 1–7 and 12 |
| Gap acceptance ignores stationary conflicting vehicles. The leader search is O(n²) | By design (decision 0001) | `src/tms_sim/sim/engine.py` |

## 6. Final submission

- [x] GitHub Project backlog with story points, assignments and sprints
- [x] GitHub Actions run on every PR. Members raise PRs and the repo owner reviews and merges
- [x] Sprint 1 video: `demo/sprint1_demo.mp4`
- [ ] Sprint 2 video (2 min): `demo/sprint2_demo.mp4`, following §2
- [x] #34 reports merged (§3)
- [x] #35 documentation merged (§4)
- [ ] #12 closed, with the blocked tests recorded as deviations
- [ ] Demo rehearsed with all four members
- [ ] Development frozen. Tag the final `main` commit (for example `v1.0`)
