"""Verify same-seed demand and simulation event repeatability."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tms_sim.reporting.metrics import compute_metrics
from tms_sim.sim.scenario import load_scenario


SCENARIO = ROOT / "fixtures/valid/performance_10_intersections.json"
OUTPUT = ROOT / "artifacts/dem_determinism_detail.json"


def run_once():
    engine = load_scenario(SCENARIO)
    engine.start()

    while not engine.finished:
        engine.step()

    metrics = compute_metrics(engine)

    # Capture every generated vehicle and its scheduled departure.
    demand = [
        {
            "id": vehicle.id,
            "entry": vehicle.entry,
            "movement": vehicle.movement,
            "depart_time": vehicle.depart_time,
        }
        for vehicle in engine.vehicles
    ]

    # Event tuple: (time, vehicle_id, "spawn" | "exit", segment_id).
    events = [
        {
            "time": event[0],
            "vehicle_id": event[1],
            "type": event[2],
            "segment_id": event[3],
        }
        for event in engine.events
    ]

    metric_values = {
        "status": metrics.status,
        "simulated_time": metrics.simulated_time,
        "duration": metrics.duration,
        "vehicles_generated": metrics.vehicles_generated,
        "total_scheduled": metrics.total_scheduled,
        "vehicles_entered": metrics.vehicles_entered,
        "vehicles_completed": metrics.vehicles_completed,
        "vehicles_in_network": metrics.vehicles_in_network,
        "mean_travel_time": metrics.mean_travel_time,
        "average_speed_mps": metrics.average_speed_mps,
        "throughput_vph": metrics.throughput_vph,
        "average_delay_s": metrics.average_delay_s,
        "queue_length_veh": metrics.queue_length_veh,
    }

    return {
        "seed": 42,
        "demand": demand,
        "events": events,
        "metrics": metric_values,
    }


def main():
    first = run_once()
    second = run_once()

    demand_match = first["demand"] == second["demand"]
    events_match = first["events"] == second["events"]
    metrics_match = first["metrics"] == second["metrics"]

    result = {
        "scenario": str(SCENARIO),
        "seed": 42,
        "runs_compared": 2,
        "demand_match": demand_match,
        "event_log_match": events_match,
        "metrics_match": metrics_match,
        "demand_vehicle_count": len(first["demand"]),
        "event_count_run_1": len(first["events"]),
        "event_count_run_2": len(second["events"]),
        "metrics_run_1": first["metrics"],
        "metrics_run_2": second["metrics"],
        "run_1": first,
        "run_2": second,
        "preliminary_result": (
            "PASS"
            if demand_match and events_match and metrics_match
            else "FAIL"
        ),
        "note": (
            "Compares scheduled vehicle demand, ordered spawn/exit events, "
            "and computed metrics between two independent runs."
        ),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print("Demand identical:", demand_match)
    print("Complete event logs identical:", events_match)
    print("Metrics identical:", metrics_match)
    print("Demand vehicles:", len(first["demand"]))
    print("Events in each run:", len(first["events"]), len(second["events"]))
    print("Preliminary result:", result["preliminary_result"])
    print("Evidence saved to:", OUTPUT)


if __name__ == "__main__":
    main()
