"""Import and export complete, versioned TMS simulation scenarios."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from tms_sim.network.serialization import (
    SCHEMA_VERSION,
    network_from_dict,
)
from tms_sim.signal.serialization import plan_from_dict


class ScenarioFormatError(ValueError):
    """Raised when a scenario document is malformed or unsupported."""


def scenario_from_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a scenario document's structure and return a safe copy."""
    if not isinstance(data, dict):
        raise ScenarioFormatError("Scenario must be a JSON object.")

    if data.get("schema_version") != SCHEMA_VERSION:
        raise ScenarioFormatError(
            f"Unsupported or missing schema_version: {data.get('schema_version')!r}"
        )

    if not isinstance(data.get("network"), dict):
        raise ScenarioFormatError("Scenario must contain a network object.")

    try:
        # Reuse existing parsers for network and signal-plan structure.
        network_from_dict(data)

        has_single_plan = "signal_plan" in data
        has_multiple_plans = "signal_plans" in data

        if has_single_plan == has_multiple_plans:
            raise ScenarioFormatError(
                "Provide either signal_plan or signal_plans, but not both."
            )

        if has_single_plan:
            plans = [data["signal_plan"]]
        else:
            plans = data["signal_plans"]
            if not isinstance(plans, list) or not plans:
                raise ScenarioFormatError(
                    "signal_plans must be a non-empty list."
                )

        for plan in plans:
            plan_from_dict({"signal_plan": plan})

    except ScenarioFormatError:
        raise
    except (ValueError, TypeError, KeyError) as exc:
        raise ScenarioFormatError(f"Invalid scenario structure: {exc}") from exc

    demand = data.get("demand")
    if not isinstance(demand, dict):
        raise ScenarioFormatError("Scenario must contain a demand object.")

    if not isinstance(demand.get("arrival_rates_vehicles_per_hour"), dict):
        raise ScenarioFormatError(
            "demand.arrival_rates_vehicles_per_hour must be an object."
        )

    if not isinstance(demand.get("turning_ratios"), dict):
        raise ScenarioFormatError("demand.turning_ratios must be an object.")

    simulation = data.get("simulation")
    if not isinstance(simulation, dict):
        raise ScenarioFormatError("Scenario must contain a simulation object.")

    for field in ("seed", "duration_s", "time_step_s"):
        if field not in simulation:
            raise ScenarioFormatError(
                f"simulation is missing required field: {field}"
            )

    return deepcopy(data)


def scenario_to_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and serialize a complete scenario document."""
    return scenario_from_dict(data)


def load_scenario_document(path: str | Path) -> dict[str, Any]:
    """Load and validate a complete scenario JSON file."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScenarioFormatError(f"Could not read scenario JSON: {exc}") from exc

    return scenario_from_dict(data)


def save_scenario_document(
    data: dict[str, Any], path: str | Path
) -> None:
    """Save a validated scenario atomically as formatted JSON."""
    scenario = scenario_to_dict(data)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            json.dump(scenario, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
