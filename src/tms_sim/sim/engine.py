"""Simulation Engine (SAD §3.4; TMS-F-040/041/042). Headless: no Qt, no randomness (demand is input).

Model values are PROPOSED in docs/decisions/0001-baseline-proposal.md and await team sign-off (#1):
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
    def __init__(self, segments, routes, vehicles: list[Vehicle], signals=None, yields_to=None,
                 duration: float = 3600.0, params: Params = Params(), on_finish: Callable | None = None):
        self.segs, self.routes, self.vehicles = segments, routes, sorted(vehicles, key=lambda v: v.depart_time)
        self.signals, self.yields_to = signals or {}, yields_to or {}
        self.duration, self.p, self.on_finish = duration, params, on_finish
        self.reset()

    # ---- controls (TMS-F-041) ----
    def reset(self):
        """Back to t = 0 with the same inputs; nothing random lives here so reruns are identical."""
        self.time, self.running, self.finished, self.speed = 0.0, False, False, 1
        self.cars: list[Car] = []
        self.exited: list[Car] = []
        self.events: list[tuple] = []  # (time, vehicle id, "spawn" | "exit", segment id)
        # Canonical metrics event log. Legacy lifecycle events remain in ``events`` for
        # callers that consume the original four-field tuple format.
        self.metric_events: list[dict] = []
        self._waiting = list(self.vehicles)
        self._wall = 0.0

    def start(self):
        self.running = not self.finished

    def pause(self):
        self.running = False

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
        blocked = {c.id: self._blocked(c) for c in self.cars}
        acc = {c.id: self._accel(c, blocked[c.id]) for c in self.cars}
        distance_this_step = 0.0
        active_vehicle_time = 0.0
        for c in self.cars:
            v = max(0.0, c.v + acc[c.id] * p.dt)
            distance = (c.v + v) / 2 * p.dt
            if c.leg + 1 == len(c.route):
                distance = min(distance, max(0.0, self.segs[c.route[c.leg]].length - c.x))
            c.x += distance
            c.distance_m += distance
            distance_this_step += distance
            active_vehicle_time += p.dt
            c.v = v
        for c in list(self.cars):
            length = self.segs[c.route[c.leg]].length
            if blocked[c.id]:
                if c.x > length:  # held at the line: never carried over it on red
                    c.x, c.v = length, 0.0
                continue
            while c.x >= length:
                if c.leg + 1 == len(c.route):
                    self.cars.remove(c)
                    self.exited.append(c)
                    exit_time = self.time + p.dt
                    self.events.append((exit_time, c.id, "exit", c.route[c.leg]))
                    self.metric_events.append({
                        "type": "exit", "time": exit_time, "vehicle_id": c.id,
                        "segment_id": c.route[c.leg], "distance_m": c.distance_m,
                        "free_flow_time_s": self._free_flow_time(c.route),
                    })
                    break
                c.x -= length
                c.leg += 1
                length = self.segs[c.route[c.leg]].length
        self.time += p.dt
        queues: dict[str, int] = {}
        for c in self.cars:
            if c.v < 0.5:
                segment_id = c.route[c.leg]
                queues[segment_id] = queues.get(segment_id, 0) + 1
        self.metric_events.append({
            "type": "sample", "time": self.time, "dt": p.dt,
            "speed_distance_m": distance_this_step,
            "active_vehicle_time_s": active_vehicle_time,
            "queue_by_approach": queues,
        })
        if self.time >= self.duration:
            self.finished, self.running = True, False
            if self.on_finish:
                self.on_finish(self)  # exactly once per run: step() is a no-op once finished

    def _spawn(self):
        p = self.p
        while self._waiting and self._waiting[0].depart_time <= self.time:
            veh = self._waiting[0]
            route = self.routes[(veh.entry, veh.movement)]
            v0 = self.segs[route[0]].speed_limit
            first = [c for c in self.cars if c.route[c.leg] == route[0]]
            if first and min(c.x for c in first) - p.length - p.length < p.s0 + p.headway * v0:
                return  # entry not clear: vehicle waits (FIFO)
            self._waiting.pop(0)
            self.cars.append(Car(veh.id, route, 0, p.length, v0, self.time))
            self.events.append((self.time, veh.id, "spawn", route[0]))
            self.metric_events.append({
                "type": "spawn", "time": self.time, "vehicle_id": veh.id,
                "segment_id": route[0],
                "free_flow_time_s": self._free_flow_time(route),
            })

    def _free_flow_time(self, route: list[str]) -> float:
        """Free-flow time for the route distance from the spawn point to its exit."""
        return max(0.0, sum(
            (self.segs[segment_id].length / self.segs[segment_id].speed_limit)
            for segment_id in route
        ) - self.p.length / self.segs[route[0]].speed_limit)

    # ---- model ----
    def _blocked(self, c: Car) -> bool:
        """Must c stop at the end of its segment: red light, or no acceptable gap to a conflicting stream."""
        seg = c.route[c.leg]
        nxt = c.route[c.leg + 1] if c.leg + 1 < len(c.route) else None
        green = self.signals.get((seg, nxt))
        if green and not green(self.time):
            # committed: cannot stop before the line even at max braking (yellow-onset dilemma zone)
            return c.v ** 2 / (2 * self.p.max_brake) <= self.segs[seg].length - c.x
        for other in self.yields_to.get(seg, ()):
            for o in self.cars:
                # ponytail: stationary conflicting vehicles are ignored (no deadlock); revisit with #1's rule
                if o.route[o.leg] == other and o.v > 0.5 and (self.segs[other].length - o.x) / o.v < self.p.critical_gap:
                    return True
        return False

    def _leader(self, c: Car):
        # ponytail: O(n^2) scan; index cars per segment if NF-001 (2000 vehicles) is missed
        p, seg = self.p, c.route[c.leg]
        ahead = [o for o in self.cars if o is not c and o.route[o.leg] == seg and o.x > c.x]
        if ahead:
            o = min(ahead, key=lambda o: o.x)
            return o.x - p.length - c.x, o.v
        if c.leg + 1 < len(c.route):
            nxt = [o for o in self.cars if o.route[o.leg] == c.route[c.leg + 1]]
            if nxt:
                o = min(nxt, key=lambda o: o.x)
                return self.segs[seg].length - c.x + o.x - p.length, o.v
        return None

    def _accel(self, c: Car, blocked: bool) -> float:
        p, seg = self.p, self.segs[c.route[c.leg]]
        gaps = []
        if (lead := self._leader(c)) is not None:
            gaps.append(lead)
        if blocked:
            gaps.append((seg.length - c.x, 0.0))  # stop line behaves like a stationary leader
        a = p.a_max * (1 - (c.v / seg.speed_limit) ** 4)
        if gaps:
            s, vl = min(gaps)
            s = max(s, 0.1)
            s_star = p.s0 + max(0.0, c.v * p.headway + c.v * (c.v - vl) / (2 * math.sqrt(p.a_max * p.b)))
            a -= p.a_max * (s_star / s) ** 2
        return max(a, -p.max_brake)
