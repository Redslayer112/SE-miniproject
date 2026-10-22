"""Conflict rule for two movements at one intersection (proposal for issue #1, item 9).

Two movements conflict when their paths cross or merge inside the intersection,
unless they start from the same approach segment:

* same from_segment: no conflict (they share the approach and split inside it);
* same to_segment: conflict (merge);
* otherwise geometry decides. Each movement is a chord on a circle around the
  intersection centre. A road to a neighbour at bearing phi from the centre is
  entered at angle phi - side*delta and left at angle phi + side*delta. Two chords
  conflict when their endpoints interleave around the circle.

Positions use y-up axes (bearing = atan2(dy, dx)). Chords that share an endpoint
angle are not treated as interleaved. If a position needed for the geometry is
missing, ConflictCheckUnavailable is raised instead of guessing.
"""
from __future__ import annotations

import math

from tms_sim.network import Network, TurningMovement

DRIVE_SIDE = "left"  # "left" or "right"; a wrong value fails at import
_SIDE = {"left": 1, "right": -1}[DRIVE_SIDE]
_DELTA = math.radians(10)
_TAU = 2 * math.pi


class ConflictCheckUnavailable(Exception):
    """The geometry needed to decide a conflict is missing."""


def movements_conflict(network: Network, a: TurningMovement, b: TurningMovement) -> bool:
    if a.from_segment == b.from_segment:
        return False
    if a.to_segment == b.to_segment:
        return True
    segments = {s.id: s for s in network.segments}
    positions = {i.id: i.position for i in network.intersections}
    return _interleave(_chord(a, segments, positions), _chord(b, segments, positions))


def _chord(m, segments, positions):
    src, dst = segments.get(m.from_segment), segments.get(m.to_segment)
    if src is None or dst is None:
        raise ConflictCheckUnavailable(f"movement '{m.id}' uses an unknown segment")
    enter = _bearing(positions, m.intersection, src.from_intersection) - _SIDE * _DELTA
    leave = _bearing(positions, m.intersection, dst.to_intersection) + _SIDE * _DELTA
    return enter, leave


def _bearing(positions, center_id, other_id):
    center, other = positions.get(center_id), positions.get(other_id)
    missing = [i for i, p in ((center_id, center), (other_id, other)) if p is None]
    if missing:
        raise ConflictCheckUnavailable(f"no position for intersection {', '.join(sorted(set(missing)))}")
    if center == other:
        raise ConflictCheckUnavailable(f"intersections '{center_id}' and '{other_id}' share a position")
    return math.atan2(other[1] - center[1], other[0] - center[0])


def _interleave(a, b):
    lo, hi = sorted(x % _TAU for x in a)
    return sum(lo < x % _TAU < hi for x in b) == 1
