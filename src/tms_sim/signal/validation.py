"""Signal plan validation. Reports every defect; errors block a plan, warnings do not.

Uses the issue structure from the network package so both validators report alike.
"""
from __future__ import annotations

import math
from collections import Counter
from itertools import combinations

from tms_sim.network import ControlType, Network, ValidationIssue, ValidationResult
from tms_sim.network.validation import ERROR, WARNING

from .conflicts import ConflictCheckUnavailable, movements_conflict
from .model import SignalPlan


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _valid_order(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def validate_signal_plan(plan: SignalPlan, network: Network) -> ValidationResult:
    issues: list[ValidationIssue] = []
    iid = plan.intersection_id

    def add(code, message, etype, eid, severity=ERROR):
        issues.append(ValidationIssue(code, message, etype, eid, severity))

    inter = next((i for i in network.intersections if i.id == iid), None)
    if inter is None:
        add("UNKNOWN_INTERSECTION", f"plan references unknown intersection '{iid}'", "signal_plan", iid)
    elif inter.control_type != ControlType.SIGNALIZED:
        add("NOT_SIGNALIZED", f"intersection '{iid}' is not signalized", "signal_plan", iid)

    if not plan.phases:
        add("NO_PHASES", f"plan for '{iid}' has no phases", "signal_plan", iid)

    for order, n in Counter(p.order for p in plan.phases if _valid_order(p.order)).items():
        if n > 1:
            add("DUPLICATE_PHASE_ORDER", f"plan for '{iid}' uses phase order {order} {n} times",
                "signal_phase", f"{iid}:{order}")

    moves = {m.id: m for m in network.turning_movements}
    served: set[str] = set()
    unavailable: set[str] = set()

    for p in plan.phases:
        pid = f"{iid}:{p.order}"
        if not _valid_order(p.order):
            add("INVALID_PHASE_ORDER", f"phase order {p.order!r} must be an integer greater than 0",
                "signal_phase", pid)
        if not p.movement_ids:
            add("EMPTY_PHASE", f"phase {p.order} of '{iid}' has no movements", "signal_phase", pid)

        for mid, n in Counter(p.movement_ids).items():
            if n > 1:
                add("DUPLICATE_MOVEMENT_IN_PHASE",
                    f"movement '{mid}' is listed {n} times in phase {p.order} of '{iid}'", "signal_phase", pid)

        usable = []
        for mid in dict.fromkeys(p.movement_ids):
            m = moves.get(mid)
            if m is None:
                add("UNKNOWN_MOVEMENT", f"phase {p.order} of '{iid}' references unknown movement '{mid}'",
                    "turning_movement", mid)
            elif m.intersection != iid:
                add("MOVEMENT_WRONG_INTERSECTION",
                    f"movement '{mid}' in phase {p.order} belongs to '{m.intersection}', not '{iid}'",
                    "turning_movement", mid)
            else:
                usable.append(m)
                served.add(mid)

        for name, value, ok, rule in (
                ("green_s", p.green_s, _finite(p.green_s) and p.green_s > 0, "a finite number greater than 0"),
                ("yellow_s", p.yellow_s, _finite(p.yellow_s) and p.yellow_s >= 0, "a finite number of 0 or more"),
                ("all_red_s", p.all_red_s, _finite(p.all_red_s) and p.all_red_s >= 0, "a finite number of 0 or more")):
            if not ok:
                add(f"INVALID_{name[:-2].upper()}",
                    f"phase {p.order} of '{iid}': {name} must be {rule}, got {value!r}", "signal_phase", pid)

        for a, b in combinations(usable, 2):
            try:
                if movements_conflict(network, a, b):
                    add("CONFLICTING_MOVEMENTS",
                        f"movements '{a.id}' and '{b.id}' conflict in phase {p.order} of '{iid}'",
                        "signal_phase", pid)
            except ConflictCheckUnavailable as e:
                unavailable.add(str(e))

    if unavailable:
        add("CONFLICT_CHECK_UNAVAILABLE",
            f"conflict check cannot run for plan '{iid}': {'; '.join(sorted(unavailable))}", "signal_plan", iid)

    for m in network.turning_movements:
        if m.intersection == iid and m.id not in served:
            add("UNSERVED_MOVEMENT", f"movement '{m.id}' is not served by any phase of '{iid}'",
                "turning_movement", m.id, WARNING)

    return ValidationResult(issues)
