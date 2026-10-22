"""JSON load/save for the network. Only the "network" key of a scenario file is read."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .model import ControlType, Intersection, Network, Segment, TurningMovement

SCHEMA_VERSION = "1.0"


class NetworkFormatError(ValueError):
    """Input is structurally broken (not merely an invalid network)."""


def _obj(v, where):
    if not isinstance(v, dict):
        raise NetworkFormatError(f"{where} must be an object")
    return v


def _list(d, key):
    v = d.get(key, [])
    if not isinstance(v, list):
        raise NetworkFormatError(f"'{key}' must be a list")
    return v


def _str(d, key, where):
    v = d.get(key)
    if not isinstance(v, str) or not v:
        raise NetworkFormatError(f"{where}: missing or non-string '{key}'")
    return v


def _num(d, key, where, integer=False, optional=False):
    v = d.get(key)
    if v is None and optional:
        return None
    ok = isinstance(v, int) if integer else isinstance(v, (int, float))
    if not ok or isinstance(v, bool):
        raise NetworkFormatError(f"{where}: '{key}' must be {'an integer' if integer else 'a number'}")
    return v


def _position(d, where):
    p = d.get("position")
    if p is None:
        return None
    if (not isinstance(p, list) or len(p) != 2
            or any(isinstance(c, bool) or not isinstance(c, (int, float)) for c in p)):
        raise NetworkFormatError(f"{where}: 'position' must be [x, y]")
    return (p[0], p[1])


def network_from_dict(data) -> Network:
    data = _obj(data, "document")
    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise NetworkFormatError(f"unsupported schema_version {version!r}")
    net = _obj(data.get("network"), "'network'")

    intersections = []
    for raw in _list(net, "intersections"):
        w = "intersection"
        raw = _obj(raw, w)
        try:
            ct = ControlType(raw.get("control_type", ControlType.UNCONTROLLED.value))
        except ValueError:
            raise NetworkFormatError(f"intersection: unknown control_type {raw.get('control_type')!r}") from None
        intersections.append(Intersection(_str(raw, "id", w), _position(raw, w), ct))

    segments = []
    for raw in _list(net, "segments"):
        w = "segment"
        raw = _obj(raw, w)
        segments.append(Segment(
            _str(raw, "id", w), _str(raw, "from", w), _str(raw, "to", w),
            _num(raw, "length_m", w), _num(raw, "lane_count", w, integer=True),
            _num(raw, "speed_limit_mps", w, optional=True)))

    movements = []
    for raw in _list(net, "turning_movements"):
        w = "turning_movement"
        raw = _obj(raw, w)
        movements.append(TurningMovement(
            _str(raw, "id", w), _str(raw, "intersection", w),
            _str(raw, "from_segment", w), _str(raw, "to_segment", w)))

    return Network(intersections, segments, movements)


def network_to_dict(network: Network) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "network": {
            "intersections": [
                {"id": i.id, "position": list(i.position) if i.position is not None else None,
                 "control_type": ControlType(i.control_type).value}
                for i in network.intersections],
            "segments": [
                {"id": s.id, "from": s.from_intersection, "to": s.to_intersection,
                 "length_m": s.length_m, "lane_count": s.lane_count,
                 "speed_limit_mps": s.speed_limit_mps}
                for s in network.segments],
            "turning_movements": [
                {"id": m.id, "intersection": m.intersection,
                 "from_segment": m.from_segment, "to_segment": m.to_segment}
                for m in network.turning_movements],
        },
    }


def load_network(path) -> Network:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise NetworkFormatError(f"malformed JSON in {path}: {e}") from e
    return network_from_dict(data)


def save_network(network: Network, path) -> None:
    """Write atomically: temp file in the same directory, then replace."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(network_to_dict(network), f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
