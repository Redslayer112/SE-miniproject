
import math
from pathlib import Path

import pytest

from tms_sim.network import (
    ControlType,
    Intersection,
    Network,
    NetworkBlockedError,
    NetworkFormatError,
    NetworkService,
    Segment,
    TurningMovement,
    load_network,
    save_network,
    validate,
)

DATA = Path(__file__).parent / "data" / "network"


def codes(result):
    return {(e.code, e.element_type, e.element_id) for e in result.errors}


def test_valid_network():
    r = validate(load_network(DATA / "valid.json"))
    assert r.is_valid and r.errors == []
    assert [w.element_id for w in r.warnings] == ["R1"]  # R1 approaches I2, no movement


@pytest.mark.parametrize("fixture, expected", [
    ("disconnected", {("DISCONNECTED_GRAPH", "intersection", "I3")}),
    ("zero_lanes", {("ZERO_LANES", "segment", "R2")}),
    ("zero_length", {("ZERO_LENGTH", "segment", "R2")}),
    ("missing_receiving_lane", {
        ("ZERO_LANES", "segment", "R1"),
        ("NO_RECEIVING_LANE", "turning_movement", "TM1"),
    }),
])
def test_each_defect(fixture, expected):
    r = validate(load_network(DATA / f"{fixture}.json"))
    assert not r.is_valid
    assert codes(r) == expected
    assert all(e.message for e in r.errors)


def test_all_errors_listed():
    net = load_network(DATA / "valid.json")
    net.segments[0].length_m = 0
    net.segments[1].lane_count = 0
    net.intersections.append(Intersection("I9"))
    got = codes(validate(net))
    assert {
        ("ZERO_LENGTH", "segment", "R1"),
        ("ZERO_LANES", "segment", "R2"),
        ("DISCONNECTED_GRAPH", "intersection", "I9"),
    } <= got


def test_other_errors():
    net = load_network(DATA / "valid.json")
    net.segments[0].speed_limit_mps = None
    net.segments[1].speed_limit_mps = math.nan
    net.segments.append(Segment("R1", "I1", "I1", -5, 1, 10))
    net.segments.append(Segment("R3", "I1", "IX", 5, 1, 10))
    net.turning_movements.append(TurningMovement("TM2", "I2", "R2", "R9"))
    got = codes(validate(net))
    assert ("MISSING_SPEED_LIMIT", "segment", "R1") in got
    assert ("INVALID_SPEED_LIMIT", "segment", "R2") in got
    assert ("DUPLICATE_ID", "segment", "R1") in got
    assert ("SELF_LOOP", "segment", "R1") in got
    assert ("INVALID_LENGTH", "segment", "R1") in got
    assert ("UNKNOWN_INTERSECTION", "segment", "R3") in got
    assert ("UNKNOWN_SEGMENT", "turning_movement", "TM2") in got
    assert ("MOVEMENT_NOT_AT_INTERSECTION", "turning_movement", "TM2") in got


def test_booleans_rejected():
    net = load_network(DATA / "valid.json")
    net.segments[0].length_m = True
    net.segments[0].lane_count = True
    net.segments[1].speed_limit_mps = True
    got = codes(validate(net))
    assert ("INVALID_LENGTH", "segment", "R1") in got
    assert ("INVALID_LANE_COUNT", "segment", "R1") in got
    assert ("INVALID_SPEED_LIMIT", "segment", "R2") in got


def test_disconnected_reports_each_outside_intersection():
    net = load_network(DATA / "valid.json")
    net.intersections += [Intersection("I3"), Intersection("I4")]
    assert {e.element_id for e in validate(net).errors} == {"I3", "I4"}


def test_empty_network_blocked():
    assert validate(Network()).is_valid is False
    assert ("EMPTY_NETWORK", "network", "") in codes(validate(Network()))
    with pytest.raises(NetworkBlockedError):
        NetworkService(Network()).provide_network_state()


