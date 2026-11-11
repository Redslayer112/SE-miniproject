
"""Simulation Engine (SAD §3.4; TMS-F-040/041/042). Headless: no Qt, no randomness (demand is input).

Model values are APPROVED in docs/decisions/0001-baseline-proposal.md (#1):
IDM car-following (Treiber et al. 2000), red signal = stationary obstacle at the stop line,
critical-gap acceptance where a segment yields to others, fixed time step.

Network/signal inputs are plain data so the network (#3) and signal (#5) owners can feed them:
  segments    id -> Segment (length, speed limit)
  routes      (entry id, movement id) -> ordered segment ids; entry id is the first segment
  signals     (from segment, to segment) -> green(t) -> bool, for that movement's stop line
  yields_to   segment id -> segment ids whose approaching vehicles must be given way to
"""

import math
from dataclasses import dataclass
from typing import Callable

from tms_sim.sim.demand import Vehicle

SPEEDS = (0.5, 1, 2, 4)  # TMS-F-041 (8x / unbounded are SRS-listed but outside issue #7)


@dataclass(frozen=True)
class Params:
    dt: float = 0.5  # s; SRS allows 0.1-1.0
    a_max: float = 1.5  # m/s^2
    b: float = 2.0  # m/s^2 comfortable deceleration
    s0: float = 2.0  # m standstill gap
    headway: float = 1.5  # s desired time headway
    length: float = 5.0  # m vehicle length
    critical_gap: float = 3.0  # s to a conflicting vehicle
    max_brake: float = 9.0  # m/s^2 physical limit


@dataclass(frozen=True)
class Segment:
    length: float  # m
    speed_limit: float  # m/s


@dataclass
class Car:
    id: int
    route: list[str]
    leg: int  # index into route
    x: float  # m, front bumper, from the start of the current segment
    v: float
    entered: float  # simulated time the car entered the network
    distance_m: float = 0.0


