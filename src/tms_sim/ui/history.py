"""Scenario configuration undo/redo history manager.

Provides snapshot-based configuration history management for desktop workbench editing,
preserving network topology, properties, demand, and signal plans without storing
transient simulation engine state.
"""

from __future__ import annotations

import copy
from typing import Any


class ScenarioHistoryManager:
    """Manages undo and redo stacks of scenario configuration snapshots."""

    def __init__(
        self,
        initial_scenario: dict[str, Any] | None = None,
        max_history: int = 50,
    ) -> None:
        self.max_history = max_history
        self.undo_stack: list[tuple[dict[str, Any], str]] = []
        self.redo_stack: list[tuple[dict[str, Any], str]] = []
        if initial_scenario is not None:
            self.reset(initial_scenario)

    def reset(
        self,
        initial_scenario: dict[str, Any],
        description: str = "Initial state",
    ) -> None:
        """Reset history with a new baseline scenario."""
        self.undo_stack = [(copy.deepcopy(initial_scenario), description)]
        self.redo_stack.clear()

    def push(self, scenario: dict[str, Any], description: str = "") -> bool:
        """Record a new configuration snapshot if it differs from the current top of stack.

        Returns True if recorded, False if ignored as a duplicate.
        """
        if not self.undo_stack:
            self.undo_stack.append((copy.deepcopy(scenario), description))
            return True

        current_top, _ = self.undo_stack[-1]
        if scenario == current_top:
            return False

        self.undo_stack.append((copy.deepcopy(scenario), description))
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)

        self.redo_stack.clear()
        return True

    @property
    def can_undo(self) -> bool:
        """True if there is an earlier snapshot to restore."""
        return len(self.undo_stack) > 1

    @property
    def can_redo(self) -> bool:
        """True if there is an undone snapshot to restore."""
        return len(self.redo_stack) > 0

    @property
    def current_state(self) -> dict[str, Any] | None:
        """Return the current top configuration snapshot without mutating stacks."""
        if not self.undo_stack:
            return None
        return copy.deepcopy(self.undo_stack[-1][0])

    @property
    def undo_description(self) -> str:
        """Return description of the action that would be undone."""
        if not self.can_undo:
            return ""
        return self.undo_stack[-1][1]

    @property
    def redo_description(self) -> str:
        """Return description of the action that would be redone."""
        if not self.can_redo:
            return ""
        return self.redo_stack[-1][1]

    def undo(self) -> tuple[dict[str, Any], str] | None:
        """Undo the most recent edit.

        Returns (restored_scenario, undone_action_description) or None.
        """
        if not self.can_undo:
            return None

        current_entry = self.undo_stack.pop()
        self.redo_stack.append(current_entry)
        previous_scenario, _ = self.undo_stack[-1]
        undone_description = current_entry[1]
        return copy.deepcopy(previous_scenario), undone_description

    def redo(self) -> tuple[dict[str, Any], str] | None:
        """Redo the most recently undone edit.

        Returns (restored_scenario, redone_action_description) or None.
        """
        if not self.can_redo:
            return None

        entry_to_redo = self.redo_stack.pop()
        self.undo_stack.append(entry_to_redo)
        redone_scenario, redone_description = entry_to_redo
        return copy.deepcopy(redone_scenario), redone_description
