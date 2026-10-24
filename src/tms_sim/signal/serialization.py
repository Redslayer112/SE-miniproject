"""JSON load/save for a signal plan. Only the "signal_plan" key of a scenario file is read.

Invalid values (zero green, NaN, ...) are kept so the validator can report them;
only broken structure raises SignalFormatError.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from tms_sim.network.serialization import NetworkFormatError, _list, _num, _obj, _str

from .model import SignalPhase, SignalPlan


class SignalFormatError(NetworkFormatError):
    """Input is structurally broken (not merely an invalid plan)."""


def plan_from_dict(data) -> SignalPlan:
    try:
        return _parse(data)
    except SignalFormatError:
        raise
    except NetworkFormatError as e:
        raise SignalFormatError(str(e)) from None


def _parse(data) -> SignalPlan:
    plan = _obj(_obj(data, "document").get("signal_plan"), "'signal_plan'")
    phases = []
    for raw in _list(plan, "phases"):
        w = "phase"
        raw = _obj(raw, w)
        ids = raw.get("movement_ids")
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise SignalFormatError(f"{w}: 'movement_ids' must be a list of strings")
        phases.append(SignalPhase(
            _num(raw, "order", w, integer=True), tuple(ids),
            _num(raw, "green_s", w), _num(raw, "yellow_s", w), _num(raw, "all_red_s", w)))
    return SignalPlan(_str(plan, "intersection_id", "signal_plan"), tuple(phases))


def plan_to_dict(plan: SignalPlan) -> dict:
    return {
        "signal_plan": {
            "intersection_id": plan.intersection_id,
            "phases": [
                {"order": p.order, "movement_ids": list(p.movement_ids),
                 "green_s": p.green_s, "yellow_s": p.yellow_s, "all_red_s": p.all_red_s}
                for p in plan.phases],
        },
    }


def load_signal_plan(path) -> SignalPlan:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise SignalFormatError(f"malformed JSON in {path}: {e}") from e
    return plan_from_dict(data)


def save_signal_plan(plan: SignalPlan, path) -> None:
    """Write atomically: temp file in the same directory, then replace."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(plan_to_dict(plan), f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