class Engine:
    def __init__(
        self,
        segments,
        routes,
        vehicles: list[Vehicle],
        signals=None,
        yields_to=None,
        duration: float = 3600.0,
        params: Params = Params(),
        on_finish: Callable | None = None,
    ):
        self.segs, self.routes, self.vehicles = (
            segments,
            routes,
            sorted(vehicles, key=lambda v: v.depart_time),
        )
        self.signals, self.yields_to = signals or {}, yields_to or {}
        self.duration, self.p, self.on_finish = duration, params, on_finish
        self.running_state_transitions: list[dict] = []
        self._running = False
        self.reset()

    # ---- controls (TMS-F-041) ----
    def reset(self):
        """Back to t = 0 with the same inputs; nothing random lives here so reruns are identical."""
        self.time, self.finished, self.speed = 0.0, False, 1
        self._steps = 0
        self._set_running(False, "reset", "engine")
        self.cars: list[Car] = []
        self.exited: list[Car] = []
        self.events: list[tuple] = []  # (time, vehicle id, "spawn" | "exit", segment id)
        # Canonical metrics event log. Legacy lifecycle events remain in ``events`` for
        # callers that consume the original four-field tuple format.
        self.metric_events: list[dict] = []
        self._waiting = list(self.vehicles)
        self._wall = 0.0

    def start(self):
        self._set_running(not self.finished, "start", "engine")

    @property
    def running(self) -> bool:
        return self._running

    @running.setter
    def running(self, value: bool):
        """Retain the public attribute API and audit direct/unknown transitions."""
        self._set_running(value, "unknown_direct_assignment", "unknown")

    def _set_running(self, value: bool, reason: str, source: str):
        value = bool(value)
        previous = getattr(self, "_running", False)
        self._running = value
        if previous != value:
            self.running_state_transitions.append({
                "sequence": len(self.running_state_transitions) + 1,
                "simulation_time_s": round(float(getattr(self, "time", 0.0)), 3),
                "from_running": previous,
                "to_running": value,
                "reason": reason,
                "source": source,
            })

    def pause(self, reason: str = "programmatic", source: str | None = None):
        self._set_running(False, reason, source or "programmatic")

    def set_speed(self, multiplier):
        if multiplier not in SPEEDS:
            raise ValueError(f"speed must be one of {SPEEDS}")
        self.speed = multiplier

    def advance(self, wall_seconds: float):
        """Called by the UI timer: runs speed x wall_seconds of simulated time while running."""
        if not self.running:
            return
        self._wall += wall_seconds * self.speed
        while self._wall >= self.p.dt and self.running:
            self.step()
            self._wall -= self.p.dt

    # ---- one time step (TMS-F-040, TMS-F-042) ----
    def step(self):
        if self.finished:
            return
        p = self.p
        self._spawn()
        stop = {c.id: self._stop_line(c) for c in self.cars}
        acc = {c.id: self._accel(c, stop[c.id]) for c in self.cars}
        distance_this_step = 0.0
        active_vehicle_time = 0.0

        for c in self.cars:
            v = max(0.0, c.v + acc[c.id] * p.dt)
            distance = (c.v + v) / 2 * p.dt
            if c.leg + 1 == len(c.route):
                distance = min(
                    distance,
                    max(0.0, self.segs[c.route[c.leg]].length - c.x),
                )
            c.x += distance
            c.distance_m += distance
            distance_this_step += distance
            active_vehicle_time += p.dt
            c.v = v

        for c in list(self.cars):
            length = self.segs[c.route[c.leg]].length
            while c.x >= length:
                if stop[c.id] is not None and stop[c.id][0] == c.leg:
                    if c.x > length:  # held at the line: never carried over it on red
                        c.x, c.v = length, 0.0
                    break
                if c.leg + 1 == len(c.route):
                    self.cars.remove(c)
                    self.exited.append(c)
                    exit_time = self.time + p.dt
                    self.events.append((exit_time, c.id, "exit", c.route[c.leg]))
                    self.metric_events.append({
                        "type": "exit",
                        "time": exit_time,
                        "vehicle_id": c.id,
                        "segment_id": c.route[c.leg],
                        "distance_m": c.distance_m,
                        "free_flow_time_s": self._free_flow_time(c.route),
                    })
                    break
                c.x -= length
                c.leg += 1
                length = self.segs[c.route[c.leg]].length

        self._steps += 1
        self.time = round(self._steps * p.dt, 9)  # counter, not +=: no float drift
        queues: dict[str, int] = {}
        for c in self.cars:
            if c.v < 0.5:
                segment_id = c.route[c.leg]
                queues[segment_id] = queues.get(segment_id, 0) + 1

        self.metric_events.append({
            "type": "sample",
            "time": self.time,
            "dt": p.dt,
            "speed_distance_m": distance_this_step,
            "active_vehicle_time_s": active_vehicle_time,
            "queue_by_approach": queues,
        })

        if self.time >= self.duration:
            self.finished = True
            self._set_running(False, "completion", "engine")
            if self.on_finish:
                self.on_finish(self)  # exactly once per run: step() is a no-op once finished

    def _spawn(self):
        p = self.p
        jammed = set()
        for veh in [v for v in self._waiting if v.depart_time <= self.time]:
            if veh.entry in jammed:
                continue  # FIFO per entry: nobody overtakes a waiting vehicle at its own entry
            route = self.routes[(veh.entry, veh.movement)]
            v0 = self.segs[route[0]].speed_limit
            first = [c for c in self.cars if c.route[c.leg] == route[0]]
            if first and min(c.x for c in first) - p.length - p.length < p.s0 + p.headway * v0:
                jammed.add(veh.entry)  # entry not clear: vehicle waits, other entries still spawn
                continue
            self._waiting.remove(veh)
            self.cars.append(Car(veh.id, route, 0, p.length, v0, self.time))
            self.events.append((self.time, veh.id, "spawn", route[0]))
            self.metric_events.append({
                "type": "spawn",
                "time": self.time,
                "vehicle_id": veh.id,
                "segment_id": route[0],
                "free_flow_time_s": self._free_flow_time(route),
            })

    def _free_flow_time(self, route: list[str]) -> float:
        """Free-flow time for the route distance from the spawn point to its exit."""
        return max(
            0.0,
            sum(
                self.segs[segment_id].length / self.segs[segment_id].speed_limit
                for segment_id in route
            ) - self.p.length / self.segs[route[0]].speed_limit,
        )

    # ---- model ----
    def _stop_line(self, c: Car):
        """(leg, distance) of the first stop line c must stop at, looking at the end of its current
        segment and the next one (so a short segment cannot be jumped in one step), else None."""
        distance = self.segs[c.route[c.leg]].length - c.x
        for leg in (c.leg, c.leg + 1):
            if leg >= len(c.route):
                return None
            if leg > c.leg:
                distance += self.segs[c.route[leg]].length
            if self._blocked(c, leg, distance):
                return leg, distance
        return None

    def _blocked(self, c: Car, leg: int, distance: float) -> bool:
        """Must c stop at the end of route[leg], `distance` m ahead: red light, or no acceptable gap."""
        seg = c.route[leg]
        nxt = c.route[leg + 1] if leg + 1 < len(c.route) else None
        green = self.signals.get((seg, nxt))
        if green and not green(self.time):
            # committed: cannot stop before the line even at max braking (yellow-onset dilemma zone)
            return c.v ** 2 / (2 * self.p.max_brake) <= distance
        for other in self.yields_to.get(seg, ()):
            for o in self.cars:
                # ponytail: stationary conflicting vehicles are ignored (no deadlock); revisit with #1's rule
                if (
                    o.route[o.leg] == other
                    and o.v > 0.5
                    and (self.segs[other].length - o.x) / o.v < self.p.critical_gap
                ):
                    return True
        return False

    def _leader(self, c: Car):
        # ponytail: O(n^2) scan; index cars per segment if NF-001 (2000 vehicles) is missed
        p, seg = self.p, c.route[c.leg]
        ahead = [
            o for o in self.cars
            if o is not c and o.route[o.leg] == seg and o.x > c.x
        ]
        if ahead:
            o = min(ahead, key=lambda o: o.x)
            return o.x - p.length - c.x, o.v
        if c.leg + 1 < len(c.route):
            nxt = [o for o in self.cars if o.route[o.leg] == c.route[c.leg + 1]]
            if nxt:
                o = min(nxt, key=lambda o: o.x)
                return self.segs[seg].length - c.x + o.x - p.length, o.v
        return None

    def _accel(self, c: Car, stop) -> float:
        p, seg = self.p, self.segs[c.route[c.leg]]
        gaps = []
        if (lead := self._leader(c)) is not None:
            gaps.append(lead)
        if stop is not None:
            gaps.append((stop[1], 0.0))  # stop line behaves like a stationary leader
        a = p.a_max * (1 - (c.v / seg.speed_limit) ** 4)
        if gaps:
            s, vl = min(gaps)
            s = max(s, 0.1)
            s_star = p.s0 + max(
                0.0,
                c.v * p.headway
                + c.v * (c.v - vl) / (2 * math.sqrt(p.a_max * p.b)),
            )
            a -= p.a_max * (s_star / s) ** 2
        return max(a, -p.max_brake)
