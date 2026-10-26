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

    status: str  # "Ready", "Running", "Paused", "Completed"
    simulated_time: float  # Current simulated time in seconds
    duration: float  # Configured total duration in seconds
    vehicles_generated: int  # Authoritative count of vehicles generated so far
    total_scheduled: int  # Total vehicles generated in scenario demand
    vehicles_entered: int  # Unique vehicles that entered the network
    vehicles_completed: int  # Unique vehicles that completed their journeys
    vehicles_in_network: int  # Active vehicles currently inside the network
    mean_travel_time: float | None  # Mean travel time (s) for completed trips; None if no completed trips
    # Unsupported / unmodeled metrics in current backend (TMS-F-050)
    throughput_vph: float | None = None
    average_delay_s: float | None = None
    queue_length_veh: float | None = None


def compute_metrics(engine: Engine | None) -> SimulationMetrics:
    """Compute authoritative metrics from the engine state and event log.

    Semantics:
    - Status: "Completed" if engine.finished; "Running" if engine.running;
      "Paused" if engine.time > 0 and not running; "Ready" if engine.time == 0.
    - Vehicles generated: Count of vehicles whose departure time has arrived
      (depart_time <= engine.time). When engine.finished, equals total_scheduled.
    - Vehicles entered: Count of unique vehicle IDs that spawned into the network.
      A vehicle is NOT counted as entered merely because it was generated.
    - Vehicles completed: Count of unique vehicle exit events.
    - Vehicles in network: Current active vehicles (len(engine.cars)).
    - Mean travel time: Average of (exit_time - spawn_time) for completed trips only.
      Incomplete trips are excluded. If zero completed trips, returns None.
    - Additional metrics (throughput, delay, queue lengths): None, as the current
      backend does not model queues or track delays.
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
        )

    # Status
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
        vehicles_generated = sum(1 for v in engine.vehicles if v.depart_time <= engine.time)

    spawns: dict[int, float] = {}
    exits: list[tuple[float, int]] = []
    for event in engine.events:
        # event: (time, vehicle_id, "spawn" | "exit", segment_id)
        ev_time, veh_id, ev_type = event[0], event[1], event[2]
        if ev_type == "spawn":
            if veh_id not in spawns:
                spawns[veh_id] = ev_time
        elif ev_type == "exit":
            exits.append((ev_time, veh_id))

    vehicles_entered = len(spawns)
    vehicles_completed = len(exits)
    vehicles_in_network = len(engine.cars)

    travel_times = [
        exit_time - spawns[veh_id]
        for exit_time, veh_id in exits
        if veh_id in spawns
    ]

    mean_travel_time: float | None = None
    if travel_times:
        mean_travel_time = sum(travel_times) / len(travel_times)

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
    )