def test_round_trip(tmp_path):
    net = Network(
        [
            Intersection("A", (1.5, -2), ControlType.SIGNALIZED),
            Intersection("B", (10, 20), ControlType.YIELD_CONTROLLED),
            Intersection("C", None, ControlType.STOP_CONTROLLED),
            Intersection("D", (0, 0), ControlType.UNCONTROLLED),
        ],
        [
            Segment("S1", "A", "B", 123.4, 3, 13.9),
            Segment("S2", "B", "A", 50, 2, 8.3),
            Segment("S3", "B", "C", 70, 1, 9),
            Segment("S4", "C", "D", 70, 1, 9),
        ],
        [
            TurningMovement("T1", "B", "S1", "S2"),
            TurningMovement("T2", "B", "S1", "S3"),
        ],
    )
    p = tmp_path / "net.json"
    save_network(net, p)
    first = p.read_text()
    assert load_network(p) == net
    save_network(load_network(p), p)
    assert p.read_text() == first
    assert [f.name for f in tmp_path.iterdir()] == ["net.json"]


def test_loader_keeps_invalid_values_and_defaults(tmp_path):
    p = tmp_path / "n.json"
    p.write_text(
        '{"network": {"intersections": [{"id": "I1"}], '
        '"segments": [{"id": "R", "from": "I1", "to": "I1", '
        '"length_m": 0, "lane_count": 0}]}}'
    )
    net = load_network(p)
    assert net.intersections[0].control_type is ControlType.UNCONTROLLED
    assert net.intersections[0].position is None
    assert net.segments[0].speed_limit_mps is None
    assert net.segments[0].lane_count == 0


def test_loader_ignores_other_keys(tmp_path):
    p = tmp_path / "n.json"
    p.write_text(
        '{"schema_version": "1.0", "network": {}, '
        '"signal_plan": 5, "demand": [], "simulation": {}}'
    )
    assert load_network(p) == Network()


@pytest.mark.parametrize("text", [
    '{"schema_version": "2.0", "network": {}}',
    '{"network": {"intersections": [{"position": [0, 0]}]}}',
    '{"network": {"intersections": [{"id": "I", "control_type": "roundabout"}]}}',
    '{"network": {"segments": [{"id": "R", "from": "A", "to": "B", "length_m": "x", "lane_count": 1}]}}',
    '{"network": {"segments": [{"id": "R", "from": "A", "to": "B", "length_m": 1, "lane_count": 1.5}]}}',
    '{"network": []}',
    '[]',
])
def test_format_errors(tmp_path, text):
    p = tmp_path / "bad.json"
    p.write_text(text)
    with pytest.raises(NetworkFormatError):
        load_network(p)


def test_malformed_json():
    with pytest.raises(NetworkFormatError, match="malformed"):
        load_network(DATA / "malformed.json")


def test_service_valid():
    svc = NetworkService()
    net = svc.load_network(DATA / "valid.json")
    assert svc.validate_network().is_valid
    assert svc.provide_network_state() is net


@pytest.mark.parametrize(
    "fixture",
    ["disconnected", "zero_lanes", "zero_length", "missing_receiving_lane"],
)
def test_service_blocks_invalid(fixture):
    svc = NetworkService()
    svc.load_network(DATA / f"{fixture}.json")
    with pytest.raises(NetworkBlockedError) as exc:
        svc.provide_network_state()
    assert exc.value.errors


def test_service_blocks_when_not_loaded():
    svc = NetworkService()
    assert svc.validate_network().errors[0].code == "NETWORK_NOT_LOADED"
    with pytest.raises(NetworkBlockedError):
        svc.provide_network_state()


def test_service_camel_case_aliases():
    svc = NetworkService()
    net = svc.loadNetwork(DATA / "valid.json")
    assert svc.validateNetwork().is_valid
    assert svc.provideNetworkState() is net


# Additional regression tests for the validation fixes.


def test_empty_network_blocked():
    net = Network([], [], [])

    result = validate(net)

    assert not result.is_valid
    assert ("EMPTY_NETWORK", "network", "") in codes(result)


@pytest.mark.parametrize("value", [True, False])
def test_boolean_length_and_speed_are_invalid(value):
    net = load_network(DATA / "valid.json")
    net.segments[0].length_m = value
    net.segments[0].speed_limit_mps = value

    result = validate(net)
    got = codes(result)

    assert ("INVALID_LENGTH", "segment", "R1") in got
    assert ("INVALID_SPEED_LIMIT", "segment", "R1") in got


@pytest.mark.parametrize("value", [True, False])
def test_boolean_lane_count_is_invalid(value):
    net = load_network(DATA / "valid.json")
    net.segments[0].lane_count = value

    result = validate(net)

    assert ("INVALID_LANE_COUNT", "segment", "R1") in codes(result)
