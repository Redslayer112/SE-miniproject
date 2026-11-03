
"""Simulation history and time-series sampling model (SAD §3.4, TMS-F-050, TMS-F-051).

Provides an authoritative, GUI-independent data collection model for live
performance charts, recording simulation metric samples and completed trip observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tms_sim.reporting.metrics import SimulationMetrics, compute_metrics

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

        # Incremental lifecycle event tracking
        self._processed_event_count = 0
        self._spawn_times: dict[int, float] = {}
        self._tracked_engine = None
        self._tracked_events = None

    def reset(self) -> None:
        """Clear all historical samples and completed-trip observations."""
        self.samples.clear()
        self.completed_trips.clear()
        self._last_sampled_time = None

        # Reset incremental event tracking
        self._processed_event_count = 0
        self._spawn_times.clear()
        self._tracked_engine = None
        self._tracked_events = None

    def record_state(
        self,
        engine: Engine | None,
        force: bool = False,
        metrics: SimulationMetrics | None = None,
    ) -> bool:
        """Record current engine state and completed trips.

        An optional metrics snapshot can be supplied to avoid recomputing
        metrics when the caller has already calculated them.

        Returns True if a new time-series sample was recorded, False otherwise.
        """
        if engine is None:
            return False

        # Update completed trips using newly appended lifecycle events only.
        self._sync_completed_trips(engine)

        current_time = float(engine.time)

        # Check if a new time-series sample should be recorded.
        should_sample = False

        if not self.samples:
            should_sample = True

        elif self._last_sampled_time is not None:
            if current_time > self._last_sampled_time:
                if force or engine.finished:
                    should_sample = True
                elif (
                    current_time - self._last_sampled_time
                ) >= self.min_sample_interval:
                    should_sample = True

            # If current_time <= _last_sampled_time, do NOT sample.
            # This prevents duplicate samples.

        if should_sample:
            # Reuse an existing metrics snapshot when available.
            snapshot = (
                metrics
                if metrics is not None
                else compute_metrics(engine)
            )

            sample = HistorySample(
                simulated_time=current_time,
                vehicles_generated=snapshot.vehicles_generated,
                vehicles_entered=snapshot.vehicles_entered,
                vehicles_completed=snapshot.vehicles_completed,
                vehicles_in_network=snapshot.vehicles_in_network,
            )

            self.samples.append(sample)
            self._last_sampled_time = current_time
            return True

        return False

    def _sync_completed_trips(self, engine: Engine) -> None:
        """Process only newly appended lifecycle events."""

        events = engine.events

        # Handle a new engine, replaced event list, or cleared event history.
        if (
            engine is not self._tracked_engine
            or events is not self._tracked_events
            or len(events) < self._processed_event_count
        ):
            self.completed_trips.clear()
            self._spawn_times.clear()
            self._processed_event_count = 0

            self._tracked_engine = engine
            self._tracked_events = events

        # Process only events that have not been handled yet.
        for event in events[self._processed_event_count:]:
            ev_time, veh_id, ev_type = event[0], event[1], event[2]

            if ev_type == "spawn":
                if veh_id not in self._spawn_times:
                    self._spawn_times[veh_id] = ev_time

            elif ev_type == "exit":
                spawn_time = self._spawn_times.get(veh_id)

                if spawn_time is not None:
                    self.completed_trips.append(
                        CompletedTrip(
                            vehicle_id=veh_id,
                            spawn_time=spawn_time,
                            completion_time=ev_time,
                            travel_time=ev_time - spawn_time,
                        )
                    )

        # Remember the number of events already processed.
        self._processed_event_count = len(events)