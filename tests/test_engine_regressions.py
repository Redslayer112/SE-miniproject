"""Sprint 3 engine regressions and boundary cases (#27, #32). Each test names the defect it pins."""
from pathlib import Path

import pytest

from tms_sim.sim.demand import Vehicle
from tms_sim.sim.engine import Engine, Params, Segment
from tms_sim.sim.scenario import load_scenario

FIXTURES = Path(__file__).parent.parent / "fixtures" / "valid"
RED = lambda t: False  # noqa: E731


def finish(e):
    while not e.finished:
        e.step()
    return e


# ---- defect 1: a short segment could be crossed in one step, skipping its red light ----
@pytest.mark.parametrize("dt", [0.1, 0.5, 1.0])
@pytest.mark.parametrize("short", [1.0, 4.0, 10.0])
def test_short_segment_red_is_never_jumped(dt, short):
    segs = {"A": Segment(40.0, 20.0), "C": Segment(short, 20.0), "B": Segment(100.0, 20.0)}
    e = finish(Engine(segs, {("A", "t"): ["A", "C", "B"]}, [Vehicle(1, "A", "t", 0.0)],
                      signals={("C", "B"): RED}, duration=30.0, params=Params(dt=dt)))
    (c,) = e.cars
    assert not e.exited and c.route[c.leg] in ("A", "C")
    assert c.leg < 1 or c.x <= short  # held at or before C's stop line


# ---- defect 2: one jammed entry stopped every other entry from spawning (head-of-line) ----
def test_jammed_entry_does_not_hold_back_other_entries():
    segs = {"A": Segment(100.0, 10.0), "B": Segment(100.0, 10.0)}
    vehicles = [Vehicle(i, "A", "t", 0.0) for i in range(5)] + [Vehicle(99, "B", "t", 0.0)]
    e = Engine(segs, {("A", "t"): ["A"], ("B", "t"): ["B"]}, vehicles, duration=60.0)
    e.step()
    assert {c.id for c in e.cars} == {0, 99}


def test_spawn_stays_fifo_within_an_entry():
    segs = {"A": Segment(300.0, 10.0)}
    vehicles = [Vehicle(i, "A", "t", 0.0) for i in range(4)]
    e = finish(Engine(segs, {("A", "t"): ["A"]}, vehicles, duration=120.0))
    spawns = [vid for _, vid, kind, _ in e.events if kind == "spawn"]
    assert spawns == [0, 1, 2, 3]


# ---- defect 3: simulated time drifted (60.00000000000058 after 600 steps of 0.1 s) ----
@pytest.mark.parametrize("dt, duration", [(0.1, 60.0), (0.3, 30.0), (0.7, 70.0), (1.0, 5.0)])
def test_clock_is_exact_and_stops_on_duration(dt, duration):
    e = Engine({"a": Segment(100.0, 10.0)}, {}, [], duration=duration, params=Params(dt=dt))
    steps = 0
    while not e.finished:
        e.step()
        steps += 1
    assert e.time == duration and steps == round(duration / dt)


def test_event_times_are_whole_steps():
    e = finish(load_scenario(FIXTURES / "small_valid_scenario.json"))
    dt = e.p.dt
    assert e.events and all(abs(t / dt - round(t / dt)) < 1e-9 for t, *_ in e.events)


# ---- invariants on the shared fixtures ----
@pytest.mark.parametrize("name", ["small_valid_scenario.json", "performance_10_intersections.json"])
def test_no_overlap_and_no_negative_speed(name):
    e = load_scenario(FIXTURES / name)
    while not e.finished:
        e.step()
        assert all(c.v >= 0.0 for c in e.cars)
        by_seg = {}
        for c in e.cars:
            by_seg.setdefault(c.route[c.leg], []).append(c.x)
        for xs in by_seg.values():
            xs.sort()
            assert all(b - a >= e.p.length - 1e-6 for a, b in zip(xs, xs[1:]))


def test_every_spawned_vehicle_is_in_network_or_exited():
    e = finish(load_scenario(FIXTURES / "small_valid_scenario.json"))
    spawned = {vid for _, vid, kind, _ in e.events if kind == "spawn"}
    assert spawned == {c.id for c in e.cars} | {c.id for c in e.exited}


# ---- boundaries and negatives ----
def test_empty_demand_runs_to_completion():
    e = finish(Engine({"a": Segment(100.0, 10.0)}, {}, [], duration=10.0))
    assert e.time == 10.0 and not e.events


def test_controls_after_finish_are_no_ops():
    calls = []
    e = finish(Engine({"a": Segment(100.0, 10.0)}, {}, [], duration=2.0, on_finish=calls.append))
    e.start()
    e.step()
    e.advance(10.0)
    assert e.time == 2.0 and not e.running and len(calls) == 1


@pytest.mark.parametrize("bad", [0, 3, 8, -1, None])
def test_unsupported_speed_rejected_and_unchanged(bad):
    e = Engine({"a": Segment(100.0, 10.0)}, {}, [], duration=2.0)
    e.set_speed(2)
    with pytest.raises(ValueError):
        e.set_speed(bad)
    assert e.speed == 2


def test_reset_mid_run_replays_identically():
    first = finish(load_scenario(FIXTURES / "small_valid_scenario.json"))
    events = list(first.events)
    first.reset()
    for _ in range(50):
        first.step()
    first.reset()
    assert finish(first).events == events
