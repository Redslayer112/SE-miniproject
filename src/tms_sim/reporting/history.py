"""Simulation history and time-series sampling model (SAD §3.4, TMS-F-050, TMS-F-051).

Provides an authoritative, GUI-independent data collection model for live
performance charts, recording simulation metric samples and completed trip observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tms_sim.reporting.metrics import compute_metrics

if TYPE_CHECKING:
    from tms_sim.sim.engine import Engine


@dataclass(frozen=True)
class HistorySample:
    """Snapshot of simulation vehicle counts at a specific simulated time."""

    simulated_time: float
    vehicles_generated: int
    vehicles_entered: int
    vehicles_completed: int
    vehicles_in_network: int


@dataclass(frozen=True)
class CompletedTrip:
    """Individual observation of a vehicle that completed its trip."""

    vehicle_id: int
    spawn_time: float
    completion_time: float
    travel_time: float


class SimulationHistoryTracker:
    """Tracks time-series history samples and completed trips across a simulation run.

    Requirements:
    - Driven by simulation time, not wall-clock time.
    - Avoids duplicate samples when simulation time has not advanced.
    - Samples at a configurable simulated-time interval (default: 1.0s) while
      always capturing manual single-steps and run completion.
    - Captures actual observed states without fabricating intermediate points.
    - Excludes incomplete trips from completed-trip travel-time observations.
    """

    def __init__(self, min_sample_interval: float = 1.0):
        self.min_sample_interval = float(min_sample_interval)
        self.samples: list[HistorySample] = []
        self.completed_trips: list[CompletedTrip] = []
        self._last_sampled_time: float | None = None

    def reset(self) -> None:
        """Clear all historical samples and completed-trip observations."""
        self.samples.clear()
        self.completed_trips.clear()
        self._last_sampled_time = None

    def record_state(self, engine: Engine | None, force: bool = False) -> bool:
        """Record current engine state and completed trips.

        Returns True if a new time-series sample was recorded, False otherwise.
        """
        if engine is None:
            return False

        # 1. Update completed trips from authoritative engine events
        self._sync_completed_trips(engine)

        current_time = float(engine.time)

        # 2. Check if a new time-series sample should be recorded
        should_sample = False
        if not self.samples:
            should_sample = True
        elif self._last_sampled_time is not None:
            if current_time > self._last_sampled_time:
                if force or engine.finished:
                    should_sample = True
                elif (current_time - self._last_sampled_time) >= self.min_sample_interval:
                    should_sample = True
            # If current_time <= _last_sampled_time, do NOT sample (prevents duplicates)

        if should_sample:
            metrics = compute_metrics(engine)
            sample = HistorySample(
                simulated_time=current_time,
                vehicles_generated=metrics.vehicles_generated,
                vehicles_entered=metrics.vehicles_entered,
                vehicles_completed=metrics.vehicles_completed,
                vehicles_in_network=metrics.vehicles_in_network,
            )
            self.samples.append(sample)
            self._last_sampled_time = current_time
            return True

        return False

    def _sync_completed_trips(self, engine: Engine) -> None:
        """Extract completed trips directly from engine events log."""
        spawns: dict[int, float] = {}
        exits: list[tuple[float, int]] = []
        for event in engine.events:
            ev_time, veh_id, ev_type = event[0], event[1], event[2]
            if ev_type == "spawn":
                if veh_id not in spawns:
                    spawns[veh_id] = ev_time
            elif ev_type == "exit":
                exits.append((ev_time, veh_id))

        if len(exits) != len(self.completed_trips):
            self.completed_trips = [
                CompletedTrip(
                    vehicle_id=veh_id,
                    spawn_time=spawns[veh_id],
                    completion_time=exit_time,
                    travel_time=exit_time - spawns[veh_id],
                )
                for exit_time, veh_id in exits
                if veh_id in spawns
            ]
