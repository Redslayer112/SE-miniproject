import pytest

from tms_sim.sim.demand import Vehicle
from tms_sim.sim.engine import Car, Engine, Params, Segment

P = Params()
ROAD = {"A": Segment(500.0, 15.0), "B": Segment(500.0, 15.0)}
ROUTES = {("A", "go"): ["A", "B"]}


def make(vehicles, **kw):
    kw.setdefault("duration", 120.0)
    return Engine(ROAD, ROUTES, vehicles, **kw)


def car(v, x=100.0):
    return Car(0, ["A"], 0, x, v, 0.0)


def run(e, seconds):
    e.start()
    e.advance(seconds)


def test_free_vehicle_travels_whole_route_and_exits():  # TC-SIM-01
    e = make([Vehicle(0, "A", "go", 0.0)], duration=200.0)
    run(e, 200.0)
    assert [ev[2] for ev in e.events] == ["spawn", "exit"]
    travel = e.events[1][0] - e.events[0][0]
    free = (1000.0 - P.length) / 15.0  # spawns with its front one vehicle length in; 15 m/s limit
    assert free <= travel <= free + 2 * P.dt


def test_idm_hand_checked_values():  # AC-040: a = a_max*(1-(v/v0)^4-(s*/s)^2)
    e = make([])
    assert e._accel(car(0.0), False) == pytest.approx(1.5)  # free road from rest
    assert e._accel(car(15.0), False) == pytest.approx(0.0)  # at the speed limit
    follower = car(10.0, x=0.0)
    e.cars = [follower, Car(1, ["A"], 0, 22.0, 10.0, 0.0)]  # gap = 22 - 5 - 0 = 17 = s* (v=vl=10)
    assert e._accel(follower, False) == pytest.approx(1.5 * (1 - (10 / 15) ** 4 - 1))


def test_follower_never_overlaps_a_stopped_leader():
    sig = {("A", "B"): lambda t: False}  # leader waits at the line for ever; follower must queue behind it
    e = make([Vehicle(0, "A", "go", 0.0), Vehicle(1, "A", "go", 8.0)], signals=sig)
    run(e, 120.0)
    lead, follow = sorted(e.cars, key=lambda c: -c.x)
    assert lead.x <= 500.0 and lead.x - P.length - follow.x >= 0.0
    assert follow.v == pytest.approx(0.0, abs=0.05)


def test_red_signal_holds_vehicle_then_green_releases_it():  # TC-SIM-01 red-signal check
    e = make([Vehicle(0, "A", "go", 0.0)], signals={("A", "B"): lambda t: t >= 60.0}, duration=200.0)
    e.start()
    while e.time < 60.0:
        e.advance(P.dt)
        assert not e.exited
        assert all(c.leg == 0 and c.x <= 500.0 for c in e.cars)
    run(e, 140.0)
    assert len(e.exited) == 1


GAP_ROADS = {"A": Segment(300.0, 15.0), "M": Segment(300.0, 15.0), "X": Segment(200.0, 15.0)}
GAP_ROUTES = {("A", "go"): ["A", "X"], ("M", "go"): ["M"]}


def gap_engine(vehicles=()):
    return Engine(GAP_ROADS, GAP_ROUTES, list(vehicles), yields_to={"A": ["M"]}, duration=100.0)


@pytest.mark.parametrize("m_x, m_v, must_wait", [
    (280.0, 10.0, True),   # 2.0 s from its line < 3 s critical gap
    (200.0, 10.0, False),  # 10 s away: acceptable gap
    (290.0, 0.0, False),   # stationary conflicting vehicle is not a threat
])
def test_gap_acceptance_rule(m_x, m_v, must_wait):
    e = gap_engine()
    a = Car(0, ["A", "X"], 0, 250.0, 10.0, 0.0)
    e.cars = [a, Car(1, ["M"], 0, m_x, m_v, 0.0)]
    assert e._blocked(a) is must_wait


def test_yielding_vehicle_still_gets_through():
    e = gap_engine([Vehicle(0, "M", "go", 0.0), Vehicle(1, "A", "go", 0.0)])
    run(e, 100.0)
    assert len(e.exited) == 2


def test_pause_step_reset():  # TC-SIM-02
    e = make([Vehicle(0, "A", "go", 0.0)])
    e.start()
    e.advance(5.0)
    t = e.time
    e.pause()
    e.advance(10.0)
    assert e.time == t  # paused: frozen
    e.step()
    assert e.time == pytest.approx(t + P.dt)  # one step is exactly dt
    e.reset()
    assert e.time == 0.0 and not e.cars and not e.running and not e.events


@pytest.mark.parametrize("m", [0.5, 1, 2, 4])
def test_speed_multiplier(m):
    e = make([])
    e.set_speed(m)
    run(e, 10.0)
    assert e.time == pytest.approx(10.0 * m, abs=P.dt)


def test_invalid_speed_rejected():
    with pytest.raises(ValueError):
        make([]).set_speed(3)


def test_stops_at_duration_and_finalizes_once():  # TC-SIM-03
    calls = []
    e = make([], duration=10.2, on_finish=calls.append)
    run(e, 100.0)
    assert e.finished and not e.running
    assert 10.2 <= e.time < 10.2 + P.dt  # within one step
    t = e.time
    e.start()  # cannot restart a finished run
    e.advance(50.0)
    e.step()
    assert e.time == t and len(calls) == 1
    e.reset()
    run(e, 100.0)
    assert len(calls) == 2  # a fresh run finalizes once more


def test_runs_are_deterministic():
    vs = [Vehicle(i, "A", "go", 3.0 * i) for i in range(10)]
    a, b = make(vs, signals={("A", "B"): lambda t: (t // 20) % 2 == 0}), make(vs, signals={("A", "B"): lambda t: (t // 20) % 2 == 0})
    run(a, 120.0)
    run(b, 120.0)
    assert a.events == b.events and a.time == b.time


def test_car_standing_on_the_line_stays_there_on_red():
    e = make([], signals={("A", "B"): lambda t: False})
    e.cars = [Car(0, ["A", "B"], 0, 500.0, 0.0, 0.0)]  # front exactly at the stop line
    for _ in range(10):
        e.step()
    assert e.cars[0].leg == 0 and e.cars[0].x == 500.0


def test_committed_car_may_clear_when_it_cannot_stop():
    e = make([], signals={("A", "B"): lambda t: False})
    fast = Car(0, ["A", "B"], 0, 498.0, 15.0, 0.0)  # needs 12.5 m at 9 m/s^2, has 2 m
    e.cars = [fast]
    assert e._blocked(fast) is False
    assert e._blocked(Car(1, ["A", "B"], 0, 400.0, 15.0, 0.0)) is True  # 100 m out: must stop
