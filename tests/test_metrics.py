
"""Independent metric recomputation and boundary coverage for issue #10."""

from types import SimpleNamespace
from typing import Any

import pytest

from tms_sim.reporting.metrics import (
    IncrementalMetricsCalculator,
    compute_metrics,
)
from tms_sim.reporting.history import SimulationHistoryTracker
from tms_sim.sim.demand import Vehicle
from tms_sim.sim.engine import Engine, Segment


def fake_engine(
    events,
    *,
    time=2.0,
    finished=False,
    cars=(),
    vehicles=(),
) -> Any:
    """Create a lightweight fake engine for metric tests."""
    return SimpleNamespace(
        finished=finished,
        running=not finished,
        time=time,
        duration=10.0,
        vehicles=vehicles,
        cars=list(cars),
        segs={"A": object(), "B": object()},
        metric_events=events,
        events=[],
    )


def assert_optional_float_matches(actual, expected):
    """Compare optional floating-point metric values."""
    if expected is None:
        assert actual is None
    else:
        assert actual == pytest.approx(expected)


def assert_metrics_match(actual, expected):
    """Compare incremental metrics against independent recomputation."""

    assert actual.status == expected.status
    assert actual.simulated_time == pytest.approx(expected.simulated_time)
    assert actual.duration == pytest.approx(expected.duration)

    assert actual.vehicles_generated == expected.vehicles_generated
    assert actual.total_scheduled == expected.total_scheduled
    assert actual.vehicles_entered == expected.vehicles_entered
    assert actual.vehicles_completed == expected.vehicles_completed
    assert actual.vehicles_in_network == expected.vehicles_in_network

    assert_optional_float_matches(
        actual.mean_travel_time, expected.mean_travel_time
    )
    assert_optional_float_matches(
        actual.average_speed_mps, expected.average_speed_mps
    )
    assert_optional_float_matches(
        actual.throughput_vph, expected.throughput_vph
    )
    assert_optional_float_matches(
        actual.average_delay_s, expected.average_delay_s
    )
    assert_optional_float_matches(
        actual.maximum_delay_s, expected.maximum_delay_s
    )
    assert_optional_float_matches(
        actual.queue_length_veh, expected.queue_length_veh
    )

    assert (
        actual.average_queue_length_by_approach.keys()
        == expected.average_queue_length_by_approach.keys()
    )

    for approach, value in expected.average_queue_length_by_approach.items():
        assert actual.average_queue_length_by_approach[approach] == pytest.approx(
            value
        )


def test_metrics_are_recomputed_from_lifecycle_and_measurement_events():
    events = [
        {
            "type": "spawn",
            "time": 0.0,
            "vehicle_id": 1,
            "free_flow_time_s": 8.0,
        },
        {
            "type": "exit",
            "time": 12.0,
            "vehicle_id": 1,
            "free_flow_time_s": 8.0,
        },
        {
            "type": "spawn",
            "time": 1.0,
            "vehicle_id": 2,
            "free_flow_time_s": 8.0,
        },
        {
            "type": "sample",
            "time": 1.0,
            "dt": 1.0,
            "speed_distance_m": 10.0,
            "active_vehicle_time_s": 2.0,
            "queue_by_approach": {"A": 1},
        },
        {
            "type": "sample",
            "time": 2.0,
            "dt": 1.0,
            "speed_distance_m": 10.0,
            "active_vehicle_time_s": 2.0,
            "queue_by_approach": {},
        },
    ]

    m = compute_metrics(fake_engine(events))

    assert m.vehicles_entered == 2
    assert m.vehicles_completed == 1
    assert m.mean_travel_time == pytest.approx(12.0)
    assert m.average_delay_s == pytest.approx(4.0)
    assert m.maximum_delay_s == pytest.approx(4.0)
    assert m.throughput_vph == pytest.approx(1800.0)
    assert m.average_speed_mps == pytest.approx(5.0)
    assert m.average_queue_length_by_approach["A"] == pytest.approx(0.5)
    assert m.average_queue_length_by_approach["B"] == pytest.approx(0.0)
    assert m.queue_length_veh == pytest.approx(0.5)


