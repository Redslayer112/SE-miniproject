"""Automated tests for TMS-Sim Step 5A: Simulation Results and Metrics Dashboard.

Covers:
1. Dashboard initial state before a simulation starts.
2. Accurate generated, entered, completed, and in-network counts.
3. Mean travel time and its units.
4. Dashboard updates as simulation time advances.
5. Paused-state stability.
6. Manual-step refresh.
7. Reset clears run-specific results correctly.
8. Loading a different scenario clears stale results.
9. Completion preserves final metrics.
10. Empty or zero-vehicle runs do not crash or show misleading averages.
11. Dashboard values agree with CLI/backend calculations where comparable.
12. Network/demand edits refresh dashboard with newly rebuilt engine.
"""
from typing import cast
from tms_sim.sim import engine
from tms_sim.sim.engine import Engine
import copy
import json
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

from tms_sim.reporting.metrics import compute_metrics, SimulationMetrics
from tms_sim.ui.app import Workbench

SAMPLE_SCENARIO_PATH = (
    Path(__file__).resolve().parent / "data" / "scenario" / "small_valid_scenario.json"
)


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single QApplication instance exists for testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def workbench(qapp):
    """Provide a fresh Workbench instance for each test, closing it on teardown."""
    win = Workbench()
    yield win
    win.timer.stop()
    win.close()


def test_dashboard_initial_state_before_simulation(workbench):
    """Verify results dashboard starts in Ready state with zeroed counters and N/A averages."""
    assert workbench.metric_status_label.text() == "Ready"
    assert workbench.metric_time.text() == "0.0 s"
    assert "600.0 s" in workbench.metric_duration_label.text()
    assert workbench.vehicle_count_label.text() == "0"
    assert workbench.in_network_label.text() == "0"
    assert workbench.completed_label.text() == "0"
    assert workbench.entered_label.text() == "0"
    assert workbench.generated_label.text() == "0"
    assert workbench.mean_travel_time_label.text() == "N/A"
    assert workbench.throughput_label.text() == "Not available"
    assert "Not available" in workbench.queue_metric_label.text()
    assert "Not available" in workbench.delay_metric_label.text()


def test_dashboard_updates_as_simulation_advances(workbench):
    """Verify dashboard metrics and running status update as simulation steps advance."""
    workbench.start_simulation()
    assert workbench.metric_status_label.text() == "Running"
    assert workbench.engine.running is True

    # Advance several ticks
    for _ in range(10):
        workbench.advance_simulation()

    assert workbench.engine.time > 0.0
    sim_time = float(workbench.metric_time.text().replace(" s", ""))
    assert sim_time > 0.0
    assert workbench.metric_status_label.text() == "Running"


def test_paused_state_stability(workbench):
    """Verify metrics remain stable and unchanged when simulation is paused."""
    workbench.start_simulation()
    for _ in range(5):
        workbench.advance_simulation()
    workbench.pause_simulation()

    assert workbench.metric_status_label.text() == "Paused"
    paused_time = workbench.metric_time.text()
    paused_cars = workbench.vehicle_count_label.text()
    paused_completed = workbench.completed_label.text()

    # Repeated calls to update_metrics while paused do not alter values
    for _ in range(3):
        workbench.update_metrics()
        assert workbench.metric_status_label.text() == "Paused"
        assert workbench.metric_time.text() == paused_time
        assert workbench.vehicle_count_label.text() == paused_cars
        assert workbench.completed_label.text() == paused_completed


def test_manual_step_refresh(workbench):
    """Verify single-stepping updates time and dashboard values immediately."""
    assert workbench.engine.time == 0.0
    workbench.step_simulation()
    assert workbench.engine.time == workbench.engine.p.dt
    assert workbench.metric_time.text() == f"{workbench.engine.p.dt:.1f} s"
    assert workbench.metric_status_label.text() == "Paused"


