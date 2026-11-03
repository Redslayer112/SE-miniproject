import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # no display needed in CI


@pytest.fixture(autouse=True)
def isolate_default_scenario_store(tmp_path, monkeypatch):
    """Keep automatic UI run captures inside each test's temporary directory."""
    from tms_sim.storage import store

    monkeypatch.setattr(store, "default_db_path", lambda: tmp_path / "scenario-library.sqlite3")


def _destroy_qt_windows():
    """Close and delete every top-level Qt widget now, while the QApplication still exists.

    Left alone, these widgets are destroyed during interpreter shutdown after the
    QApplication, which is the classic PySide6 access violation (0xC0000005) seen on
    Windows CI after all tests had passed (issue #12 defect log).
    """
    import sys

    if "PySide6.QtWidgets" not in sys.modules:  # pure-logic tests never touch Qt
        return
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.fixture(autouse=True)
def destroy_qt_windows_after_test():
    yield
    _destroy_qt_windows()


def pytest_sessionfinish(session, exitstatus):
    import gc

    _destroy_qt_windows()
    gc.collect()
