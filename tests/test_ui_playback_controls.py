"""Automated tests for TMS-Sim Step 5C: Simulation Playback Controls.

Covers:
1. Initial playback state.
2. Play starts simulation advancement.
3. Pause stops advancement.
4. Resume continues from current time without reset.
5. Repeated Play does not create duplicate timers.
6. Step Forward advances exactly one engine step.
7. Step Forward works while paused.
8. Reset restores initial state and clears current-run chart history.
9. Speed options map to documented timer behavior.
10. Speed changes while paused apply on resume.
11. Speed changes do not alter configured simulation duration or dt.
12. Completed simulations cannot accidentally restart from stale state.
13. Completion updates the toolbar and disables inappropriate controls.
14. Scenario loading stops old playback and resets progress.
15. Network or demand edits cannot leave the old engine running.
16. Read-only timeline cannot alter engine time when seeking is unsupported.
17. Keyboard shortcuts toggle playback safely and ignore text inputs.
18. Clean GUI startup and shutdown in offscreen environment.
"""

from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit

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
    win = Workbench(SAMPLE_SCENARIO_PATH)
    yield win
    win.timer.stop()
    win.close()


def test_initial_playback_state(workbench):
    """Verify toolbar initial state: Play enabled, Pause/Reset disabled, Step enabled, progress at 0."""
    assert workbench.btn_play.isEnabled() is True
    assert "Play" in workbench.btn_play.text()
    assert workbench.btn_pause.isEnabled() is False
    assert workbench.btn_step.isEnabled() is True
    assert workbench.btn_reset.isEnabled() is False
    assert workbench.progress_bar.value() == 0
    assert "0.0%" in workbench.progress_bar.text()
    assert workbench.clock_label.text() == "Simulation time: 0.0 s"
    assert workbench.speed_box.currentText() == "1x"
    assert workbench.status_label.text() == "Ready"


def test_play_starts_simulation_advancement(workbench):
    """Verify Play starts the engine and the QTimer, updating button states and status."""
    workbench.start_simulation()

    assert workbench.engine.running is True
    assert workbench.timer.isActive() is True
    assert workbench.btn_play.isEnabled() is False
    assert workbench.btn_pause.isEnabled() is True
    assert workbench.btn_step.isEnabled() is False
    assert workbench.btn_reset.isEnabled() is True
    assert workbench.status_label.text() == "Simulation running"


def test_pause_stops_advancement(workbench):
    """Verify Pause stops automatic time advancement and preserves engine and history state."""
    workbench.start_simulation()
    # Advance two timer ticks
    workbench.advance_simulation()
    workbench.advance_simulation()
    current_time = workbench.engine.time

    workbench.pause_simulation()

    assert workbench.timer.isActive() is False
    assert workbench.engine.running is False
    assert workbench.engine.time == current_time
    assert workbench.btn_play.isEnabled() is True
    assert "Resume" in workbench.btn_play.text()
    assert workbench.btn_pause.isEnabled() is False
    assert workbench.btn_step.isEnabled() is True
    assert workbench.btn_reset.isEnabled() is True
    assert workbench.status_label.text() == "Simulation paused"


def test_resume_continues_from_current_time(workbench):
    """Verify resuming from paused state continues without resetting elapsed simulation time."""
    dt = workbench.engine.p.dt
    for _ in range(4):
        workbench.step_simulation()
    paused_time = workbench.engine.time
    assert paused_time == pytest.approx(4 * dt)

    # Resume
    workbench.start_simulation()
    assert workbench.timer.isActive() is True
    assert workbench.engine.running is True
    assert workbench.engine.time == pytest.approx(paused_time)

    # Advance 10 ticks (0.5s wall time at 1x)
    for _ in range(10):
        workbench.advance_simulation()
    assert workbench.engine.time > paused_time


def test_repeated_play_does_not_create_duplicate_timers(workbench):
    """Verify repeated Play calls do not start duplicate timers or change timer interval."""
    workbench.start_simulation()
    assert workbench.timer.isActive() is True
    interval = workbench.timer.interval()

    # Call play again while already running
    workbench.start_simulation()
    workbench.start_simulation()

    assert workbench.timer.isActive() is True
    assert workbench.timer.interval() == interval
    assert workbench.engine.running is True


