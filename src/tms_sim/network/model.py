"""Road-network data model. Plain values only; validation lives in validation.py."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ControlType(str, Enum):
    SIGNALIZED = "signalized"
    STOP_CONTROLLED = "stop_controlled"
    YIELD_CONTROLLED = "yield_controlled"
    UNCONTROLLED = "uncontrolled"


@dataclass
class Intersection:
    id: str
    position: tuple[float, float] | None = None
    control_type: ControlType = ControlType.UNCONTROLLED


@dataclass
class Segment:
    """Directed road segment from one intersection to another."""
    id: str
    from_intersection: str
    to_intersection: str
    length_m: float
    lane_count: int
    speed_limit_mps: float | None = None


@dataclass
class TurningMovement:
    """Permitted movement from an approach segment onto a receiving segment."""
    id: str
    intersection: str
    from_segment: str
    to_segment: str


@dataclass
class Network:
    # Lists (not dicts) so duplicate ids survive loading and get reported.
    intersections: list[Intersection] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    turning_movements: list[TurningMovement] = field(default_factory=list)
