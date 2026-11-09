"""Run metrics recomputed from the engine's lifecycle and measurement event logs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tms_sim.sim.engine import Engine


@dataclass(frozen=True)
class SimulationMetrics:
    """A snapshot of simulation metrics."""

    status: str
    simulated_time: float
    duration: float
    vehicles_generated: int
    total_scheduled: int
    vehicles_entered: int
    vehicles_completed: int
    vehicles_in_network: int
    mean_travel_time: float | None
    average_speed_mps: float | None = None
    throughput_vph: float | None = None
    average_delay_s: float | None = None
    maximum_delay_s: float | None = None
    queue_length_veh: float | None = None
    average_queue_length_by_approach: dict[str, float] = field(default_factory=dict)


def _optional_float(value: Any) -> float | None:
    """Convert a numeric event value to float while preserving missing values."""
    if isinstance(value, (int, float)):
        return float(value)
    return None


def compute_metrics(engine: Engine | None) -> SimulationMetrics:
    """Independently recompute metrics from the engine's event logs."""
    if engine is None:
        return SimulationMetrics("Ready", 0.0, 0.0, 0, 0, 0, 0, 0, None)

    status = "Completed" if engine.finished else (
        "Running" if engine.running else "Paused" if engine.time > 0 else "Ready"
    )
    total_scheduled = len(engine.vehicles)
    generated = total_scheduled if engine.finished else sum(
        vehicle.depart_time <= engine.time for vehicle in engine.vehicles
    )

    metric_events = getattr(engine, "metric_events", None)
    spawns: dict[int, tuple[float, float | None]] = {}
    exits: dict[int, tuple[float, float | None]] = {}
    samples: list[dict[str, Any]] = []

    if metric_events is not None:
        for event in metric_events:
            kind = event.get("type")
            vehicle_id_value = event.get("vehicle_id")

            if kind == "sample":
                samples.append(event)
            elif kind in ("spawn", "exit") and isinstance(vehicle_id_value, int):
                event_time = float(event["time"])
                free_flow_time = _optional_float(event.get("free_flow_time_s"))
                if kind == "spawn" and vehicle_id_value not in spawns:
                    spawns[vehicle_id_value] = (event_time, free_flow_time)
                elif kind == "exit" and vehicle_id_value not in exits:
                    exits[vehicle_id_value] = (event_time, free_flow_time)
    else:
        for event in engine.events:
            event_time, vehicle_id, kind = event[:3]
            if not isinstance(vehicle_id, int):
                continue
            if kind == "spawn" and vehicle_id not in spawns:
                spawns[vehicle_id] = (float(event_time), None)
            elif kind == "exit" and vehicle_id not in exits:
                exits[vehicle_id] = (float(event_time), None)

    completed_ids = set(spawns).intersection(exits)
    trip_times = [
        exits[vehicle_id][0] - spawns[vehicle_id][0]
        for vehicle_id in completed_ids
    ]

    delays: list[float] = []
    for vehicle_id in completed_ids:
        spawn_time, free_flow_time = spawns[vehicle_id]
        if free_flow_time is not None:
            delays.append(max(0.0, exits[vehicle_id][0] - spawn_time - free_flow_time))

    mean_travel = sum(trip_times) / len(trip_times) if trip_times else None
    mean_delay = sum(delays) / len(delays) if delays else None
    max_delay = max(delays) if delays else None
    throughput = (
        len(completed_ids) * 3600.0 / engine.time if engine.time > 0 else None
    )

    speed_distance = sum(
        float(sample.get("speed_distance_m", 0.0)) for sample in samples
    )
    vehicle_time = sum(
        float(sample.get("active_vehicle_time_s", 0.0)) for sample in samples
    )
    average_speed = speed_distance / vehicle_time if vehicle_time > 0 else None

    approach_ids = set(getattr(engine, "segs", {}))
    for sample in samples:
        approach_ids.update(sample.get("queue_by_approach", {}))

    queue_integrals: dict[str, float] = {
        approach: 0.0 for approach in approach_ids
    }
    queue_total = 0.0
    for sample in samples:
        dt = float(sample.get("dt", 0.0))
        queues = sample.get("queue_by_approach", {})
        for approach in approach_ids:
            count = float(queues.get(approach, 0))
            queue_integrals[approach] += count * dt
            queue_total += count * dt

    average_by_approach = (
        {
            key: value / engine.time
            for key, value in sorted(queue_integrals.items())
        }
        if engine.time > 0 and samples else {}
    )
    average_queue = (
        queue_total / engine.time if engine.time > 0 and samples else None
    )

    return SimulationMetrics(
        status=status,
        simulated_time=engine.time,
        duration=engine.duration,
        vehicles_generated=generated,
        total_scheduled=total_scheduled,
        vehicles_entered=len(spawns),
        vehicles_completed=len(completed_ids),
        vehicles_in_network=len(engine.cars),
        mean_travel_time=mean_travel,
        average_speed_mps=average_speed,
        throughput_vph=throughput,
        average_delay_s=mean_delay,
        maximum_delay_s=max_delay,
        queue_length_veh=average_queue,
        average_queue_length_by_approach=average_by_approach,
    )