def test_step_forward_advances_exactly_one_step(workbench):
    """Verify Step Forward advances simulation by exactly one engine dt."""
    dt = workbench.engine.p.dt
    assert workbench.engine.time == 0.0

    workbench.step_simulation()
    assert workbench.engine.time == pytest.approx(dt)

    workbench.step_simulation()
    assert workbench.engine.time == pytest.approx(2 * dt)
    assert workbench.status_label.text() == "Advanced one simulation step"


def test_step_forward_works_while_paused(workbench):
    """Verify Step Forward works correctly when simulation is paused without starting timer."""
    workbench.start_simulation()
    for _ in range(10):
        workbench.advance_simulation()
    workbench.pause_simulation()

    paused_time = workbench.engine.time
    dt = workbench.engine.p.dt

    workbench.step_simulation()
    assert workbench.timer.isActive() is False
    assert workbench.engine.running is False
    assert workbench.engine.time == pytest.approx(paused_time + dt)
    assert "Resume" in workbench.btn_play.text()
    assert workbench.btn_play.isEnabled() is True


def test_reset_restores_initial_state_and_clears_history(workbench):
    """Verify Reset restores simulation time, engine, history tracker, and controls to initial state."""
    workbench.start_simulation()
    for _ in range(20):
        workbench.advance_simulation()
    assert workbench.engine.time > 0.0

    workbench.reset_simulation()

    assert workbench.timer.isActive() is False
    assert workbench.engine.time == 0.0
    assert workbench.engine.running is False
    assert workbench.engine.finished is False
    assert len(workbench.history_tracker.samples) == 1
    assert workbench.history_tracker.samples[0].simulated_time == 0.0
    assert workbench.btn_play.isEnabled() is True
    assert "Play" in workbench.btn_play.text()
    assert workbench.btn_pause.isEnabled() is False
    assert workbench.btn_step.isEnabled() is True
    assert workbench.btn_reset.isEnabled() is False
    assert workbench.progress_bar.value() == 0
    assert workbench.status_label.text() == "Simulation reset"


def test_speed_options_map_to_engine_speed(workbench):
    """Verify speed combo box options map to engine speed multiplier."""
    expected_speeds = {"0.5x": 0.5, "1x": 1.0, "2x": 2.0, "4x": 4.0}
    for text, mult in expected_speeds.items():
        workbench.speed_box.setCurrentText(text)
        assert workbench.engine.speed == mult


def test_speed_changes_while_paused_apply_on_resume(workbench):
    """Verify speed change made during pause takes effect when simulation resumes."""
    workbench.pause_simulation()
    workbench.speed_box.setCurrentText("2x")
    assert workbench.engine.speed == 2.0

    # Resume and advance 10 ticks (0.5s wall time at 2x -> 1.0s simulated time)
    workbench.start_simulation()
    t_start = workbench.engine.time
    for _ in range(10):
        workbench.advance_simulation()
    simulated_elapsed = workbench.engine.time - t_start
    assert simulated_elapsed == pytest.approx(1.0, abs=0.1)


def test_speed_changes_do_not_alter_duration_or_dt(workbench):
    """Verify speed multipliers do not alter configured simulation duration or time-step dt."""
    orig_duration = workbench.engine.duration
    orig_dt = workbench.engine.p.dt

    for speed_text in ("0.5x", "1x", "2x", "4x"):
        workbench.speed_box.setCurrentText(speed_text)
        assert workbench.engine.duration == orig_duration
        assert workbench.engine.p.dt == orig_dt


def test_completed_simulations_cannot_accidentally_restart(workbench):
    """Verify finished simulation cannot restart playback without a reset."""
    workbench.engine.time = workbench.engine.duration
    workbench.engine.finished = True
    workbench.engine.running = False
    workbench.update_metrics()

    assert workbench.btn_play.isEnabled() is False
    assert workbench.btn_pause.isEnabled() is False
    assert workbench.btn_step.isEnabled() is False
    assert workbench.btn_reset.isEnabled() is True

    # Attempting to call start_simulation does not start timer
    workbench.start_simulation()
    assert workbench.timer.isActive() is False
    assert "Reset to run again" in workbench.status_label.text()


