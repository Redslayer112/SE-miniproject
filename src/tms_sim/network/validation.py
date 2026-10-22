"""Network validation. Reports every defect; errors block a run, warnings do not."""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from .model import Network

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    element_type: str
    element_id: str
    severity: str = ERROR


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == WARNING]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _positive_finite(v) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v) and v > 0


def _has_lane(seg) -> bool:
    return isinstance(seg.lane_count, int) and seg.lane_count > 0


def validate(network: Network) -> ValidationResult:
    issues: list[ValidationIssue] = []

    def add(code, message, etype, eid, severity=ERROR):
        issues.append(ValidationIssue(code, message, etype, eid, severity))

    for etype, items in (("intersection", network.intersections),
                         ("segment", network.segments),
                         ("turning_movement", network.turning_movements)):
        for eid, n in Counter(i.id for i in items).items():
            if n > 1:
                add("DUPLICATE_ID", f"{etype} id '{eid}' is used {n} times", etype, eid)

    inter_ids = {i.id for i in network.intersections}
    seg_by_id = {s.id: s for s in network.segments}

    for s in network.segments:
        for end in (s.from_intersection, s.to_intersection):
            if end not in inter_ids:
                add("UNKNOWN_INTERSECTION", f"segment '{s.id}' references unknown intersection '{end}'", "segment", s.id)
        if s.from_intersection == s.to_intersection:
            add("SELF_LOOP", f"segment '{s.id}' starts and ends at '{s.from_intersection}'", "segment", s.id)
        if s.length_m == 0:
            add("ZERO_LENGTH", f"segment '{s.id}' has zero length", "segment", s.id)
        elif not _positive_finite(s.length_m):
            add("INVALID_LENGTH", f"segment '{s.id}' has invalid length {s.length_m!r}", "segment", s.id)
        if s.lane_count == 0:
            add("ZERO_LANES", f"segment '{s.id}' has zero lanes", "segment", s.id)
        elif not _has_lane(s):
            add("INVALID_LANE_COUNT", f"segment '{s.id}' has invalid lane count {s.lane_count!r}", "segment", s.id)
        if s.speed_limit_mps is None:
            add("MISSING_SPEED_LIMIT", f"segment '{s.id}' has no speed limit", "segment", s.id)
        elif not _positive_finite(s.speed_limit_mps):
            add("INVALID_SPEED_LIMIT", f"segment '{s.id}' has invalid speed limit {s.speed_limit_mps!r}", "segment", s.id)

    for m in network.turning_movements:
        if m.intersection not in inter_ids:
            add("UNKNOWN_INTERSECTION", f"movement '{m.id}' references unknown intersection '{m.intersection}'", "turning_movement", m.id)
        src, dst = seg_by_id.get(m.from_segment), seg_by_id.get(m.to_segment)
        for ref, seg in ((m.from_segment, src), (m.to_segment, dst)):
            if seg is None:
                add("UNKNOWN_SEGMENT", f"movement '{m.id}' references unknown segment '{ref}'", "turning_movement", m.id)
        if src and src.to_intersection != m.intersection:
            add("MOVEMENT_NOT_AT_INTERSECTION", f"approach '{src.id}' of movement '{m.id}' does not end at '{m.intersection}'", "turning_movement", m.id)
        if dst and dst.from_intersection != m.intersection:
            add("MOVEMENT_NOT_AT_INTERSECTION", f"receiving segment '{dst.id}' of movement '{m.id}' does not start at '{m.intersection}'", "turning_movement", m.id)
        if dst and not _has_lane(dst):
            add("NO_RECEIVING_LANE", f"movement '{m.id}' leads onto segment '{dst.id}' which has no lane", "turning_movement", m.id)

    _check_connectivity(network, inter_ids, add)

    with_movement = {m.from_segment for m in network.turning_movements}
    for s in network.segments:
        if s.to_intersection in inter_ids and s.id not in with_movement:
            add("APPROACH_WITHOUT_MOVEMENT", f"approach '{s.id}' has no turning movement", "segment", s.id, WARNING)

    return ValidationResult(issues)


def _check_connectivity(network, inter_ids, add):
    """Weak connectivity: each intersection outside the largest component is an error."""
    parent = {i: i for i in inter_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for s in network.segments:
        if s.from_intersection in parent and s.to_intersection in parent:
            parent[find(s.from_intersection)] = find(s.to_intersection)

    sizes = Counter(find(i) for i in parent)
    if len(sizes) <= 1:
        return
    # Ties: pick the component holding the earliest-declared intersection (deterministic).
    order = [find(i.id) for i in network.intersections if i.id in parent]
    main = max(sizes, key=lambda r: (sizes[r], -order.index(r)))
    for i in network.intersections:
        if i.id in parent and find(i.id) != main:
            add("DISCONNECTED_GRAPH", f"intersection '{i.id}' is not connected to the main network", "intersection", i.id)