def test_average_travel_time_deduplicates_duplicate_spawn_and_exit_events():
    events = [
        {"type": "spawn", "time": 0.0, "vehicle_id": 1},
        {"type": "spawn", "time": 100.0, "vehicle_id": 1},
        {"type": "exit", "time": 10.0, "vehicle_id": 1},
        {"type": "exit", "time": 110.0, "vehicle_id": 1},
    ]
    engine = fake_engine(events)

    metrics = compute_metrics(engine)
    incremental = IncrementalMetricsCalculator().calculate(engine)

    assert metrics.vehicles_entered == 1
    assert metrics.vehicles_completed == 1
    assert metrics.mean_travel_time == pytest.approx(10.0)
    assert incremental.mean_travel_time == pytest.approx(10.0)


def test_average_travel_time_uses_only_uniquely_matched_completed_trips():
    events = [
        {"type": "spawn", "time": 0.0, "vehicle_id": 1},
        {"type": "exit", "time": 10.0, "vehicle_id": 1},
        {"type": "spawn", "time": 1.0, "vehicle_id": 2},
        {"type": "exit", "time": 9.0, "vehicle_id": 2},
        {"type": "spawn", "time": 3.0, "vehicle_id": 3},
        {"type": "exit", "time": 5.0, "vehicle_id": 4},
    ]
    engine = fake_engine(events)

    metrics = compute_metrics(engine)
    incremental = IncrementalMetricsCalculator().calculate(engine)

    # Vehicle 3 has no exit, vehicle 4 has no spawn; trips 1 and 2 take 10s and 8s.
    assert metrics.vehicles_entered == 3
    assert metrics.vehicles_completed == 2
    assert metrics.mean_travel_time == pytest.approx(9.0)
    assert incremental.vehicles_completed == 2
    assert incremental.mean_travel_time == pytest.approx(9.0)


def test_empty_run_distinguishes_zero_counts_from_unavailable_metrics():
    m = compute_metrics(fake_engine([], time=0.0, finished=True))

    assert m.vehicles_completed == 0
    assert m.mean_travel_time is None
    assert m.average_delay_s is None
    assert m.maximum_delay_s is None
    assert m.throughput_vph is None
    assert m.average_speed_mps is None
    assert m.queue_length_veh is None
    assert m.average_queue_length_by_approach == {}


def test_average_speed_is_unavailable_without_measurement_samples():
    engine = fake_engine([], cars=[SimpleNamespace(v=8.0)])

    assert compute_metrics(engine).average_speed_mps is None
    assert IncrementalMetricsCalculator().calculate(engine).average_speed_mps is None


def test_average_speed_includes_stationary_vehicle_time():
    engine = fake_engine(
        [
            {
                "type": "sample",
                "time": 1.0,
                "dt": 1.0,
                "speed_distance_m": 10.0,
                "active_vehicle_time_s": 1.0,
                "queue_by_approach": {},
            },
            {
                "type": "sample",
                "time": 4.0,
                "dt": 3.0,
                "speed_distance_m": 0.0,
                "active_vehicle_time_s": 3.0,
                "queue_by_approach": {},
            },
        ],
        time=4.0,
    )

    assert compute_metrics(engine).average_speed_mps == pytest.approx(2.5)
    incremental = IncrementalMetricsCalculator().calculate(engine)
    assert incremental.average_speed_mps == pytest.approx(2.5)


def test_zero_completed_trips_after_elapsed_time_has_zero_throughput():
    metrics = compute_metrics(fake_engine([], time=2.0))

    assert metrics.vehicles_completed == 0
    assert metrics.throughput_vph == pytest.approx(0.0)


def test_incomplete_trip_is_counted_but_not_used_for_completed_trip_metrics():
    m = compute_metrics(
        fake_engine(
            [
                {
                    "type": "spawn",
                    "time": 0.0,
                    "vehicle_id": 7,
                    "free_flow_time_s": 5.0,
                },
                {
                    "type": "sample",
                    "time": 2.0,
                    "dt": 2.0,
                    "speed_distance_m": 4.0,
                    "active_vehicle_time_s": 2.0,
                    "queue_by_approach": {"A": 1},
                },
            ]
        )
    )

    assert m.vehicles_entered == 1
    assert m.vehicles_completed == 0
    assert m.mean_travel_time is None
    assert m.average_delay_s is None
    assert m.maximum_delay_s is None
    assert m.average_speed_mps == pytest.approx(2.0)
    assert m.average_queue_length_by_approach["A"] == pytest.approx(1.0)


