import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # no display needed in CI


@pytest.fixture(autouse=True)
def isolate_default_scenario_store(tmp_path, monkeypatch):
    """Keep automatic UI run captures inside each test's temporary directory."""
    from tms_sim.storage import store

    monkeypatch.setattr(store, "default_db_path", lambda: tmp_path / "scenario-library.sqlite3")
