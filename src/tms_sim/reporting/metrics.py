"""Run metrics recomputed from the engine's lifecycle and measurement event logs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tms_sim.sim.engine import Engine


@dataclass(frozen=True)
class SimulationMetrics:
    """A metrics snapshot; unavailable values are ``None``, never fabricated zeroes."""

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


def compute_metrics(engine: Engine | None) -> SimulationMetrics:
    """Recompute metrics from immutable lifecycle events and per-step measurements.

    Travel time and delay include completed trips only. Delay is completed-trip time
    minus free-flow time for the same route (clamped at zero). Throughput is completed
    trips divided by elapsed simulated time, expressed per hour. Queue is the time
    average count of vehicles below 0.5 m/s, grouped by their current approach segment.
    Average speed is distance divided by vehicle-time across all simulated steps, so
    stopped vehicles contribute zero speed. Display/export rounds to one decimal; the
    stored values retain full floating-point precision. A quantity without a valid
    denominator or observation is unavailable (``None``); an observed zero is 0.
    """
    if engine is None:
        return SimulationMetrics("Ready", 0.0, 0.0, 0, 0, 0, 0, 0, None)

    status = "Completed" if engine.finished else (
        "Running" if engine.running else "Paused" if engine.time > 0 else "Ready"
    )
    total_scheduled = len(engine.vehicles)
    generated = total_scheduled if engine.finished else sum(
        vehicle.depart_time <= engine.time for vehicle in engine.vehicles
    )

    # The canonical log records spawn, exit, and step measurement events. Older or
    # test-double engines fall back to their lifecycle tuple events.
    log = getattr(engine, "metric_events", None)
    spawns: dict[int, tuple[float, float | None]] = {}
    exits: dict[int, tuple[float, float | None]] = {}
    samples: list[dict] = []
    if log is not None:
        for event in log:
            kind = event.get("type")
            vehicle_id = event.get("vehicle_id")
            if kind == "spawn" and vehicle_id not in spawns:
                spawns[vehicle_id] = (float(event["time"]), event.get("free_flow_time_s"))
            elif kind == "exit" and vehicle_id not in exits:
                exits[vehicle_id] = (float(event["time"]), event.get("free_flow_time_s"))
            elif kind == "sample":
                samples.append(event)
    else:
        for event in engine.events:
            t, vehicle_id, kind = event[:3]
            if kind == "spawn" and vehicle_id not in spawns:
                spawns[vehicle_id] = (float(t), None)
            elif kind == "exit" and vehicle_id not in exits:
                exits[vehicle_id] = (float(t), None)

    completed_ids = set(spawns).intersection(exits)
    trip_times = [exits[i][0] - spawns[i][0] for i in completed_ids]
    delays = [
        max(0.0, exits[i][0] - spawns[i][0] - float(spawns[i][1]))
        for i in completed_ids if spawns[i][1] is not None
    ]
    mean_travel = sum(trip_times) / len(trip_times) if trip_times else None
    mean_delay = sum(delays) / len(delays) if delays else None
    max_delay = max(delays) if delays else None
    throughput = (
        len(completed_ids) * 3600.0 / engine.time if engine.time > 0 else None
    )

    speed_distance = sum(float(sample.get("speed_distance_m", 0.0)) for sample in samples)
    vehicle_time = sum(float(sample.get("active_vehicle_time_s", 0.0)) for sample in samples)
    if samples:
        average_speed = speed_distance / vehicle_time if vehicle_time > 0 else None
    else:
        cars = getattr(engine, "cars", [])
        average_speed = sum(car.v for car in cars) / len(cars) if cars else None

    approach_ids = set(getattr(engine, "segs", {}))
    for sample in samples:
        approach_ids.update(sample.get("queue_by_approach", {}))
    queue_integrals = {approach: 0.0 for approach in approach_ids}
    queue_total = 0.0
    for sample in samples:
        dt = float(sample.get("dt", 0.0))
        queues = sample.get("queue_by_approach", {})
        for approach in approach_ids:
            count = float(queues.get(approach, 0))
            queue_integrals[approach] += count * dt
            queue_total += count * dt
    average_by_approach = (
        {key: value / engine.time for key, value in sorted(queue_integrals.items())}
        if engine.time > 0 and samples else {}
    )
    average_queue = queue_total / engine.time if engine.time > 0 and samples else None

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