def test_incremental_metrics_match_recomputation_as_events_are_appended():
    events = [
        {
            "type": "spawn",
            "time": 0.0,
            "vehicle_id": 1,
            "free_flow_time_s": 8.0,
        },
        {
            "type": "sample",
            "time": 1.0,
            "dt": 1.0,
            "speed_distance_m": 10.0,
            "active_vehicle_time_s": 2.0,
            "queue_by_approach": {"A": 1},
        },
    ]

    engine = fake_engine(events, time=1.0)
    calculator = IncrementalMetricsCalculator()

    # First calculation processes the initial events.
    incremental = calculator.calculate(engine)
    expected = compute_metrics(engine)

    assert_metrics_match(incremental, expected)

    # Append more events to the same event log.
    events.extend(
        [
            {
                "type": "exit",
                "time": 12.0,
                "vehicle_id": 1,
                "free_flow_time_s": 8.0,
            },
            {
                "type": "spawn",
                "time": 1.0,
                "vehicle_id": 2,
                "free_flow_time_s": 8.0,
            },
            {
                "type": "sample",
                "time": 2.0,
                "dt": 1.0,
                "speed_distance_m": 10.0,
                "active_vehicle_time_s": 2.0,
                "queue_by_approach": {},
            },
        ]
    )

    engine.time = 2.0

    # Only newly appended events should be processed.
    incremental = calculator.calculate(engine)
    expected = compute_metrics(engine)

    assert_metrics_match(incremental, expected)

    # Calling again without new events must preserve the same result.
    repeated = calculator.calculate(engine)

    assert_metrics_match(repeated, expected)


def test_incremental_calculator_rebuilds_when_engine_or_event_log_changes():
    calculator = IncrementalMetricsCalculator()

    first_events = [
        {
            "type": "spawn",
            "time": 0.0,
            "vehicle_id": 1,
            "free_flow_time_s": 5.0,
        },
        {
            "type": "exit",
            "time": 8.0,
            "vehicle_id": 1,
            "free_flow_time_s": 5.0,
        },
    ]

    first_engine = fake_engine(first_events, time=2.0)

    first_result = calculator.calculate(first_engine)
    assert_metrics_match(first_result, compute_metrics(first_engine))

    # A different engine must not inherit the first engine's cached metrics.
    second_events = [
        {
            "type": "spawn",
            "time": 0.0,
            "vehicle_id": 2,
            "free_flow_time_s": 4.0,
        },
        {
            "type": "exit",
            "time": 6.0,
            "vehicle_id": 2,
            "free_flow_time_s": 4.0,
        },
    ]

    second_engine = fake_engine(second_events, time=3.0)

    second_result = calculator.calculate(second_engine)
    assert_metrics_match(second_result, compute_metrics(second_engine))

    assert second_result.vehicles_completed == 1
    assert second_result.mean_travel_time == pytest.approx(6.0)

    # Replacing the event log on the same engine must also rebuild the cache.
    replacement_events = [
        {
            "type": "spawn",
            "time": 0.0,
            "vehicle_id": 3,
            "free_flow_time_s": 2.0,
        }
    ]

    second_engine.metric_events = replacement_events
    second_engine.time = 1.0

    replacement_result = calculator.calculate(second_engine)
    expected = compute_metrics(second_engine)

    assert_metrics_match(replacement_result, expected)
    assert replacement_result.vehicles_entered == 1
    assert replacement_result.vehicles_completed == 0


