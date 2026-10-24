import sys

from PySide6.QtWidgets import QApplication, QMainWindow


class Workbench(QMainWindow):
    """Blank workbench window; panels are added by the UI issues."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TMS-Sim")
        self.resize(1366, 768)  # SRS §2.4 minimum display


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    win = Workbench()
    win.show()
    return app.exec()
