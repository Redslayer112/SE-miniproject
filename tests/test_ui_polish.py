"""Automated tests for TMS-Sim Step 5I: Desktop Workbench UI/UX Polish.

Covers:
1. Workbench minimum window size policy (preventing collapsed panels on resize).
2. Header toolbar layout completeness (btn_history present, grouping separators included).
3. Simulation playback controls formatting, button minimum widths, and alignment.
4. Comprehensive tooltips across properties, traffic demand, and signal plan inspector controls.
5. RoadCanvas responsive HUD and accessible signal legend rendering (color + text + letter indicators).
6. Modal dialog minimum sizes, responsiveness, and close button accessibility.
"""
from __future__ import annotations

from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QMessageBox, QPushButton

from tms_sim.reporting.comparison import SimulationRunRecord
from tms_sim.reporting.metrics import SimulationMetrics
from tms_sim.ui.app import Workbench
from tms_sim.ui.comparison import ScenarioComparisonDialog
from tms_sim.ui.run_history import RunDetailsDialog, SimulationRunHistoryDialog

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
def workbench(qapp, monkeypatch):
    """Provide a fresh Workbench instance for each test, mocking modal message boxes."""
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    win = Workbench(SAMPLE_SCENARIO_PATH)
    win.canvas.resize(800, 600)
    yield win
    win.timer.stop()
    win.close()

def test_workbench_minimum_size(workbench):
    """Verify Workbench enforces a minimum size policy of at least 980x620."""
    min_size = workbench.minimumSize()
    assert min_size.width() >= 980
    assert min_size.height() >= 620


def test_header_toolbar_includes_history_and_separators(workbench):
    """Verify btn_history is included in header toolbar layout alongside separators."""
    # Find header layout
    central = workbench.centralWidget()
    outer_layout = central.layout()
    header_layout = outer_layout.itemAt(0).layout()
    assert header_layout is not None

    # Collect widgets in header layout
    widgets = []
    for i in range(header_layout.count()):
        item = header_layout.itemAt(i)
        w = item.widget()
        if w is not None:
            widgets.append(w)

    assert workbench.btn_history in widgets
    assert workbench.btn_undo in widgets
    assert workbench.btn_redo in widgets
    assert workbench.btn_compare in widgets
    assert workbench.reset_view_button in widgets
    assert workbench.open_button in widgets
    assert workbench.save_button in widgets
    assert workbench.save_as_button in widgets

    # Verify vertical separator frames are present
    v_seps = [w for w in widgets if isinstance(w, QFrame) and w.frameShape() == QFrame.Shape.VLine]
    assert len(v_seps) >= 3


def test_simulation_controls_formatting_and_alignment(workbench):
    """Verify simulation transport buttons have minimum widths, and speed box and clock have tooltips/alignment."""
    assert workbench.btn_play.minimumWidth() >= 75
    assert workbench.btn_pause.minimumWidth() >= 75
    assert workbench.btn_step.minimumWidth() >= 75
    assert workbench.btn_reset.minimumWidth() >= 75

    assert workbench.speed_box.minimumWidth() >= 80
    assert bool(workbench.speed_box.toolTip())

    assert workbench.clock_label.minimumWidth() >= 150
    alignment = workbench.clock_label.alignment()
    assert bool(alignment & Qt.AlignmentFlag.AlignRight)


def test_inspector_and_demand_tooltips(workbench):
    """Verify form controls across property inspectors, demand, and signals have helpful tooltips."""
    # Intersection inspector
    assert bool(workbench.combo_inter_control.toolTip())
    assert bool(workbench.edit_inter_x.toolTip())
    assert bool(workbench.edit_inter_y.toolTip())

    # Road segment inspector
    assert bool(workbench.edit_seg_length.toolTip())
    assert bool(workbench.spin_seg_lanes.toolTip())
    assert bool(workbench.edit_seg_speed.toolTip())

    # Traffic demand
    assert bool(workbench.combo_demand_segment.toolTip())
    assert bool(workbench.edit_demand_rate.toolTip())

    # Signal plans
    assert bool(workbench.combo_signal_plan.toolTip())
    assert bool(workbench.spin_phase_order.toolTip())
    assert bool(workbench.edit_phase_green.toolTip())
    assert bool(workbench.edit_phase_yellow.toolTip())
    assert bool(workbench.edit_phase_all_red.toolTip())


def test_road_canvas_responsive_hud_narrow_and_wide(workbench):
    """Verify RoadCanvas renders cleanly without error under wide, medium, and narrow widths."""
    canvas = workbench.canvas

    # Render at standard wide size
    canvas.resize(800, 600)
    pix_wide = QPixmap(800, 600)
    canvas.render(pix_wide)

    # Render at medium size (480px width)
    canvas.resize(480, 400)
    pix_med = QPixmap(480, 400)
    canvas.render(pix_med)

    # Render at narrow width (320px width)
    canvas.resize(320, 300)
    pix_narrow = QPixmap(320, 300)
    canvas.render(pix_narrow)


def test_road_canvas_signal_legend_vertical_responsiveness(workbench):
    """Verify RoadCanvas renders properly when canvas height is constrained without crashing."""
    canvas = workbench.canvas

    # Constrained height (< 140px)
    canvas.resize(600, 120)
    pix_short = QPixmap(600, 120)
    canvas.render(pix_short)


def test_dialog_minimum_sizes_and_accessibility(workbench):
    """Verify RunDetailsDialog, SimulationRunHistoryDialog, and ScenarioComparisonDialog have minimum sizes and close button tooltips."""
    # 1. RunDetailsDialog
    sample_metrics = SimulationMetrics(
        status="Completed",
        simulated_time=60.0,
        duration=60.0,
        vehicles_generated=15,
        total_scheduled=15,
        vehicles_entered=12,
        vehicles_completed=10,
        vehicles_in_network=2,
        mean_travel_time=18.5,
    )
    rec = SimulationRunRecord(
        run_id="run-test",
        label="Test Run",
        scenario_name="Small Scenario",
        metrics=sample_metrics,
        timestamp="2026-10-26 10:00:00",
    )
    details_dlg = RunDetailsDialog(rec, parent=workbench)
    assert details_dlg.minimumWidth() >= 500
    assert details_dlg.minimumHeight() >= 350
    close_btns = [w for w in details_dlg.findChildren(QPushButton) if w.text() == "Close"]
    assert len(close_btns) == 1
    assert bool(close_btns[0].toolTip())

    # 2. SimulationRunHistoryDialog
    hist_dlg = SimulationRunHistoryDialog(workbench, parent=workbench)
    assert hist_dlg.minimumWidth() >= 600
    assert hist_dlg.minimumHeight() >= 400
    close_btns_hist = [w for w in hist_dlg.findChildren(QPushButton) if w.text() == "Close"]
    assert len(close_btns_hist) == 1
    assert bool(close_btns_hist[0].toolTip())

    # 3. ScenarioComparisonDialog
    comp_dlg = ScenarioComparisonDialog(workbench, parent=workbench)
    assert comp_dlg.minimumWidth() >= 600
    assert comp_dlg.minimumHeight() >= 400
    close_btns_comp = [w for w in comp_dlg.findChildren(QPushButton) if w.text() == "Close"]
    assert len(close_btns_comp) == 1
    assert bool(close_btns_comp[0].toolTip())