def test_incremental_calculator_starts_fresh_after_real_engine_reset():
    engine = Engine(
        {"R": Segment(25.0, 10.0)},
        {("R", "straight"): ["R"]},
        [Vehicle(11, "R", "straight", 0.5)],
        duration=10.0,
    )
    calculator = IncrementalMetricsCalculator()

    engine.start()
    engine.advance(3.0)
    before_reset = calculator.calculate(engine)

    assert before_reset.vehicles_entered == 1
    assert before_reset.vehicles_completed == 1
    assert before_reset.mean_travel_time == pytest.approx(2.0)

    engine.reset()
    after_reset = calculator.calculate(engine)

    assert after_reset.status == "Ready"
    assert after_reset.simulated_time == pytest.approx(0.0)
    assert after_reset.duration == pytest.approx(10.0)
    assert after_reset.vehicles_generated == 0
    assert after_reset.total_scheduled == 1
    assert after_reset.vehicles_entered == 0
    assert after_reset.vehicles_completed == 0
    assert after_reset.vehicles_in_network == 0
    assert after_reset.mean_travel_time is None
    assert after_reset.average_speed_mps is None
    assert after_reset.throughput_vph is None
    assert after_reset.average_delay_s is None
    assert after_reset.maximum_delay_s is None
    assert after_reset.queue_length_veh is None
    assert after_reset.average_queue_length_by_approach == {}


def test_incremental_calculator_repeatedly_handles_empty_real_engine_history():
    engine = Engine(
        {"R": Segment(25.0, 10.0)},
        {("R", "straight"): ["R"]},
        [Vehicle(11, "R", "straight", 1.0)],
        duration=10.0,
    )
    calculator = IncrementalMetricsCalculator()

    first = calculator.calculate(engine)
    second = calculator.calculate(engine)

    assert first == second
    assert first.status == "Ready"
    assert first.simulated_time == pytest.approx(0.0)
    assert first.duration == pytest.approx(10.0)
    assert first.vehicles_generated == 0
    assert first.total_scheduled == 1
    assert first.vehicles_entered == 0
    assert first.vehicles_completed == 0
    assert first.vehicles_in_network == 0
    assert first.mean_travel_time is None
    assert first.average_speed_mps is None
    assert first.throughput_vph is None
    assert first.average_delay_s is None
    assert first.maximum_delay_s is None
    assert first.queue_length_veh is None
    assert first.average_queue_length_by_approach == {}


def test_out_of_order_lifecycle_events_expose_history_tracker_mismatch():
    events = [
        {"type": "exit", "time": 5.0, "vehicle_id": 7},
        {
            "type": "spawn",
            "time": 1.0,
            "vehicle_id": 7,
            "free_flow_time_s": 2.0,
        },
    ]
    engine = fake_engine(events, time=5.0)
    # The history tracker consumes the engine's legacy tuple event stream.
    engine.events = [(5.0, 7, "exit"), (1.0, 7, "spawn")]
    calculator = IncrementalMetricsCalculator()
    tracker = SimulationHistoryTracker()

    metrics = calculator.calculate(engine)
    tracker.record_state(engine)

    assert metrics.vehicles_completed == 1
    assert metrics.mean_travel_time == pytest.approx(4.0)
    assert metrics.average_delay_s == pytest.approx(2.0)
    assert tracker.completed_trips == []
    assert metrics.vehicles_completed != len(tracker.completed_trips)


def test_incremental_metrics_match_fixed_expectations_for_real_engine_run():
    engine = Engine(
        {"R": Segment(25.0, 10.0)},
        {("R", "straight"): ["R"]},
        [
            Vehicle(11, "R", "straight", 0.0),
            Vehicle(12, "R", "straight", 2.0),
        ],
        duration=10.0,
    )
    calculator = IncrementalMetricsCalculator()

    engine.start()
    engine.advance(1.0)
    calculator.calculate(engine)
    engine.advance(1.0)
    calculator.calculate(engine)
    engine.advance(8.0)
    actual = calculator.calculate(engine)

    # Fixed expectations from the deterministic two-vehicle, single-road run.
    assert actual.status == "Completed"
    assert actual.simulated_time == pytest.approx(10.0)
    assert actual.duration == pytest.approx(10.0)
    assert actual.vehicles_generated == 2
    assert actual.total_scheduled == 2
    assert actual.vehicles_entered == 2
    assert actual.vehicles_completed == 2
    assert actual.vehicles_in_network == 0
    assert actual.mean_travel_time == pytest.approx(2.0)
    assert actual.average_speed_mps == pytest.approx(10.0)
    assert actual.throughput_vph == pytest.approx(720.0)
    assert actual.average_delay_s == pytest.approx(0.0)
    assert actual.maximum_delay_s == pytest.approx(0.0)
    assert actual.queue_length_veh == pytest.approx(0.0)
    assert actual.average_queue_length_by_approach == {"R": 0.0}
