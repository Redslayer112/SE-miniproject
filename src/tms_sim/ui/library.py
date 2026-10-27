"""Scenario Library dialog (TMS-F-060): save, list, load, duplicate, rename, delete, import, export.

Every action takes its inputs as optional arguments and only prompts when they are missing,
so it can be driven from tests without dialogs. Errors are shown, never swallowed.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QInputDialog, QListWidget, QMessageBox, QPushButton, QVBoxLayout,
)

from tms_sim.sim.serialization import ScenarioFormatError
from tms_sim.storage.store import ScenarioStore, ScenarioStoreError


class ScenarioLibraryDialog(QDialog):
    def __init__(self, workbench, db_path=None):
        super().__init__(workbench)
        self.workbench = workbench
        self.store = ScenarioStore(db_path)
        self.setWindowTitle("Scenario Library")
        self.resize(420, 360)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self.load_selected())
        buttons = QHBoxLayout()
        for text, slot in [("Save current…", self.save_current), ("Load", self.load_selected),
                           ("Duplicate…", self.duplicate_selected), ("Rename…", self.rename_selected),
                           ("Delete", self.delete_selected)]:
            b = QPushButton(text)
            b.clicked.connect(lambda checked=False, f=slot: f())
            buttons.addWidget(b)
        files = QHBoxLayout()
        for text, slot in [("Import JSON…", self.import_file), ("Export JSON…", self.export_selected)]:
            b = QPushButton(text)
            b.clicked.connect(lambda checked=False, f=slot: f())
            files.addWidget(b)
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addLayout(buttons)
        layout.addLayout(files)
        self.refresh()

    def refresh(self):
        self.list.clear()
        self.list.addItems(self.store.list_scenarios())

    def selected(self) -> str | None:
        item = self.list.currentItem()
        return item.text() if item else None

    def select(self, name: str):
        for i in range(self.list.count()):
            if self.list.item(i).text() == name:
                self.list.setCurrentRow(i)

    # ---- actions ----
    def save_current(self, name: str | None = None, overwrite: bool | None = None) -> bool:
        name = name or self._ask("Save to library", "Scenario name:", self._default_name())
        if not name:
            return False
        try:
            self.store.save_scenario(name, self.workbench.scenario_data, overwrite=bool(overwrite))
        except ScenarioStoreError as exc:
            if overwrite is None and "already exists" in str(exc) and self._confirm(f"Replace '{name}'?"):
                return self.save_current(name, overwrite=True)
            return self._fail(exc)
        except ScenarioFormatError as exc:
            return self._fail(f"The current scenario is invalid and was not saved:\n\n{exc}")
        self._done(f"Saved '{name}' to the library", name)
        return True

    def load_selected(self, name: str | None = None) -> bool:
        name = name or self.selected()
        if not name or not self.workbench.maybe_save_changes():
            return False
        try:
            document = self.store.load_scenario(name)
        except ScenarioStoreError as exc:
            return self._fail(exc)
        return self.workbench.load_scenario_data(document, name)

    def duplicate_selected(self, new_name: str | None = None) -> bool:
        name = self.selected()
        new_name = name and (new_name or self._ask("Duplicate", "New name:", f"{name} (copy)"))
        return bool(new_name) and self._try(lambda: self.store.duplicate_scenario(name, new_name),
                                            f"Duplicated '{name}' as '{new_name}'", new_name)

    def rename_selected(self, new_name: str | None = None) -> bool:
        name = self.selected()
        new_name = name and (new_name or self._ask("Rename", "New name:", name))
        return bool(new_name) and self._try(lambda: self.store.rename_scenario(name, new_name),
                                            f"Renamed '{name}' to '{new_name}'", new_name)

    def delete_selected(self, confirm: bool | None = None) -> bool:
        name = self.selected()
        if not name or not (confirm if confirm is not None else self._confirm(f"Delete '{name}' from the library?")):
            return False
        return self._try(lambda: self.store.delete_scenario(name), f"Deleted '{name}'")

    def import_file(self, path: str | Path | None = None) -> bool:
        path = path or QFileDialog.getOpenFileName(self, "Import Scenario", "", "JSON Files (*.json)")[0]
        if not path:
            return False
        name = Path(path).stem
        return self._try(lambda: self.store.import_scenario(path, name), f"Imported '{name}'", name)

    def export_selected(self, path: str | Path | None = None) -> bool:
        name = self.selected()
        if not name:
            return False
        path = path or QFileDialog.getSaveFileName(self, "Export Scenario", f"{name}.json", "JSON Files (*.json)")[0]
        return bool(path) and self._try(lambda: self.store.export_scenario(name, path), f"Exported '{name}'")

    # ---- helpers ----
    def _try(self, op, message: str, select: str | None = None) -> bool:
        try:
            op()
        except (ScenarioStoreError, ScenarioFormatError, OSError) as exc:
            return self._fail(exc)
        self._done(message, select)
        return True

    def _done(self, message: str, select: str | None = None):
        self.refresh()
        if select:
            self.select(select)
        self.workbench.status_label.setText(message)

    def _fail(self, exc) -> bool:
        self.last_error = str(exc)
        QMessageBox.warning(self, "Scenario Library", str(exc))
        return False

    def _ask(self, title, label, default) -> str | None:
        text, ok = QInputDialog.getText(self, title, label, text=default)
        return text.strip() if ok and text.strip() else None

    def _confirm(self, question: str) -> bool:
        return QMessageBox.question(self, "Scenario Library", question) == QMessageBox.StandardButton.Yes

    def _default_name(self) -> str:
        path = getattr(self.workbench, "scenario_path", None)
        return (self.workbench.scenario_data or {}).get("name") or (path.stem if path else "scenario")

    def closeEvent(self, event):
        self.store.close()
        super().closeEvent(event)
