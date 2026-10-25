# Issue #11 — Test Catalogue (DRAFT)

**Project:** Traffic Management System (Simulation)  
**Status:** Draft for team review; implementation and baseline-dependent test criteria require verification.  
**Source:** SRS v0.2, SAD v1.0, STP v1.0 uploaded for this task.  
**Important:** These are test specifications, not execution results. Do not mark any test Passed until the implementation exists and the test has actually run.

**STP traceability note:** TC-NET-02 (TMS-F-011), TC-NET-04 (TMS-F-013), TC-SIM-03 (TMS-F-042), TC-MET-02 (TMS-F-051), and TC-MET-03 (TMS-F-052) are included in this draft catalogue but are missing from STP §13. Their corresponding STP traceability entries require team review and inclusion in a revised STP draft. This documentation gap does not establish that the associated functionality is implemented or tested.

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
| TC-MET-01 | TMS-F-050 | Completed run with event log suitable for independent recomputation | Compute average/maximum delay, average queue length, throughput, average speed and travel time | Reported metrics match independent calculations within documented rounding |
| TC-MET-02 | TMS-F-051 | Active run with generated events | Observe results dashboard during run | Required live metrics are displayed and update consistently with simulation state |
| TC-MET-03 | TMS-F-052 | Completed run with known scenario, seed and configuration | Save run; reload stored record | Run metrics, seed and configuration persist and reload correctly |
| TC-MET-04 | TMS-F-053 | Two completed runs on comparable scenarios | Compare the two runs | Comparison table presents the required metrics for both runs without mixing run identities |
| TC-MET-05 | TMS-F-054 | Completed run | Export summary metrics to CSV; parse exported file | CSV contains required metric headers and values; file is readable and corresponds to the selected run |
| TC-LIB-01 | TMS-F-060 | Valid scenario in isolated scenario store | Save, list, load, rename and delete scenario | Each operation succeeds; list reflects changes; deleted scenario is absent |

## Non-functional test cases

| Test ID | Requirement | Preconditions / procedure | Expected result | Status |
| --- | --- | --- | --- | --- |
| TC-PERF-01 | TMS-NF-001 | Reference scenario is proposed as 10 intersections / 500 vehicles / fixed seed / 1 simulated hour; measure FPS on agreed reference hardware | Target is at least 15 FPS average, subject to the team's approval of measurement method and scenario details | Not Run — baseline decision required |
| TC-REL-01 | TMS-NF-002 | Run the agreed seeded reliability scenario three times for one simulated hour each | All runs complete without crash; exact criteria require team approval | Not Run — baseline decision required |
| TC-UX-01 | TMS-NF-003 | Five new testers attempt to build and run a two-intersection network without help; time each attempt | At least four of five finish within ten minutes, subject to team approval | Not Run — baseline decision required |
| TC-PORT-01 | TMS-NF-004 | Install and run the agreed reference scenario on clean Windows 10 and Windows 11 environments | Installation, launch and scenario execution succeed on both environments | Not Run — baseline decision required |

## Execution record template

For each test execution, record:

- Test ID and date
- Commit hash / application version
- Environment and Python version
- Status: Not Run / Passed / Failed / Blocked
- Actual result and evidence path
- Defect issue link, if applicable

## Open dependencies

1. **Issue #1:** Confirm and document any remaining baseline decisions, including NFR criteria, storage/schema and simulation rules.
2. **Issue #2:** Confirm the Python project structure, test framework, test command and module contracts.
3. Do not invent API names or mark tests passed before execution.
4. Ensure each invalid fixture is tested against the appropriate validator or importer. Fixtures that contain only a network or signal-plan fragment require a matching test setup; they are not necessarily standalone runnable scenarios.
5. Keep unresolved requirement mappings flagged for clarification rather than inventing requirement text.