class IncrementalMetricsCalculator:
    """Incrementally aggregate an engine's append-only metric event log."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Discard all cached state."""
        self._engine: Engine | None = None
        self._event_log: list[dict[str, Any]] | None = None
        self._processed_event_count = 0
        self._spawns: dict[int, tuple[float, float | None]] = {}
        self._exits: dict[int, tuple[float, float | None]] = {}
        self._completed_ids: set[int] = set()
        self._trip_time_total = 0.0
        self._delay_total = 0.0
        self._delay_count = 0
        self._maximum_delay: float | None = None
        self._speed_distance = 0.0
        self._vehicle_time = 0.0
        self._sample_count = 0
        self._queue_integrals: dict[str, float] = {}

    def calculate(self, engine: Engine | None) -> SimulationMetrics:
        """Return current metrics, processing only events not seen previously."""
        if engine is None:
            self.reset()
            return compute_metrics(None)

        metric_events = getattr(engine, "metric_events", None)
        if metric_events is None:
            self.reset()
            return compute_metrics(engine)

        if (
            engine is not self._engine
            or metric_events is not self._event_log
            or len(metric_events) < self._processed_event_count
        ):
            self.reset()
            self._engine = engine
            self._event_log = metric_events

        for event in metric_events[self._processed_event_count:]:
            self._process_event(event)
        self._processed_event_count = len(metric_events)

        status = "Completed" if engine.finished else (
            "Running" if engine.running else "Paused" if engine.time > 0 else "Ready"
        )
        total_scheduled = len(engine.vehicles)
        generated = total_scheduled if engine.finished else sum(
            vehicle.depart_time <= engine.time for vehicle in engine.vehicles
        )

        completed_count = len(self._completed_ids)
        mean_travel = (
            self._trip_time_total / completed_count if completed_count else None
        )
        mean_delay = (
            self._delay_total / self._delay_count if self._delay_count else None
        )
        throughput = (
            completed_count * 3600.0 / engine.time if engine.time > 0 else None
        )

        average_speed = (
            self._speed_distance / self._vehicle_time
            if self._vehicle_time > 0 else None
        )

        approach_ids = set(getattr(engine, "segs", {}))
        approach_ids.update(self._queue_integrals)
        average_by_approach = (
            {
                key: self._queue_integrals.get(key, 0.0) / engine.time
                for key in sorted(approach_ids)
            }
            if engine.time > 0 and self._sample_count else {}
        )
        average_queue = (
            sum(self._queue_integrals.values()) / engine.time
            if engine.time > 0 and self._sample_count else None
        )

        return SimulationMetrics(
            status=status,
            simulated_time=engine.time,
            duration=engine.duration,
            vehicles_generated=generated,
            total_scheduled=total_scheduled,
            vehicles_entered=len(self._spawns),
            vehicles_completed=completed_count,
            vehicles_in_network=len(engine.cars),
            mean_travel_time=mean_travel,
            average_speed_mps=average_speed,
            throughput_vph=throughput,
            average_delay_s=mean_delay,
            maximum_delay_s=self._maximum_delay,
            queue_length_veh=average_queue,
            average_queue_length_by_approach=average_by_approach,
        )

    def _process_event(self, event: dict[str, Any]) -> None:
        """Fold one new lifecycle or measurement event into cached totals."""
        kind = event.get("type")

        if kind == "sample":
            self._sample_count += 1
            self._speed_distance += float(event.get("speed_distance_m", 0.0))
            self._vehicle_time += float(event.get("active_vehicle_time_s", 0.0))
            dt = float(event.get("dt", 0.0))
            queue_data = event.get("queue_by_approach", {})
            if isinstance(queue_data, dict):
                for approach, count in queue_data.items():
                    self._queue_integrals[approach] = (
                        self._queue_integrals.get(approach, 0.0)
                        + float(count) * dt
                    )
            return

        if kind not in ("spawn", "exit"):
            return

        vehicle_id_value = event.get("vehicle_id")
        if not isinstance(vehicle_id_value, int):
            return
        vehicle_id = vehicle_id_value
        event_time = float(event["time"])
        free_flow_time = _optional_float(event.get("free_flow_time_s"))

        if kind == "spawn":
            if vehicle_id not in self._spawns:
                self._spawns[vehicle_id] = (event_time, free_flow_time)
                self._try_add_completed_trip(vehicle_id)
        elif vehicle_id not in self._exits:
            self._exits[vehicle_id] = (event_time, free_flow_time)
            self._try_add_completed_trip(vehicle_id)

    def _try_add_completed_trip(self, vehicle_id: int) -> None:
        """Add a completed trip once both its first spawn and first exit exist."""
        if (
            vehicle_id in self._completed_ids
            or vehicle_id not in self._spawns
            or vehicle_id not in self._exits
        ):
            return

        self._completed_ids.add(vehicle_id)
        spawn_time, free_flow_time = self._spawns[vehicle_id]
        exit_time, _ = self._exits[vehicle_id]
        self._trip_time_total += exit_time - spawn_time

        if free_flow_time is not None:
            delay = max(0.0, exit_time - spawn_time - free_flow_time)
            self._delay_total += delay
            self._delay_count += 1
            if self._maximum_delay is None or delay > self._maximum_delay:
                self._maximum_delay = delay
