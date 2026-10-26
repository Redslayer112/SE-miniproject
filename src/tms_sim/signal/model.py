"""Fixed-time signal plan model. Plain values only; validation lives in validation.py.

Plans are frozen so a validated plan cannot be changed after it was accepted.
Lists passed in are stored as tuples.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalPhase:
    """One phase: the movements that get green together, and its timing in seconds."""
    order: int
    movement_ids: tuple[str, ...]
    green_s: float
    yellow_s: float
    all_red_s: float

    def __post_init__(self):
        if isinstance(self.movement_ids, list):
            object.__setattr__(self, "movement_ids", tuple(self.movement_ids))

    @property
    def duration_s(self) -> float:
        return self.green_s + self.yellow_s + self.all_red_s


@dataclass(frozen=True)
class SignalPlan:
    """Ordered phases for one signalized intersection."""
    intersection_id: str
    phases: tuple[SignalPhase, ...] = ()

    def __post_init__(self):
        if isinstance(self.phases, list):
            object.__setattr__(self, "phases", tuple(self.phases))

    @property
    def cycle_time_s(self) -> float:
        """Sum of all phase durations. Only meaningful for a plan that passed validation."""
        return sum(p.duration_s for p in self.phases)

    def movement_state(self, movement_id: str, t: float) -> str:
        """Return the signal indication ('GREEN', 'YELLOW', or 'RED') for movement_id at time t."""
        cycle = self.cycle_time_s
        if cycle <= 0:
            return "RED"
        t_mod = t % cycle
        start = 0.0
        active_state = "RED"
        for ph in sorted(self.phases, key=lambda p: p.order):
            if movement_id in ph.movement_ids:
                green_end = start + ph.green_s
                yellow_end = green_end + ph.yellow_s
                if start <= t_mod < green_end:
                    return "GREEN"
                elif green_end <= t_mod < yellow_end:
                    active_state = "YELLOW"
            start += ph.duration_s
        return active_state

    def intersection_state(self, t: float) -> str:
        """Return the active indication ('GREEN', 'YELLOW', or 'RED') for the intersection at time t."""
        cycle = self.cycle_time_s
        if cycle <= 0:
            return "RED"
        t_mod = t % cycle
        start = 0.0
        active_state = "RED"
        for ph in sorted(self.phases, key=lambda p: p.order):
            green_end = start + ph.green_s
            yellow_end = green_end + ph.yellow_s
            if start <= t_mod < green_end:
                return "GREEN"
            elif green_end <= t_mod < yellow_end:
                active_state = "YELLOW"
            start += ph.duration_s
        return active_state