def test_accurate_counts_and_travel_time(workbench):
    """Verify generated, entered, completed, in-network, and travel time against engine state."""
    # Run until at least some vehicles spawn and complete trips
    workbench.engine.start()
    while len(workbench.engine.exited) < 2 and not workbench.engine.finished:
        workbench.engine.step()
    workbench.update_metrics()

    # Recompute authoritative metrics from backend
    spawns = {e[1]: e[0] for e in workbench.engine.events if e[2] == "spawn"}
    exits = [e for e in workbench.engine.events if e[2] == "exit"]
    travel = [t - spawns[v] for t, v, *_ in exits if v in spawns]

    assert workbench.entered_label.text() == str(len(spawns))
    assert workbench.completed_label.text() == str(len(exits))
    assert workbench.vehicle_count_label.text() == str(len(workbench.engine.cars))

    expected_gen = sum(1 for v in workbench.engine.vehicles if v.depart_time <= workbench.engine.time)
    assert workbench.generated_label.text() == str(expected_gen)

    if travel:
        expected_mean = sum(travel) / len(travel)
        assert workbench.mean_travel_time_label.text() == f"{expected_mean:.1f} s"
        assert workbench.mean_travel_time_label.text().endswith(" s")


def test_reset_clears_run_specific_results(workbench):
    """Verify reset restores status, time, and counters to their initial state."""
    workbench.start_simulation()
    # Advance until time has elapsed
    for _ in range(20):
        workbench.advance_simulation()
    assert workbench.engine.time > 0.0

    workbench.reset_simulation()
    assert workbench.engine.time == 0.0
    assert workbench.metric_status_label.text() == "Ready"
    assert workbench.metric_time.text() == "0.0 s"
    assert workbench.vehicle_count_label.text() == "0"
    assert workbench.completed_label.text() == "0"
    assert workbench.entered_label.text() == "0"
    assert workbench.generated_label.text() == "0"
    assert workbench.mean_travel_time_label.text() == "N/A"


def test_loading_different_scenario_clears_stale_results(workbench, tmp_path):
    """Verify loading another scenario replaces all prior run results and updates duration."""
    # Run the current scenario for a bit
    workbench.start_simulation()
    for _ in range(15):
        workbench.advance_simulation()
    workbench.pause_simulation()
    assert workbench.engine.time > 0.0

    # Create a new scenario with duration = 300s
    doc = json.loads(SAMPLE_SCENARIO_PATH.read_text(encoding="utf-8"))
    doc["name"] = "Short Scenario 300s"
    doc["simulation"]["duration_s"] = 300.0
    new_path = tmp_path / "short_scenario.json"
    new_path.write_text(json.dumps(doc), encoding="utf-8")

    success = workbench.load_scenario_file(new_path)
    assert success is True

    assert workbench.metric_status_label.text() == "Ready"
    assert workbench.metric_time.text() == "0.0 s"
    assert "300.0 s" in workbench.metric_duration_label.text()
    assert workbench.vehicle_count_label.text() == "0"
    assert workbench.completed_label.text() == "0"
    assert workbench.entered_label.text() == "0"
    assert workbench.generated_label.text() == "0"
    assert workbench.mean_travel_time_label.text() == "N/A"


def test_completion_preserves_final_metrics(workbench):
    """Verify final metrics remain stable and visible after simulation reaches duration."""
    workbench.engine.start()
    workbench.engine.set_speed(4)
    while not workbench.engine.finished:
        workbench.engine.advance(workbench.engine.p.dt)
    workbench.update_metrics()

    assert workbench.engine.finished is True
    assert workbench.metric_status_label.text() == "Completed"
    assert workbench.metric_time.text() == f"{workbench.engine.duration:.1f} s"
    assert workbench.vehicle_count_label.text() == "0"
    assert int(workbench.completed_label.text()) > 0
    assert int(workbench.entered_label.text()) > 0
    assert workbench.mean_travel_time_label.text() != "N/A"
    assert workbench.mean_travel_time_label.text().endswith(" s")

    # Calling update_metrics again preserves finished state
    workbench.update_metrics()
    assert workbench.metric_status_label.text() == "Completed"


