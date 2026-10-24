import math

import pytest

from tms_sim.sim.demand import DemandError, generate_vehicles

RATES = {"N": 600.0, "E": 300.0}
RATIOS = {"N": {"straight": 0.7, "left": 0.3}, "E": {"straight": 1.0}}
HOUR = 3600.0


def gen(seed=1, rates=RATES, ratios=RATIOS, duration_s=HOUR):
    return generate_vehicles(seed, rates, ratios, duration_s=duration_s)


def test_counts_match_rates_within_tolerance():  # AC-030: Poisson, tolerance 4 sigma
    for seed in range(1, 6):
        cars = gen(seed)
        for entry, rate in RATES.items():
            n = sum(c.entry == entry for c in cars)
            assert abs(n - rate) <= 4 * math.sqrt(rate), (seed, entry, n)


def test_turning_split_matches_ratios():
    cars = [c for c in gen(2, duration_s=10 * HOUR) if c.entry == "N"]
    left = sum(c.movement == "left" for c in cars) / len(cars)
    assert abs(left - 0.3) < 0.03


def test_sorted_and_inside_window():
    cars = gen()
    times = [c.depart_time for c in cars]
    assert times == sorted(times)
    assert 0 <= times[0] and times[-1] < HOUR
    assert [c.id for c in cars] == list(range(len(cars)))


def test_same_seed_identical_different_seed_differs():  # AC-032 (arrival sequence)
    assert gen(7) == gen(7)
    assert gen(7) != gen(8)


def test_zero_rate_entry_produces_nothing():
    assert gen(rates={"N": 0.0, "E": 300.0}) and not any(c.entry == "N" for c in gen(rates={"N": 0.0, "E": 300.0}))


@pytest.mark.parametrize(
    "rates, ratios, duration",
    [
        ({"N": -1.0}, {"N": {"s": 1.0}}, HOUR),
        ({"N": float("nan")}, {"N": {"s": 1.0}}, HOUR),
        ({"N": True}, {"N": {"s": 1.0}}, HOUR),
        ({"N": 100.0}, {"N": {"s": 0.5, "l": 0.4}}, HOUR),  # sums to 0.9
        ({"N": 100.0}, {"N": {"s": 1.5, "l": -0.5}}, HOUR),
        ({"N": 100.0}, {}, HOUR),  # no ratios
        ({"N": 100.0}, {"N": {"s": 1.0}, "X": {"s": 1.0}}, HOUR),  # ratios for unknown entry
        ({"N": 100.0}, {"N": {"s": 1.0}}, 0),
    ],
)
def test_invalid_input_rejected(rates, ratios, duration):
    with pytest.raises(DemandError):
        generate_vehicles(1, rates, ratios, duration_s=duration)


def test_all_errors_are_reported():
    with pytest.raises(DemandError) as e:
        gen(rates={"N": -1.0, "E": 100.0}, ratios={"N": {"s": 0.5}, "E": {"s": 0.5}})
    assert len(e.value.errors) == 3
