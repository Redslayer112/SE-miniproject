# 0001 – Baseline proposal for issue #1 (engine/core owner's input)

**Status: PROPOSED. Nothing here is approved.** Issue #1 requires all four teammates to review and record a decision, owner and rationale. Each row below is a recommendation to accept, change or reject; the code in `src/tms_sim/sim/` follows it so work could start, and changes if the team decides otherwise.

| # | #1 item | Proposal | Where it lives in code |
|---|---|---|---|
| 1 | Car-following model | Intelligent Driver Model (Treiber et al. 2000): `a = a_max·(1 − (v/v0)^4 − (s*/s)^2)`, `s* = s0 + v·T + v·Δv / (2·√(a_max·b))` | `engine.Engine._accel` |
| 2 | Model parameters | `a_max` 1.5 m/s², `b` 2.0 m/s², `s0` 2.0 m, `T` 1.5 s, vehicle length 5 m, braking floor −9 m/s². `v0` = segment speed limit. | `engine.Params` |
| 3 | Time step | 0.5 s fixed (SRS TMS-F-040 allows 0.1–1.0 s); semi-implicit/trapezoidal update | `Params.dt` |
| 4 | Signals | Only `green_s` is green; yellow and all-red are red. Red = stationary obstacle at the stop line. A vehicle that cannot stop before the line even at max braking when the light changes (dilemma zone) proceeds; it clears during yellow | `scenario.phase_green`, `Engine._blocked` |
| 5 | Gap acceptance | A segment that yields takes a gap only if no *moving* conflicting vehicle is within 3.0 s of its stop line. Stationary conflicting vehicles are ignored (avoids deadlock; known simplification) | `Engine._blocked`, `Params.critical_gap` |
| 6 | PRNG | One `random.Random(seed)`; entries visited in sorted order; Poisson arrivals (`expovariate`); movement via `choices` over the turning ratios. The engine itself uses no randomness | `demand.generate_vehicles` |
| 7 | Storage (v1) | JSON files in a scenarios folder with a `schema_version` field; no SQLite for v1 (fewer dependencies, human-diffable). Decision needed before #9 | not implemented |
| 8 | Module contracts | See below | `sim/demand.py`, `sim/engine.py` |

## Proposed contracts (SAD §4.3)

- **Demand → Engine:** `generate_vehicles(seed, arrival_rates, turning_ratios, *, duration_s) -> list[Vehicle]` (adds `duration_s` to the SAD signature). Entry and movement ids are strings owned by the network model.
- **Network/Signals → Engine** (plain data so #3/#5 need no engine imports): `segments: id → Segment(length_m, speed_limit_mps)`, `routes: (entry, movement) → [segment ids]`, `signals: (from segment, to segment) → green(t) -> bool` per movement, `yields_to: segment id → [segment ids]`. `sim/scenario.py` builds these from the `Network` (#3) and `SignalPlan` (#5) objects, so neither module needs to change.
- **Engine → Metrics:** `engine.events` = `(time, vehicle_id, "spawn" | "exit", segment_id)` and `engine.exited`; `on_finish(engine)` fires exactly once per run.
- **Engine → UI:** `start/pause/step/reset/set_speed(0.5|1|2|4)/advance(wall_seconds)`; the UI timer calls `advance`.

## Items for the team that this proposal does *not* settle

SRS version (v0.2 vs v1.0), access-control/admin scope vs SAD §3.9/STP §5.1, measurable criteria for TMS-NF-002/003/004, missing STP trace rows (TMS-F-011/013/042/051/052), the Jira reference and September schedule in STP §6. These need team decisions; no choice is made here.