def test_empty_or_zero_vehicle_run_does_not_crash(workbench, tmp_path):
    """Verify zero-vehicle scenario does not cause division-by-zero or crash."""
    doc = json.loads(SAMPLE_SCENARIO_PATH.read_text(encoding="utf-8"))
    doc["demand"]["arrival_rates_vehicles_per_hour"] = {"R2": 0.0}
    doc["simulation"]["duration_s"] = 50.0
    empty_file = tmp_path / "zero_demand.json"
    empty_file.write_text(json.dumps(doc), encoding="utf-8")

    success = workbench.load_scenario_file(empty_file)
    assert success is True
    assert len(workbench.engine.vehicles) == 0

    workbench.engine.start()
    while not workbench.engine.finished:
        workbench.engine.step()
    workbench.update_metrics()

    assert workbench.metric_status_label.text() == "Completed"
    assert workbench.completed_label.text() == "0"
    assert workbench.entered_label.text() == "0"
    assert workbench.generated_label.text() == "0"
    assert workbench.vehicle_count_label.text() == "0"
    assert workbench.mean_travel_time_label.text() == "N/A"


def test_dashboard_agrees_with_cli_summary(workbench):
    """Verify completed dashboard values match authoritative CLI run output exactly."""
    # Run sample scenario completely
    workbench.engine.start()
    workbench.engine.set_speed(4)
    while not workbench.engine.finished:
        workbench.engine.advance(workbench.engine.p.dt)
    workbench.update_metrics()

    # Expected from sample CLI run:
    # simulated 600.0 s | generated 30 | entered 30 | completed 30 | in network 0
    # mean travel time 16.4 s
    assert workbench.metric_time.text() == "600.0 s"
    assert workbench.generated_label.text() == "30"
    assert workbench.entered_label.text() == "30"
    assert workbench.completed_label.text() == "30"
    assert workbench.vehicle_count_label.text() == "0"
    assert workbench.mean_travel_time_label.text() == "16.4 s"


def test_network_and_demand_edits_refresh_dashboard(workbench):
    """Verify editing demand updates the engine and resets metrics cleanly."""
    # Advance current engine
    workbench.step_simulation()
    assert workbench.engine.time > 0.0

    # Edit demand arrival rate
    workbench.combo_demand_segment.setCurrentText("R2")
    workbench.edit_demand_rate.setText("240.0")
    success = workbench.apply_demand_entry()
    assert success is True

    # Rebuilt engine should be fresh at t=0
    assert workbench.engine.time == 0.0
    assert workbench.metric_status_label.text() == "Ready"
    assert workbench.metric_time.text() == "0.0 s"
    assert workbench.vehicle_count_label.text() == "0"
    assert workbench.completed_label.text() == "0"


def test_compute_metrics_standalone():
    """Verify compute_metrics function directly with None and fresh/running engines."""
    # None engine
    m = compute_metrics(None)
    assert m.status == "Ready"
    assert m.simulated_time == 0.0
    assert m.vehicles_in_network == 0
    assert m.mean_travel_time is None
    assert m.throughput_vph is None
    assert m.queue_length_veh is None
    assert m.average_delay_s is None

def test_average_speed_metric():
    """Average speed is the mean speed of currently active vehicles."""
    from types import SimpleNamespace
    from typing import cast
    from tms_sim.reporting.metrics import compute_metrics
    from tms_sim.sim.engine import Engine

    engine = SimpleNamespace(
        finished=False,
        running=True,
        time=10.0,
        duration=100.0,
        vehicles=[],
        events=[],
        cars=[
            SimpleNamespace(v=4.0),
            SimpleNamespace(v=6.0),
        ],
    )

    metrics = compute_metrics(cast(Engine, engine))

    assert metrics.average_speed_mps == 5.0
    assert metrics.vehicles_in_network == 2


def test_average_speed_is_none_when_no_vehicles_are_active():
    """Average speed is unavailable when no vehicles are in the network."""
    from types import SimpleNamespace
    from typing import cast
    from tms_sim.reporting.metrics import compute_metrics
    from tms_sim.sim.engine import Engine

    engine = SimpleNamespace(
        finished=False,
        running=False,
        time=10.0,
        duration=100.0,
        vehicles=[],
        events=[],
        cars=[],
    )

    metrics = compute_metrics(cast(Engine, engine))

    assert metrics.average_speed_mps is None
    assert metrics.vehicles_in_network == 0