def test_completion_updates_toolbar_and_progress(workbench):
    """Verify reaching completion updates the progress bar to 100% and sets appropriate states."""
    # Fast forward to finished
    workbench.engine.time = workbench.engine.duration
    workbench.engine.finished = True
    workbench.engine.running = False
    workbench.update_metrics()

    assert workbench.progress_bar.value() == 1000
    assert "100.0%" in workbench.progress_bar.text()
    assert workbench.metric_status_label.text() == "Completed"
    assert workbench.btn_play.isEnabled() is False
    assert workbench.btn_reset.isEnabled() is True


def test_scenario_loading_stops_old_playback_and_resets_progress(workbench):
    """Verify loading a scenario file cancels ongoing playback and resets progress."""
    workbench.start_simulation()
    for _ in range(10):
        workbench.advance_simulation()
    assert workbench.timer.isActive() is True
    assert workbench.engine.time > 0.0

    # Reload scenario
    success = workbench.load_scenario_file(SAMPLE_SCENARIO_PATH)
    assert success is True
    assert workbench.timer.isActive() is False
    assert workbench.engine.time == 0.0
    assert workbench.progress_bar.value() == 0
    assert "Play" in workbench.btn_play.text()
    assert workbench.btn_play.isEnabled() is True
    assert workbench.btn_reset.isEnabled() is False


def test_network_edits_stop_old_engine_and_reset_playback(workbench):
    """Verify network modifications stop the running timer and rebuild the engine cleanly."""
    workbench.start_simulation()
    for _ in range(10):
        workbench.advance_simulation()
    assert workbench.timer.isActive() is True

    workbench.on_network_modified()

    assert workbench.timer.isActive() is False
    assert workbench.engine.time == 0.0
    assert workbench.progress_bar.value() == 0
    assert workbench.btn_play.isEnabled() is True
    assert workbench.btn_reset.isEnabled() is False


def test_read_only_timeline_progress_bar_cannot_seek(workbench):
    """Verify playback progress bar is a read-only progress indicator and has no seeking signal."""
    # QProgressBar does not emit user-driven sliderMoved or sliderPressed signals
    assert not hasattr(workbench.progress_bar, "sliderMoved")
    assert not hasattr(workbench.progress_bar, "sliderPressed")
    assert workbench.progress_bar.maximum() == 1000
    assert workbench.progress_bar.minimum() == 0


def test_keyboard_shortcuts_ignored_during_text_entry(workbench, qapp):
    """Verify keyboard shortcuts (Space, S, R) do not trigger playback actions when typing in a QLineEdit."""
    workbench.show()
    qapp.processEvents()
    workbench.edit_demand_rate.setFocus()
    qapp.processEvents()

    # Initial state
    assert workbench.engine.time == 0.0
    assert workbench.engine.running is False

    # Simulate shortcut handlers when focus is on a text field
    workbench._shortcut_toggle_play_pause()
    assert workbench.engine.running is False

    workbench._shortcut_step()
    assert workbench.engine.time == 0.0

    workbench._shortcut_reset()
    assert workbench.engine.time == 0.0


def test_keyboard_shortcuts_trigger_when_not_focused_on_input(workbench):
    """Verify keyboard shortcut handlers control simulation when focus is clear."""
    workbench.canvas.setFocus()

    # Space triggers Play
    workbench._shortcut_toggle_play_pause()
    assert workbench.engine.running is True
    assert workbench.timer.isActive() is True

    # Space triggers Pause
    workbench._shortcut_toggle_play_pause()
    assert workbench.engine.running is False
    assert workbench.timer.isActive() is False

    # S triggers Step
    t0 = workbench.engine.time
    workbench._shortcut_step()
    assert workbench.engine.time == pytest.approx(t0 + workbench.engine.p.dt)

    # R triggers Reset
    workbench._shortcut_reset()
    assert workbench.engine.time == 0.0


def test_gui_startup_and_shutdown_smoke(qapp):
    """Verify GUI startup, event processing, and clean shutdown without warnings or crashes."""
    win = Workbench(SAMPLE_SCENARIO_PATH)
    win.show()
    qapp.processEvents()
    win.close()
