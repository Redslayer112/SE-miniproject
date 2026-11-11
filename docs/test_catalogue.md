# Issue #11 â€” Test Catalogue (DRAFT)

**Project:** Traffic Management System (Simulation)
**Status:** Draft for team review; implementation and operational test procedures require verification. The broad measurable-NFR decision was approved on 2026-10-27. The TC-REL-01 operational procedure has been approved and executed successfully for headless engine reliability. TC-UX-01 and TC-PORT-01 still require their respective procedures and evidence.
**Source:** SRS v0.2, SAD v1.0, STP v1.0 uploaded for this task.
**Important:** Test steps are specifications; the Status column records execution outcomes and evidence where a test has run. Do not mark any test Passed until the implementation exists and the test has actually run.

**STP traceability note:** TC-NET-02 (TMS-F-011), TC-NET-04 (TMS-F-013), TC-SIM-03 (TMS-F-042), TC-MET-02 (TMS-F-051), and TC-MET-03 (TMS-F-052) are included in this draft catalogue but are missing from STP Â§13. Their corresponding STP traceability entries require team review and inclusion in a revised STP draft. This documentation gap does not establish that the associated functionality is implemented or tested.

## Common conventions

- Use isolated temporary storage for tests that read/write scenarios or completed runs.
- Prefer deterministic fixtures and a fixed PRNG seed.
- Record actual result, status (`Not Run`, `Passed`, `Failed`, or `Blocked`), evidence, and defect link for every execution.
- Names of modules and APIs are provisional until the project structure and module contracts are confirmed.
- Any behaviour depending on unresolved requirements is marked **Baseline decision required**.

## Functional test cases

| Test ID | SRS requirement | Preconditions / fixture | Steps | Expected result |
| --- | --- | --- | --- | --- |
| TC-NET-01 | TMS-F-010 | Valid directed network fixture | Create/edit intersections and segments; save; reload | Every intersection, segment and attribute (length, lanes, direction, speed limit) reloads unchanged |
| TC-NET-02 | TMS-F-011 | Network with signalized and stop/yield/uncontrolled intersections and allowed turns | Configure control types and permitted turns; inspect generated/available movements | Only configured turning movements are permitted during a run |
| TC-NET-03 | TMS-F-012 | Separate invalid fixtures: disconnected graph, zero-length segment, zero-lane segment, and missing receiving segment | Validate each fixture; attempt to start a run | Each defect produces a specific error associated with the offending element; invalid run is blocked |
| TC-NET-04 | TMS-F-013 | Valid version-tagged JSON scenario | Export scenario; import into clean temporary store; compare data | Network, signal plan and demand match the exported scenario; schema version is validated |
| TC-SIG-01 | TMS-F-020 | Valid signal plan with ordered phases | Set green, yellow and all-red durations; save/reload or inspect | Every phase and timing value is represented correctly |
| TC-SIG-02 | TMS-F-022 | Invalid timing fixture and conflicting-movement fixture using a matching network | Validate each signal plan against its network; attempt to use an invalid plan | Invalid timing and conflicting green movements are reported, and the invalid plan cannot be used |
| TC-DEM-01 | TMS-F-030 | Small network with entry points, arrival rates and turning ratios | Configure rates; generate arrivals over a defined interval; count arrivals | Counts are reasonably consistent with configured rates under a documented tolerance |
| TC-DEM-02 | TMS-F-032 | Same valid scenario and fixed seed | Generate/run twice; compare arrival events and metrics | Both runs produce identical vehicle arrivals and metrics |
| TC-SIM-01 | TMS-F-040 | Valid network, signal plan and demand | Advance simulation in fixed steps; observe vehicles and red signals | State advances by the configured step; vehicles follow the agreed model and do not cross red signals |
| TC-SIM-02 | TMS-F-041 | Valid runnable scenario | Start, pause, single-step, reset; try speed multipliers 0.5x, 1x, 2x, 4x | Pause freezes time/state; single-step advances one step; reset returns to t=0; speed controls match selection |
| TC-SIM-03 | TMS-F-042 | Scenario with configured total duration | Start run and allow duration to elapse | Run ends at configured simulated time within one step; final metrics are persisted exactly once |
| TC-SIM-04 | TMS-F-043 | Valid scenario with vehicles and signals | Render scenario; inspect vehicle positions, signals and queues; pan/zoom | Displayed state matches engine state; pan and zoom work |
| TC-MET-01 | TMS-F-050 | Completed, empty, and incomplete runs with lifecycle and measurement events | Recompute travel time, delay, queues per approach, throughput and average speed independently | Values match the event-log formula in `docs/issue10_acceptance.md`; unavailable values remain distinct from zero |
| TC-MET-02 | TMS-F-051 | Active and completed runs | Observe results dashboard and compare with `compute_metrics` | Required live metrics update and completed dashboard values match final event-log metrics |
| TC-MET-03 | TMS-F-052 | Completed run with known scenario, seed and configuration | Save; reopen store and reload | Scenario snapshot, seed, run configuration, metadata and metrics round-trip; malformed rows produce actionable errors |
| TC-MET-04 | TMS-F-053 | Two saved runs; include different scenario names, unavailable metrics, and incomplete status | Load, select and compare runs | Both run identities, units, absolute differences, unavailable states, and compatibility warnings are displayed |
| TC-MET-05 | TMS-F-054 | Completed run with measured values and unavailable metrics | Export CSV and parse the written file | Stable metric keys, names, units, statuses and one-decimal values match the summary; path/write errors are reported |
| TC-LIB-01 | TMS-F-060 | Valid scenario in isolated scenario store | Save, list, load, rename and delete scenario | Each operation succeeds; list reflects changes; deleted scenario is absent |

