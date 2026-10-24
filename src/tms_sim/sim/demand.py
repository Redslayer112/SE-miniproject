"""Demand Generator (SAD §3.4/§4.3; TMS-F-030, TMS-F-032).

generate_vehicles() is the SAD's generateVehicles(seed, arrivalRates, turningRatios) with the
simulated duration added as a keyword; its return value is the provideDemand() output.
Entry points and movements are opaque string ids owned by the network model (#3).
"""
import math
import random
from dataclasses import dataclass

RATIO_TOL = 1e-6


class DemandError(ValueError):
    """Invalid demand input; .errors lists every problem (like network validation, TMS-F-012)."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Vehicle:
    id: int
    entry: str
    movement: str
    depart_time: float  # simulated seconds


def _number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate_demand(arrival_rates: dict[str, float], turning_ratios: dict[str, dict[str, float]]) -> None:
    errors = []
    for entry, rate in arrival_rates.items():
        if not _number(rate) or rate < 0:
            errors.append(f"{entry}: arrival rate must be a number >= 0 veh/h, got {rate!r}")
        ratios = turning_ratios.get(entry)
        if not ratios:
            errors.append(f"{entry}: no turning ratios defined")
        elif any(not _number(r) or r < 0 for r in ratios.values()):
            errors.append(f"{entry}: turning ratios must be numbers >= 0")
        elif abs(sum(ratios.values()) - 1.0) > RATIO_TOL:
            errors.append(f"{entry}: turning ratios must sum to 1, got {sum(ratios.values()):g}")
    for entry in turning_ratios:
        if entry not in arrival_rates:
            errors.append(f"{entry}: turning ratios given but no arrival rate")
    if errors:
        raise DemandError(errors)


def generate_vehicles(
    seed: int,
    arrival_rates: dict[str, float],
    turning_ratios: dict[str, dict[str, float]],
    *,
    duration_s: float,
) -> list[Vehicle]:
    """Poisson arrivals per entry (rate in veh/h), movement drawn from the turning ratios.

    One random.Random(seed) drives everything and entries are visited in sorted order, so the
    same inputs always give the same sequence. Result is sorted by departure time.
    """
    if not _number(duration_s) or duration_s <= 0:
        raise DemandError([f"duration must be > 0 s, got {duration_s!r}"])
    validate_demand(arrival_rates, turning_ratios)
    rng = random.Random(seed)
    raw = []
    for entry in sorted(arrival_rates):
        per_s = arrival_rates[entry] / 3600.0
        if per_s == 0:
            continue
        moves = sorted(turning_ratios[entry])
        weights = [turning_ratios[entry][m] for m in moves]
        t = rng.expovariate(per_s)
        while t < duration_s:
            raw.append((t, entry, rng.choices(moves, weights)[0]))
            t += rng.expovariate(per_s)
    raw.sort()
    return [Vehicle(i, e, m, t) for i, (t, e, m) in enumerate(raw)]
