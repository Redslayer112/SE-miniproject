"""Simulation run metrics computation (SAD §3.4, TMS-F-050, TMS-F-051).

This module provides authoritative recomputation of simulation metrics directly
from the simulation engine state and event log.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tms_sim.sim.engine import Engine


@dataclass(frozen=True)
class SimulationMetrics:
    """Snapshot of simulation metrics at a point in time or at completion."""

    status: str
    simulated_time: float
    duration: float
    vehicles_generated: int
    total_scheduled: int
    vehicles_entered: int
    vehicles_completed: int
    vehicles_in_network: int
    mean_travel_time: float | None

    # Mean instantaneous speed of active vehicles, in metres per second.
    average_speed_mps: float | None = None

    # Metrics not yet fully modeled by the current backend.
    throughput_vph: float | None = None
    average_delay_s: float | None = None
    queue_length_veh: float | None = None


def compute_metrics(engine: Engine | None) -> SimulationMetrics:
    """Compute authoritative metrics from engine state and event log.

    Semantics:
    - Status is Completed, Running, Paused, or Ready.
    - Vehicles generated counts demand with departure time <= current time.
    - Vehicles entered counts unique vehicle IDs with spawn events.
    - Vehicles completed counts unique vehicle IDs with exit events.
    - Vehicles in network counts currently active cars.
    - Mean travel time averages completed trips only.
    - Average speed averages instantaneous speeds of currently active cars.
      It is None when no vehicles are active.
    - Throughput, delay, and queue length remain unavailable until modeled.
    """
    if engine is None:
        return SimulationMetrics(
            status="Ready",
            simulated_time=0.0,
            duration=0.0,
            vehicles_generated=0,
            total_scheduled=0,
            vehicles_entered=0,
            vehicles_completed=0,
            vehicles_in_network=0,
            mean_travel_time=None,
            average_speed_mps=None,
        )

    # Determine simulation status.
    if engine.finished:
        status = "Completed"
    elif engine.running:
        status = "Running"
    elif engine.time > 0.0:
        status = "Paused"
    else:
        status = "Ready"

    total_scheduled = len(engine.vehicles)

    if engine.finished:
        vehicles_generated = total_scheduled
    else:
        vehicles_generated = sum(
            1 for vehicle in engine.vehicles
            if vehicle.depart_time <= engine.time
        )

    # Recompute counts and trip durations from the event log.
    spawns: dict[int, float] = {}
    exited_ids: set[int] = set()

    for event in engine.events:
        # Event format: (time, vehicle_id, "spawn" | "exit", segment_id)
        event_time, vehicle_id, event_type = (
            event[0],
            event[1],
            event[2],
        )

        if event_type == "spawn":
            if vehicle_id not in spawns:
                spawns[vehicle_id] = event_time
        elif event_type == "exit":
            exited_ids.add(vehicle_id)

    travel_times = [
        event[0] - spawns[event[1]]
        for event in engine.events
        if event[2] == "exit" and event[1] in spawns
    ]

    vehicles_entered = len(spawns)
    vehicles_completed = len(exited_ids)
    vehicles_in_network = len(engine.cars)

    mean_travel_time = (
        sum(travel_times) / len(travel_times)
        if travel_times
        else None
    )

    # Average instantaneous speed of active vehicles, in m/s.
    average_speed_mps = (
        sum(car.v for car in engine.cars) / len(engine.cars)
        if engine.cars
        else None
    )

    return SimulationMetrics(
        status=status,
        simulated_time=engine.time,
        duration=engine.duration,
        vehicles_generated=vehicles_generated,
        total_scheduled=total_scheduled,
        vehicles_entered=vehicles_entered,
        vehicles_completed=vehicles_completed,
        vehicles_in_network=vehicles_in_network,
        mean_travel_time=mean_travel_time,
        average_speed_mps=average_speed_mps,
    )