## Non-functional test cases

| Test ID | Requirement | Preconditions / procedure | Expected result | Status |
| --- | --- | --- | --- | --- |
| TC-PERF-01 | TMS-NF-001 | Reference scenario: up to 10 intersections / configured 500 vehicles per hour / seed 42 / 1 simulated hour at 1x; measure complete-run FPS | One-hour run completes and average FPS is at least 15 using `(frames - 1) / elapsed wall seconds between first and last paint` | **Passed â€” acceptance-eligible (2026-11-09).** `artifacts/issue12/tc_perf_01_full_run_controlled_retry2_2026-11-09.json`: 3,600.1 simulated seconds, 72,008 frames, 15.96 FPS; all nine acceptance checks true, process exit 0, cleanup succeeded, no input events or storage errors. Earlier failures remain historical. The artifact records an AMD64 Windows 11 host; any separate Intel reference-hardware conformance remains unverified. |
| TC-REL-01 | TMS-NF-002 | Execute three independently supervised headless simulation-engine runs using seeds 42, 43, and 44; use a 3,600-second simulated duration and 60-second wall-clock timeout per run; verify completion, state consistency, metrics consistency, exception handling, and process cleanup | All three runs pass the approved operational procedure; negative controls are detected; no child processes remain after cleanup | **Passed â€” headless engine reliability (2026-11-11).** All three independent runs passed 20/20 runner checks, exited 0, did not time out, and completed cleanup with no remaining PIDs. The runner-exception and cleanup-failure negative controls were detected. The real process-tree test passed all six checks. Summary: `artifacts/issue12/tc_rel_01/supervisor_reliability_20261111T120702_740960Z.json`. Procedure: `docs/issue12_tc_rel_01_procedure_proposal.md`. GUI, Workbench, and operating-system reliability are not established. |
| TC-UX-01 | TMS-NF-003 | Conduct the documented human usability evaluation; record participants, task completion, time, and assistance | Meet the documented TC-UX-01 procedure | **Blocked - matrix and evidence missing.** The broad measurable-NFR decision was approved on 2026-10-27, but the human evaluation procedure is not documented and no participant evaluation has been performed. Automated fixture workflow is not UX evidence. |
| TC-PORT-01 | TMS-NF-004 | Install and run the reference scenario on each Windows version in the explicit installation matrix; record clean-install results | Meet the documented TC-PORT-01 platform matrix | **Blocked - matrix and evidence missing.** The broad measurable-NFR decision was approved on 2026-10-27. Current evidence is from an existing Windows 11 build 26300 environment; clean-install verification for the specified matrix has not been performed. |

## Execution record template

For each test execution, record:

- Test ID and date
- Commit hash / application version
- Environment and Python version
- Status: Not Run / Passed / Failed / Blocked
- Actual result and evidence path
- Defect issue link, if applicable

## Open dependencies

1. **Issue #1 / baseline follow-up:** The broad measurable-NFR decision was approved on 2026-10-27 and is recorded in `docs/decisions/0001-baseline-proposal.md`. TC-REL-01 headless reliability procedure and execution are complete. TC-UX-01 human usability evaluation procedure and participant evidence remain outstanding. TC-PORT-01 Windows installation matrix and clean-install verification remain outstanding.
2. **Issue #2:** Confirm the Python project structure, test framework, test command and module contracts.
3. Do not invent API names or mark tests passed before execution.
4. Ensure each invalid fixture is tested against the appropriate validator or importer. Fixtures that contain only a network or signal-plan fragment require a matching test setup; they are not necessarily standalone runnable scenarios.
5. Keep unresolved requirement mappings flagged for clarification rather than inventing requirement text.