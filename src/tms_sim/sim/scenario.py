"""Run Simulation flow (SAD §4.2): validate network (#3) and signal plans (#5), generate demand (#6),
build the Engine (#7).

Scenario JSON is the shared fixture format (fixtures/valid/small_valid_scenario.json):
  network, signal_plan (one) or signal_plans (list), demand.arrival_rates_vehicles_per_hour
  {entry segment: veh/h}, demand.turning_ratios {movement id: ratio}, simulation {seed, duration_s, time_step_s}.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from tms_sim.network import ControlType, Network, NetworkService
from tms_sim.network.validation import ERROR, WARNING, ValidationIssue, ValidationResult
from tms_sim.network.serialization import network_from_dict
from tms_sim.signal import ConflictCheckUnavailable, SignalPlan, SignalService, movements_conflict
from tms_sim.signal.serialization import plan_from_dict
from tms_sim.sim.demand import DemandError, demand_issues, generate_vehicles
from tms_sim.sim.engine import Engine, Params, Segment

YIELDING = {ControlType.STOP_CONTROLLED, ControlType.YIELD_CONTROLLED}


def phase_green(plan: SignalPlan, movement_id: str):
    """green(t) for one movement under a fixed-time plan. Only green_s counts as green;
    yellow and all-red are treated as red (vehicles do not start on yellow)."""
    cycle, windows, start = plan.cycle_time_s, [], 0.0
    for ph in sorted(plan.phases, key=lambda p: p.order):
        if movement_id in ph.movement_ids:
            windows.append((start, start + ph.green_s))
        start += ph.duration_s
    return lambda t: any(a <= t % cycle < b for a, b in windows)


def _route(first, outgoing):
    """Entry segment, then the demand's movement, then (ponytail) the lowest-id movement at every
    later intersection until a segment with no way out. Per-approach ratios would replace this."""
    route, seg = [first.from_segment, first.to_segment], first.to_segment
    while outgoing.get(seg) and len(route) <= 100:
        nxt = min(outgoing[seg], key=lambda m: m.id).to_segment
        if nxt in route:  # loop: leave the network here
            break
        route.append(nxt)
        seg = nxt
    return route


def _real(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate_scenario(network: Network, demand: dict, simulation: dict) -> ValidationResult:
    """Scenario-level checks (SRS §4.4 schema, baseline amendment v1.1), every problem at once.

    A network entry is a segment no permitted turning movement leads onto; demand on any other
    segment is only a warning, because nothing in the baseline makes it blocking.
    """
    issues: list[ValidationIssue] = []

    def add(code, message, etype, eid, severity=ERROR):
        issues.append(ValidationIssue(code, message, etype, eid, severity))

    dt = simulation.get("time_step_s", Params.dt)
    if not _real(dt) or not 0.1 <= dt <= 1.0:
        add("INVALID_TIME_STEP", f"time_step_s must be 0.1-1.0 s (TMS-F-040), got {dt!r}", "simulation", "time_step_s")
    duration = simulation.get("duration_s", 3600.0)
    if not _real(duration) or duration <= 0:
        add("INVALID_DURATION", f"duration_s must be > 0 s, got {duration!r}", "simulation", "duration_s")
    seed = simulation.get("seed", 0)
    if not isinstance(seed, int) or isinstance(seed, bool):
        add("INVALID_SEED", f"seed must be an integer, got {seed!r}", "simulation", "seed")

    rates = demand.get("arrival_rates_vehicles_per_hour", {})
    raw_ratios = demand.get("turning_ratios", {})
    if not isinstance(rates, dict) or not isinstance(raw_ratios, dict):
        add("INVALID_DEMAND", "arrival rates and turning ratios must be objects", "demand", "")
        return ValidationResult(issues)

    seg_ids = {s.id for s in network.segments}
    fed = {m.to_segment for m in network.turning_movements}
    for entry in rates:
        if entry not in seg_ids:
            add("UNKNOWN_ENTRY_SEGMENT", f"demand entry '{entry}' is not a segment of the network", "segment", entry)
        elif entry in fed:
            add("NOT_NETWORK_ENTRY", f"demand entry '{entry}' is fed by a turning movement, so it is not a network entry",
                "segment", entry, WARNING)

    moves = {m.id: m for m in network.turning_movements}
    ratios: dict[str, dict[str, float]] = {}
    for mid, r in raw_ratios.items():
        if mid not in moves:
            add("UNKNOWN_MOVEMENT", f"turning ratio for unknown movement '{mid}'", "turning_movement", mid)
        else:
            ratios.setdefault(moves[mid].from_segment, {})[mid] = r
    issues += demand_issues(rates, ratios)
    return ValidationResult(issues)


def build_engine(network: Network, plans: list[SignalPlan], demand: dict, simulation: dict,
                 on_finish=None) -> Engine:
    network = NetworkService(network).provide_network_state()  # raises NetworkBlockedError
    signals_svc = SignalService()
    for plan in plans:
        signals_svc.set_signal_plan(plan, network)  # raises SignalPlanBlockedError
    controls = {i.id: i.control_type for i in network.intersections}

    result = validate_scenario(network, demand, simulation)
    if not result.is_valid:
        raise DemandError(result.errors)  # warnings never block a run

    moves = {m.id: m for m in network.turning_movements}
    outgoing: dict[str, list] = {}
    for m in network.turning_movements:
        outgoing.setdefault(m.from_segment, []).append(m)

    rates = demand.get("arrival_rates_vehicles_per_hour", {})
    ratios: dict[str, dict[str, float]] = {}
    for mid, r in demand.get("turning_ratios", {}).items():
        ratios.setdefault(moves[mid].from_segment, {})[mid] = r
    vehicles = generate_vehicles(simulation.get("seed", 0), rates, ratios,
                                 duration_s=simulation.get("duration_s", 3600.0))

    signals, yields_to = {}, {}
    for m in network.turning_movements:
        ctrl = controls.get(m.intersection)
        if ctrl == ControlType.SIGNALIZED:
            plan = signals_svc.provide_signal_plan(m.intersection)  # raises if the plan is missing
            signals[(m.from_segment, m.to_segment)] = phase_green(plan, m.id)
        elif ctrl in YIELDING:
            # ponytail: stop-controlled is treated like yield (no full stop first); see DEVIATIONS.md
            for o in network.turning_movements:
                if o.intersection != m.intersection or o.from_segment == m.from_segment:
                    continue
                try:
                    clash = movements_conflict(network, m, o)
                except ConflictCheckUnavailable:
                    clash = True  # no geometry: be conservative
                if clash:
                    yields_to.setdefault(m.from_segment, set()).add(o.from_segment)

    segments = {s.id: Segment(s.length_m, s.speed_limit_mps) for s in network.segments}  # validated: limit set
    routes = {(entry, mid): _route(moves[mid], outgoing) for entry, rs in ratios.items() for mid in rs}
    dt = simulation.get("time_step_s", Params.dt)
    return Engine(segments, routes, vehicles, signals=signals,
                  yields_to={k: sorted(v) for k, v in yields_to.items()},
                  duration=simulation.get("duration_s", 3600.0), params=Params(dt=dt), on_finish=on_finish)


def engine_from_document(data: dict, on_finish=None) -> Engine:
    raw_plans = data.get("signal_plans") or ([data["signal_plan"]] if data.get("signal_plan") else [])
    plans = [plan_from_dict({"signal_plan": p}) for p in raw_plans]
    return build_engine(network_from_dict(data), plans, data.get("demand", {}), data.get("simulation", {}), on_finish)


def load_scenario(path, on_finish=None) -> Engine:
    return engine_from_document(json.loads(Path(path).read_text(encoding="utf-8")), on_finish)
