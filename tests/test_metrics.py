"""Independent metric recomputation and boundary coverage for issue #10."""
from types import SimpleNamespace

import pytest

from tms_sim.reporting.metrics import compute_metrics


def fake_engine(events, *, time=2.0, finished=False, cars=(), vehicles=()):
    return SimpleNamespace(
        finished=finished, running=not finished, time=time, duration=10.0,
        vehicles=vehicles, cars=list(cars), segs={"A": object(), "B": object()},
        metric_events=events, events=[],
    )


def test_metrics_are_recomputed_from_lifecycle_and_measurement_events():
    events = [
        {"type": "spawn", "time": 0.0, "vehicle_id": 1, "free_flow_time_s": 8.0},
        {"type": "exit", "time": 12.0, "vehicle_id": 1, "free_flow_time_s": 8.0},
        {"type": "spawn", "time": 1.0, "vehicle_id": 2, "free_flow_time_s": 8.0},
        {"type": "sample", "time": 1.0, "dt": 1.0, "speed_distance_m": 10.0,
         "active_vehicle_time_s": 2.0, "queue_by_approach": {"A": 1}},
        {"type": "sample", "time": 2.0, "dt": 1.0, "speed_distance_m": 10.0,
         "active_vehicle_time_s": 2.0, "queue_by_approach": {}},
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


def test_incomplete_trip_is_counted_but_not_used_for_completed_trip_metrics():
    m = compute_metrics(fake_engine([
        {"type": "spawn", "time": 0.0, "vehicle_id": 7, "free_flow_time_s": 5.0},
        {"type": "sample", "time": 2.0, "dt": 2.0, "speed_distance_m": 4.0,
         "active_vehicle_time_s": 2.0, "queue_by_approach": {"A": 1}},
    ]))
    assert m.vehicles_entered == 1
    assert m.vehicles_completed == 0
    assert m.mean_travel_time is None
    assert m.average_delay_s is None
    assert m.maximum_delay_s is None
    assert m.average_speed_mps == pytest.approx(2.0)
    assert m.average_queue_length_by_approach["A"] == pytest.approx(1.0)
