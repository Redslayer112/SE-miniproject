# Rendering Performance Instrumentation (TC-PERF-01 / TMS-NF-001)

## 1. Background and Requirement
The non-functional requirement **TMS-NF-001** and its verification case **TC-PERF-01** specify that the simulation workbench must sustain a rendering throughput of at least **15 FPS** on reference hardware for a baseline network scenario consisting of:
- **10 intersections**
- **500 vehicles**
- Fixed random seed
- 1 simulated hour (3600 seconds)

To objectively evaluate this requirement without perturbing simulation engine dynamics, deterministic reproducibility, or introducing external profiling overhead, lightweight, built-in rendering performance instrumentation was implemented directly within `RoadCanvas`.

---

## 2. Instrumentation Architecture

### 2.1 Frame Timing Capture
`RoadCanvas.paintEvent` measures wall-clock rendering duration using Python's high-resolution monotonic timer `time.perf_counter()`:
```python
t_start = time.perf_counter()
# ... complete canvas rendering operations (network geometry, approach queues, vehicles, signals, HUD) ...
render_duration_ms = (time.perf_counter() - t_start) * 1000.0
```

### 2.2 Rolling Metrics Window
Frame duration and frame timestamps are maintained in circular deques:
- **`_frame_times` (`maxlen=60`)**: Tracks the execution duration (in milliseconds) of the last 60 paint events.
- **`_frame_timestamps` (`maxlen=60`)**: Tracks the wall-clock timestamps of recent paint completions.
- **`_total_frame_count`**: Monotonically increasing counter of total frames rendered.
- **`_fps_estimate`**: Computed as `(N - 1) / (t_newest - t_oldest)` over the circular timestamp buffer.
- **`avg_frame_ms` / `rolling_avg_ms`**: Mean render duration across the rolling window.

### 2.3 Public Instrumentation API
The canvas exposes a clean, non-mutating inspection method:
```python
canvas.get_rendering_performance_metrics() -> dict
```
Returning:
```json
{
  "last_frame_ms": 1.25,
  "avg_frame_ms": 1.18,
  "rolling_avg_ms": 1.18,
  "fps": 58.4,
  "total_frames": 240
}
```

---

## 3. Invariance and Engine Separation Guarantee
A critical constraint of TMS-Sim architecture is that visualization must never alter simulation state:
1. **Zero Side-Effects:** Metrics collection is isolated inside `RoadCanvas.paintEvent`.
2. **Decoupled Simulation Physics:** The simulation engine advances on its configured time step `dt` (e.g., 0.1 s) driven by the scenario schedule, completely independent of whether rendering occurs at 15 FPS, 60 FPS, or is skipped during headless runs.
3. **Automated Verification:** Verified by `test_canvas_rendering_never_mutates_simulation_engine` in `tests/test_ui_signal_visualization_and_zoom.py`, which asserts 100% bitwise engine state equality before and after heavy multi-zoom canvas rendering operations.

---

## 4. TC-PERF-01 Benchmark Execution Procedure

Run the approved reference fixture in the visible GUI at 1.0x playback speed:

```powershell
python measure_gui_fps.py --scenario fixtures/valid/performance_10_intersections.json --output artifacts/tc_perf_01_full_run.json
```

The run must reach the configured 3,600 simulated seconds. The acceptance FPS is
the average frames per second over the full benchmark interval, calculated as
`(total_frames - 1) / full_run_elapsed_seconds` between the first and last paint
events. `measure_gui_fps.py` resets the canvas counters immediately before the
run begins. Compare `full_run_fps` with the approved **15 FPS** target. The `fps` field
is a rolling-window estimate over the most recent 60 paint events; it is useful
diagnostic information and is not the acceptance value. Average render duration
and process RSS are also diagnostic measurements and do not create additional
pass criteria.

Record the exact scenario, seed, duration, generated vehicles, completion state,
crash/exception state, Python/platform, measured wall duration, full-run FPS, and
process memory. The fixture configures 500 vehicles/hour; the fixed seed yields
the realized demand count, which must be recorded rather than described as an
exact 500-vehicle realization.
