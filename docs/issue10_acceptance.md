# Issue #10 — Metrics, comparison, persistence, and CSV

## Metric definitions

All times are simulated seconds, distances metres, speeds metres per second, queues
vehicles, and throughput vehicles per simulated hour. Calculations retain full
floating-point precision. Dashboard, comparison, and CSV values display one decimal;
comparison absolute deltas display two decimals and percentage deltas one decimal.

| Metric | Calculation | Edge cases and data source |
|---|---|---|
| Average travel time | Arithmetic mean of `exit_time - spawn_time` for uniquely matched completed trips | `None` when no trip has both events. Trips still in the network are excluded. |
| Average vehicle delay | Mean of `max(0, travel_time - free_flow_time)` for completed trips | Free-flow time is the sum of remaining route-segment distance divided by each segment's speed limit. `None` when no completed trip has a free-flow observation. |
| Maximum vehicle delay | Maximum completed-trip delay by the same formula | `None` when there are no completed trips with free-flow observations. |
| Average queue length per approach | For each segment, sum of sampled queued vehicles times step duration divided by elapsed simulation time | A queued vehicle has speed below 0.5 m/s. Every approach is represented, including measured zero. `None`/empty mapping before any positive-duration sample. The legacy network-wide scalar is the sum of per-approach averages. |
| Throughput | Completed unique trips divided by elapsed simulation hours | `None` at zero elapsed time; measured zero when time has elapsed but no trip completed. |
| Average speed | Total simulated vehicle distance divided by total vehicle-seconds, including stationary time | Recomputed from per-step measurement events. `None` when no vehicle-time was measured. |

The engine preserves its original four-field lifecycle tuple list for existing callers.
`metric_events` is the canonical append-only event log for reporting: spawn and exit
events carry route free-flow observations, and step samples carry speed-distance,
vehicle-time, and per-approach queues. Live values and final values use the same pure
recomputation over this log. Incomplete trips count as entered and can contribute to
speed/queue measurements, but do not contribute to completed-trip time or delay.

## Verification added

- `tests/test_metrics.py`: independent hand-calculation from lifecycle and measurement
  events, queue by approach, completed/incomplete trip handling, empty-run behavior.
- `tests/test_engine.py`: existing deterministic engine and lifecycle coverage.
- `tests/test_ui_results_dashboard.py`: live and final dashboard consistency.
- `tests/test_store.py`: metadata/configuration round trip and malformed/non-finite data.
- `tests/test_scenario_comparison.py`: persisted run selection and metric differences,
  including different scenario names.
- `tests/test_reporting_export.py`: stable CSV schema and actual exported metric values.
- `tests/test_ui_run_history.py`: detailed summary includes modeled metrics.

## Acceptance checklist

| Criterion | Status | Evidence / remaining work |
|---|---|---|
| 1. Metrics calculation | PASS | `src/tms_sim/reporting/metrics.py`, `src/tms_sim/sim/engine.py`, `tests/test_metrics.py`; targeted suite passed. |
| 2. Event-log recomputation and live/final consistency | PASS | `metric_events`, `tests/test_metrics.py`, `tests/test_ui_results_dashboard.py`; targeted suite passed. |
| 3. Persistence and reload | PASS | `src/tms_sim/storage/store.py`, UI capture/load flows, `tests/test_store.py`; targeted suite passed. |
| 4. Two-run comparison | PASS | `src/tms_sim/reporting/comparison.py`, persisted-run dialog flow, `tests/test_scenario_comparison.py`; targeted suite passed. |
| 5. CSV output and error handling | PASS | `src/tms_sim/reporting/export.py`, `tests/test_reporting_export.py`; targeted suite passed. |
| 6. Unit/integration tests | PASS | Targeted suite: 103 passed. Full suite: 402 passed. |

## Test execution

- Targeted command: `python -m pytest -q tests/test_engine.py tests/test_metrics.py tests/test_store.py tests/test_scenario_comparison.py tests/test_reporting_export.py tests/test_ui_results_dashboard.py tests/test_ui_run_history.py`
- Result: **103 passed**.
- Full-suite command: `python -m pytest -q`
- Result: **402 passed**.
- `python -m compileall -q src tests` completed successfully; `git diff --check` reported no whitespace errors.

## Limitations

- Queue length is an operational model measurement based on speed below 0.5 m/s, not
  a lane occupancy or physical detector model.
- Delay uses speed-limit free-flow travel time and excludes incomplete trips; it does
  not model a separate desired-speed profile.
- Automated verification is incomplete until the targeted tests and full suite execute
  in an environment with the project's declared dependencies (`pytest` and PySide6).
