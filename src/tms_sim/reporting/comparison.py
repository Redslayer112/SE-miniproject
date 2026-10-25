"""Simulation scenario comparison and run metrics evaluation (Step 5F).

Provides headless, authoritative comparison data models and computation
for comparing completed simulation runs, computing absolute and percentage
changes, evaluating improvements/regressions, and flagging incompatibilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import TYPE_CHECKING, Any

from tms_sim.reporting.metrics import SimulationMetrics, compute_metrics

if TYPE_CHECKING:
    from tms_sim.sim.engine import Engine


class MetricDirection(str, Enum):
    """Directionality of metric evaluation for performance comparison."""

    LOWER_IS_BETTER = "lower_is_better"
    HIGHER_IS_BETTER = "higher_is_better"
    INFORMATIONAL = "informational"


class ComparisonStatus(str, Enum):
    """Evaluation status of a candidate metric compared against baseline."""

    IMPROVED = "improved"
    REGRESSED = "regressed"
    UNCHANGED = "unchanged"
    UNAVAILABLE = "unavailable"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True)
class SimulationRunRecord:
    """Immutable snapshot of a completed simulation run and its metrics."""

    run_id: str
    label: str
    scenario_name: str
    metrics: SimulationMetrics
    timestamp: str = ""

    @classmethod
    def from_engine(
        cls,
        engine: Engine,
        scenario_name: str = "",
        label: str = "",
        run_id: str = "",
        timestamp: str = "",
    ) -> SimulationRunRecord:
        """Construct a validated record from an engine instance.

        Raises ValueError if the engine has not completed its simulation.
        """
        if not getattr(engine, "finished", False):
            raise ValueError("Cannot capture an incomplete simulation run for comparison.")

        metrics = compute_metrics(engine)
        generated_id = run_id or f"run_{id(engine)}_{int(engine.time)}"
        scen_name = scenario_name or getattr(engine, "scenario_id", "Scenario")
        record_label = label or f"{scen_name} ({metrics.simulated_time:.0f}s)"

        return cls(
            run_id=generated_id,
            label=record_label,
            scenario_name=scen_name,
            metrics=metrics,
            timestamp=timestamp,
        )


@dataclass(frozen=True)
class MetricComparison:
    """Comparison result for a single metric between baseline and candidate runs."""

    key: str
    name: str
    unit: str
    baseline_value: float | int | None
    candidate_value: float | int | None
    absolute_change: float | None
    percent_change: float | None
    direction: MetricDirection
    status: ComparisonStatus
    note: str = ""

    @property
    def is_available(self) -> bool:
        """True if both baseline and candidate values are available."""
        return self.baseline_value is not None and self.candidate_value is not None


@dataclass(frozen=True)
class ScenarioComparison:
    """Complete comparison between a baseline run and candidate run."""

    baseline: SimulationRunRecord
    candidate: SimulationRunRecord
    metrics: list[MetricComparison]
    duration_compatible: bool
    warning: str | None = None

    def get_metric(self, key: str) -> MetricComparison | None:
        """Lookup a specific metric comparison by key."""
        for m in self.metrics:
            if m.key == key:
                return m
        return None


def calculate_metric_comparison(
    key: str,
    name: str,
    unit: str,
    baseline_val: float | int | None,
    candidate_val: float | int | None,
    direction: MetricDirection,
    note: str = "",
) -> MetricComparison:
    """Compute difference, percentage change, and status for a single metric."""
    if baseline_val is None or candidate_val is None:
        return MetricComparison(
            key=key,
            name=name,
            unit=unit,
            baseline_value=baseline_val,
            candidate_value=candidate_val,
            absolute_change=None,
            percent_change=None,
            direction=direction,
            status=ComparisonStatus.UNAVAILABLE,
            note=note or "Metric value not available",
        )

    b_float = float(baseline_val)
    c_float = float(candidate_val)
    diff = c_float - b_float
    abs_change = round(diff, 2)

    # Percentage change calculation with safe zero-baseline handling
    pct_change: float | None = None
    if b_float != 0.0:
        pct_change = round((diff / abs(b_float)) * 100.0, 1)

    # Status evaluation
    is_equal = math.isclose(b_float, c_float, abs_tol=1e-5)
    if is_equal:
        status = ComparisonStatus.UNCHANGED
    elif direction == MetricDirection.LOWER_IS_BETTER:
        status = ComparisonStatus.IMPROVED if diff < 0 else ComparisonStatus.REGRESSED
    elif direction == MetricDirection.HIGHER_IS_BETTER:
        status = ComparisonStatus.IMPROVED if diff > 0 else ComparisonStatus.REGRESSED
    else:
        status = ComparisonStatus.UNCHANGED

    return MetricComparison(
        key=key,
        name=name,
        unit=unit,
        baseline_value=baseline_val,
        candidate_value=candidate_val,
        absolute_change=abs_change,
        percent_change=pct_change,
        direction=direction,
        status=status,
        note=note,
    )


def compare_runs(
    baseline: SimulationRunRecord,
    candidate: SimulationRunRecord,
) -> ScenarioComparison:
    """Compare two simulation run records and return an authoritative comparison report."""
    # Check duration compatibility
    dur_b = baseline.metrics.duration
    dur_c = candidate.metrics.duration
    duration_compatible = math.isclose(dur_b, dur_c, rel_tol=1e-3, abs_tol=0.1)

    warning: str | None = None
    if not duration_compatible:
        warning = (
            f"Configured durations differ (Baseline: {dur_b:.1f}s vs Candidate: {dur_c:.1f}s). "
            "Cumulative count and throughput comparisons may be biased."
        )

    m_b = baseline.metrics
    m_c = candidate.metrics

    metrics: list[MetricComparison] = [
        # 1. Mean Travel Time (Primary efficiency metric: Lower is better)
        calculate_metric_comparison(
            key="mean_travel_time",
            name="Mean Travel Time",
            unit="s",
            baseline_val=m_b.mean_travel_time,
            candidate_val=m_c.mean_travel_time,
            direction=MetricDirection.LOWER_IS_BETTER,
            note="Average trip duration for completed journeys",
        ),
        # 2. Vehicles Completed (Primary throughput metric: Higher is better)
        calculate_metric_comparison(
            key="vehicles_completed",
            name="Vehicles Completed",
            unit="veh",
            baseline_val=m_b.vehicles_completed,
            candidate_val=m_c.vehicles_completed,
            direction=MetricDirection.HIGHER_IS_BETTER,
            note="Total journeys finished",
        ),
        # 3. Vehicles in Network (Congestion indicator: Lower is better)
        calculate_metric_comparison(
            key="vehicles_in_network",
            name="Vehicles in Network",
            unit="veh",
            baseline_val=m_b.vehicles_in_network,
            candidate_val=m_c.vehicles_in_network,
            direction=MetricDirection.LOWER_IS_BETTER,
            note="Active vehicles remaining inside network at end of run",
        ),
        # 4. Vehicles Entered (Network utilization: Higher is better)
        calculate_metric_comparison(
            key="vehicles_entered",
            name="Vehicles Entered",
            unit="veh",
            baseline_val=m_b.vehicles_entered,
            candidate_val=m_c.vehicles_entered,
            direction=MetricDirection.HIGHER_IS_BETTER,
            note="Vehicles that successfully entered from origins",
        ),
        # 5. Vehicles Generated (Demand: Informational)
        calculate_metric_comparison(
            key="vehicles_generated",
            name="Vehicles Generated",
            unit="veh",
            baseline_val=m_b.vehicles_generated,
            candidate_val=m_c.vehicles_generated,
            direction=MetricDirection.INFORMATIONAL,
            note="Scheduled vehicle demand",
        ),
        # 6. Simulation Duration (Context: Informational)
        calculate_metric_comparison(
            key="duration",
            name="Simulation Duration",
            unit="s",
            baseline_val=m_b.duration,
            candidate_val=m_c.duration,
            direction=MetricDirection.INFORMATIONAL,
            note="Configured simulation time horizon",
        ),
        # 7. Unmodeled backend metrics explicitly documented as Unavailable
        MetricComparison(
            key="throughput_vph",
            name="Hourly Throughput",
            unit="veh/h",
            baseline_value=None,
            candidate_value=None,
            absolute_change=None,
            percent_change=None,
            direction=MetricDirection.HIGHER_IS_BETTER,
            status=ComparisonStatus.UNAVAILABLE,
            note="Not modeled in current simulation engine",
        ),
        MetricComparison(
            key="queue_length_veh",
            name="Average Queue Length",
            unit="veh",
            baseline_value=None,
            candidate_value=None,
            absolute_change=None,
            percent_change=None,
            direction=MetricDirection.LOWER_IS_BETTER,
            status=ComparisonStatus.UNAVAILABLE,
            note="Not modeled in current simulation engine",
        ),
        MetricComparison(
            key="average_delay_s",
            name="Average Vehicle Delay",
            unit="s",
            baseline_value=None,
            candidate_value=None,
            absolute_change=None,
            percent_change=None,
            direction=MetricDirection.LOWER_IS_BETTER,
            status=ComparisonStatus.UNAVAILABLE,
            note="Not modeled in current simulation engine",
        ),
    ]

    return ScenarioComparison(
        baseline=baseline,
        candidate=candidate,
        metrics=metrics,
        duration_compatible=duration_compatible,
        warning=warning,
    )
