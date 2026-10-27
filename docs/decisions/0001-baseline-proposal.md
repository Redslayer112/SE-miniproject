# 0001 – Specification baseline (issue #1)

**Status: APPROVED by all four teammates on issue #1** (dispositions by @vikhyathks-10, @hashvyas, @vikasnnaik, @Redslayer112; final confirmation 27 Oct 2026). The SRS/SAD/STP document owners still need to copy these decisions into the documents before #1 closes.

| # | Item | Decision | Rationale | Where in code |
|---|---|---|---|---|
| 1 | Access control / admin | Deferred for v1; security scope stated explicitly in the documents | SRS describes a local, single-Analyst desktop app (SAD §3.9, STP §5.1) | — |
| 2 | Authoritative SRS | SRS v1.0, keeping the v0.2 revision history; README/SAD/STP references updated to match | One baseline for all documents | — |
| 3 | Measurable NFRs | Accepted. FPS = average frames per second over the full one-hour run on the reference hardware. Reference scenario, crash-check, usability procedure and Windows evidence to be documented | Makes TMS-NF-001..004 testable | `docs/performance_instrumentation.md` |
| 4 | STP trace rows | Add rows for TMS-F-011/013/042/051/052. TMS-F-021 and TMS-F-031 have no requirement text and are retired | Complete RTM | `docs/rtm_draft.csv` |
| 5 | Storage / schema | SQLite (stdlib `sqlite3`) for the local scenario library and completed runs; versioned JSON (`schema_version` "1.0") for import/export. Scenario = network, signal plan(s), `demand.arrival_rates_vehicles_per_hour` {entry segment: veh/h ≥ 0}, `demand.turning_ratios` {movement id: ratio, summing to 1 ±1e-6 per entry}, `simulation.seed`, `simulation.duration_s` (> 0), `simulation.time_step_s` (0.1–1.0, default 0.5) | Library needs rename/list/persist; JSON stays human-readable for exchange | `storage/store.py`, `sim/serialization.py` |
| 6 | Car-following | IDM (Treiber et al. 2000): `a = a_max·(1 − (v/v0)^4 − (s*/s)^2)`, `s* = s0 + v·T + v·Δv / (2·√(a_max·b))`. `v0` = segment `speed_limit_mps` (no override in v1). `a_max` 1.5 m/s², `b` 2.0 m/s², `s0` 2.0 m, `T` 1.5 s, braking floor 9 m/s², **vehicle length 5.0 m** (gap = leader rear bumper − own front bumper). Fixed time step, trapezoidal position update | Documented, standard model; one vehicle type since F-031 is retired | `sim/engine.py` `Params`, `_accel` |
| 6a | Signals | Only green is green; yellow and all-red are red; red = stationary obstacle at the stop line. A vehicle that cannot stop before the line even at 9 m/s² when the light changes may clear during yellow | No red-light running except the physical dilemma zone | `sim/scenario.py` `phase_green`, `Engine._blocked` |
| 6b | Gap acceptance | **Critical gap 3.0 s**, only at stop- and yield-controlled intersections. A vehicle on a yielding approach is held at its stop line while any moving (> 0.5 m/s) vehicle on a conflicting approach is < 3.0 s from its own stop line (distance ÷ speed). Stationary conflicting vehicles are ignored (avoids deadlock). Stop-controlled is treated as yield (DEVIATIONS #3). Signalized movements obey the signal only | Simple, deterministic, testable | `Engine._blocked`, `Params.critical_gap` |
| 7 | Tooling / schedule | GitHub Issues replaces Jira in the STP; test dates follow the sprint schedule | Matches how the team works | — |
| 8 | Validation contract | Result object with a list of issues (element id, element type, code, message, severity `error`/`warning`). Valid = zero errors; warnings never block a run. `validateSignalPlan` takes the network | Shared shape for the UI error list (SRS §3.1) | `network/validation.py`, `signal/validation.py` |
| 9 | Conflicting movements | Crossing or merging inside an intersection conflict. Same-approach exception only for movements from one approach to different receiving segments; different approaches into one receiving segment always conflict. Missing positions → located validation error. Left-hand traffic, y-up axes (UI converts screen coordinates) | Safety constraint SRS §2.5 | `signal/conflicts.py` |
| — | PRNG | One `random.Random(seed)`; entries visited in sorted order; Poisson arrivals; movement drawn from turning ratios. The engine itself has no randomness | Reproducibility (TMS-F-032) | `sim/demand.py` |

## Module contracts (SAD §4.3)

- **Demand → Engine:** `generate_vehicles(seed, arrival_rates, turning_ratios, *, duration_s) -> list[Vehicle]`.
- **Network/Signals → Engine:** `sim/scenario.py` turns the `Network` and `SignalPlan`s into `segments`, `routes`, per-movement `signals` and `yields_to`; invalid input is blocked through `NetworkService.provide_network_state()` and `SignalService`.
- **Engine → Metrics:** `engine.events` = `(time, vehicle_id, "spawn" | "exit", segment_id)`, `engine.exited`; `on_finish(engine)` fires once per run.
- **Engine → UI:** `start/pause/step/reset/set_speed(0.5|1|2|4)/advance(wall_seconds)`.
- **Scenario Store ↔ Workbench:** `ScenarioStore.save_scenario/list_scenarios/load_scenario/duplicate_scenario/rename_scenario/delete_scenario/import_scenario/export_scenario`, and `save_run/list_runs/load_run` for completed runs (#10). SAD names `saveScenario/loadScenario/listScenarios/saveRun` are aliases.
