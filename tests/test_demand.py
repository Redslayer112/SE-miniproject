import math

import pytest

from tms_sim.network.validation import ValidationIssue
from tms_sim.sim.demand import DemandError, generate_vehicles, validate_demand

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


@pytest.mark.parametrize(
    "rates, ratios, code, entry",
    [
        ({"N": -1.0}, {"N": {"s": 1.0}}, "INVALID_ARRIVAL_RATE", "N"),
        ({"N": 100.0}, {}, "MISSING_TURNING_RATIOS", "N"),
        ({"N": 100.0}, {"N": {"s": "x"}}, "INVALID_TURNING_RATIO", "N"),
        ({"N": 100.0}, {"N": {"s": 0.5, "l": 0.4}}, "TURNING_RATIO_SUM", "N"),
        ({"N": 100.0}, {"N": {"s": 1.0}, "X": {"s": 1.0}}, "RATIOS_WITHOUT_RATE", "X"),
    ],
)
def test_demand_issues_have_network_issue_shape(rates, ratios, code, entry):  # Issue #28
    with pytest.raises(DemandError) as e:
        validate_demand(rates, ratios)
    [issue] = e.value.issues
    assert isinstance(issue, ValidationIssue)
    assert (issue.code, issue.element_type, issue.element_id, issue.severity) == (code, "segment", entry, "error")
    assert e.value.errors == [issue.message] and issue.message.startswith(f"{entry}: ")


def test_ratio_sum_tolerance_is_1e_6():
    validate_demand({"N": 1.0}, {"N": {"s": 0.5, "l": 0.5 + 5e-7}})
    with pytest.raises(DemandError):
        validate_demand({"N": 1.0}, {"N": {"s": 0.5, "l": 0.5 + 2e-6}})


def test_invalid_duration_issue_code():
    with pytest.raises(DemandError) as e:
        gen(duration_s=0)
    assert [(i.code, i.element_type, i.element_id) for i in e.value.issues] == [("INVALID_DURATION", "simulation", "duration_s")]


def test_plain_string_errors_still_accepted():  # existing callers build DemandError from strings
    err = DemandError(["a", "b"])
    assert err.errors == ["a", "b"] and str(err) == "a; b"
    assert [i.code for i in err.issues] == ["INVALID_DEMAND", "INVALID_DEMAND"]
