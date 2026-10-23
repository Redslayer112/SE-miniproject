from PySide6.QtWidgets import QApplication

from tms_sim.ui.app import Workbench


def test_workbench_opens():
    app = QApplication.instance() or QApplication([])
    win = Workbench()
    win.show()
    assert win.windowTitle() == "TMS-Sim"
    assert win.isVisible()
    win.close()
    assert app is not None
