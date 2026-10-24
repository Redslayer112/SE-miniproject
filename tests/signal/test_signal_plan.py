import dataclasses
import math
from pathlib import Path

import pytest

from tms_sim.network import ControlType, Intersection, TurningMovement
from tms_sim.signal import (
    SignalFormatError, SignalPhase, SignalPlan, SignalPlanBlockedError, SignalService,
    load_signal_plan, movements_conflict, save_signal_plan, validate_signal_plan)

DATA = Path(__file__).parent.parent / "data" / "signal"


def phase(order=1, ids=("SN", "NS"), green=20, yellow=3, all_red=1):
    return SignalPhase(order, list(ids), green, yellow, all_red)


def plan(*phases, iid="X"):
    return SignalPlan(iid, list(phases))


def errors(result):
    return {(e.code, e.element_type, e.element_id) for e in result.errors}


def move(network, mid):
    return next(m for m in network.turning_movements if m.id == mid)


# --- valid plans ---------------------------------------------------------

def test_valid_two_phase_plan(network):
    p = plan(phase(1, ("SN", "NS")), phase(2, ("WE", "EW")))
    r = validate_signal_plan(p, network)
    assert r.is_valid and r.errors == []
    assert {w.code for w in r.warnings} == {"UNSERVED_MOVEMENT"}
    assert len(r.warnings) == 8  # the 8 turning movements are not in any phase
    assert p.cycle_time_s == 24 + 24


def test_zero_yellow_and_all_red_are_allowed(network):
    assert validate_signal_plan(plan(phase(yellow=0, all_red=0)), network).is_valid


def test_plan_is_immutable():
    p = plan(phase())
    assert isinstance(p.phases, tuple) and isinstance(p.phases[0].movement_ids, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.phases[0].green_s = 99


# --- timing defects, one at a time ---------------------------------------

@pytest.mark.parametrize("kwargs, code", [
    ({"green": 0}, "INVALID_GREEN"),
    ({"green": -5}, "INVALID_GREEN"),
    ({"green": "20"}, "INVALID_GREEN"),
    ({"green": True}, "INVALID_GREEN"),
    ({"green": math.nan}, "INVALID_GREEN"),
    ({"green": math.inf}, "INVALID_GREEN"),
    ({"yellow": -1}, "INVALID_YELLOW"),
    ({"yellow": None}, "INVALID_YELLOW"),
    ({"yellow": math.nan}, "INVALID_YELLOW"),
    ({"all_red": -0.5}, "INVALID_ALL_RED"),
    ({"all_red": "1"}, "INVALID_ALL_RED"),
    ({"all_red": -math.inf}, "INVALID_ALL_RED"),
])
def test_timing_defect(network, kwargs, code):
    r = validate_signal_plan(plan(phase(**kwargs)), network)
    assert errors(r) == {(code, "signal_phase", "X:1")}
    assert "phase 1" in r.errors[0].message


# --- structural defects, one at a time -----------------------------------

def test_unknown_intersection(network):
    r = validate_signal_plan(plan(phase(), iid="Q"), network)
    assert ("UNKNOWN_INTERSECTION", "signal_plan", "Q") in errors(r)


def test_not_signalized(network):
    network.intersections[0] = Intersection("X", (0, 0), ControlType.STOP_CONTROLLED)
    assert errors(validate_signal_plan(plan(phase()), network)) == {("NOT_SIGNALIZED", "signal_plan", "X")}


def test_no_phases(network):
    assert errors(validate_signal_plan(plan(), network)) == {("NO_PHASES", "signal_plan", "X")}


def test_duplicate_phase_order(network):
    r = validate_signal_plan(plan(phase(1, ("SN",)), phase(1, ("WE",))), network)
    assert errors(r) == {("DUPLICATE_PHASE_ORDER", "signal_phase", "X:1")}


@pytest.mark.parametrize("order", [0, -2, 1.5, "1", True])
def test_invalid_phase_order(network, order):
    r = validate_signal_plan(plan(phase(order)), network)
    assert errors(r) == {("INVALID_PHASE_ORDER", "signal_phase", f"X:{order}")}


def test_empty_phase(network):
    assert errors(validate_signal_plan(plan(phase(ids=())), network)) == {("EMPTY_PHASE", "signal_phase", "X:1")}


def test_unknown_movement(network):
    r = validate_signal_plan(plan(phase(ids=("SN", "ZZ"))), network)
    assert errors(r) == {("UNKNOWN_MOVEMENT", "turning_movement", "ZZ")}


def test_movement_of_other_intersection(network):
    network.turning_movements[0].intersection = "N"
    r = validate_signal_plan(plan(phase(ids=("SN", "NS"))), network)  # SN is the first movement
    assert errors(r) == {("MOVEMENT_WRONG_INTERSECTION", "turning_movement", "SN")}


def test_duplicate_movement_in_phase(network):
    r = validate_signal_plan(plan(phase(ids=("SN", "SN"))), network)
    assert errors(r) == {("DUPLICATE_MOVEMENT_IN_PHASE", "signal_phase", "X:1")}


# --- conflicts -----------------------------------------------------------

@pytest.mark.parametrize("a, b, expected", [
    ("SN", "NS", False),  # opposing through
    ("WE", "EW", False),
    ("SN", "WE", True),   # perpendicular through
    ("NS", "EW", True),
    ("SE", "NS", True),   # right turn across oncoming through (left-hand traffic)
    ("SW", "NS", False),  # left turn does not cross oncoming through
    ("SN", "SE", False),  # same approach
    ("SW", "SN", False),
    ("SN", "WN", True),   # merge into N_out
    ("EW", "NW", True),
])
def test_conflict_rule(network, a, b, expected):
    assert movements_conflict(network, move(network, a), move(network, b)) is expected
    assert movements_conflict(network, move(network, b), move(network, a)) is expected


def test_conflict_reported_once_with_both_ids_and_phase(network):
    r = validate_signal_plan(plan(phase(1, ("SN", "NS")), phase(2, ("SN", "WE", "EW"))), network)
    assert errors(r) == {("CONFLICTING_MOVEMENTS", "signal_phase", "X:2")}
    conflicts = [e for e in r.errors if e.code == "CONFLICTING_MOVEMENTS"]
    assert len(conflicts) == 2  # SN/WE and SN/EW; WE/EW do not conflict
    assert all("phase 2" in e.message for e in conflicts)
    assert any("'SN'" in e.message and "'WE'" in e.message for e in conflicts)


def test_conflict_check_unavailable_without_positions(network):
    network.intersections[1].position = None  # neighbour N
    r = validate_signal_plan(plan(phase(ids=("SN", "WE"))), network)
    assert errors(r) == {("CONFLICT_CHECK_UNAVAILABLE", "signal_plan", "X")}
    assert not r.is_valid


def test_missing_position_does_not_matter_when_no_geometry_is_needed(network):
    network.intersections[0].position = None
    assert validate_signal_plan(plan(phase(ids=("SN", "SE"))), network).is_valid  # same approach


# --- error reporting -----------------------------------------------------

def test_all_errors_listed(network):
    p = plan(phase(1, ("SN", "WE"), green=0), phase(1, ("ZZ",), yellow=-1), phase(3, ()))
    got = errors(validate_signal_plan(p, network))
    assert got == {
        ("INVALID_GREEN", "signal_phase", "X:1"),
        ("CONFLICTING_MOVEMENTS", "signal_phase", "X:1"),
        ("DUPLICATE_PHASE_ORDER", "signal_phase", "X:1"),
        ("INVALID_YELLOW", "signal_phase", "X:1"),
        ("UNKNOWN_MOVEMENT", "turning_movement", "ZZ"),
        ("EMPTY_PHASE", "signal_phase", "X:3"),
    }


def test_every_error_has_a_message(network):
    r = validate_signal_plan(plan(phase(0, ("ZZ", "ZZ"), green=-1)), network)
    assert r.errors and all(e.message and e.element_id for e in r.errors)


# --- files ---------------------------------------------------------------

def test_round_trip(tmp_path):
    p = plan(phase(1, ("SN", "NS"), 20.5, 3, 1), phase(2, ("WE",), 10, 0, 0))
    f = tmp_path / "plan.json"
    save_signal_plan(p, f)
    first = f.read_text()
    assert load_signal_plan(f) == p
    save_signal_plan(load_signal_plan(f), f)
    assert f.read_text() == first
    assert [x.name for x in tmp_path.iterdir()] == ["plan.json"]
    assert first.index('"intersection_id"') < first.index('"phases"') < first.index('"green_s"')


def test_loader_reads_only_signal_plan_key(network):
    p = load_signal_plan(DATA / "valid_plan.json")
    assert p.intersection_id == "X" and [x.order for x in p.phases] == [1, 2]
    assert validate_signal_plan(p, network).is_valid


def test_loader_keeps_invalid_values(tmp_path):
    f = tmp_path / "p.json"
    f.write_text('{"signal_plan": {"intersection_id": "X", "phases": [{"order": 0, "movement_ids": [], '
                 '"green_s": -3, "yellow_s": NaN, "all_red_s": 0}]}}')
    ph = load_signal_plan(f).phases[0]
    assert (ph.order, ph.movement_ids, ph.green_s) == (0, (), -3) and math.isnan(ph.yellow_s)


def test_invalid_fixture_reports_each_defect(network):
    r = validate_signal_plan(load_signal_plan(DATA / "invalid_plan.json"), network)
    assert errors(r) == {
        ("INVALID_GREEN", "signal_phase", "X:1"),
        ("CONFLICTING_MOVEMENTS", "signal_phase", "X:1"),
        ("INVALID_YELLOW", "signal_phase", "X:2"),
        ("UNKNOWN_MOVEMENT", "turning_movement", "NOPE"),
    }


@pytest.mark.parametrize("text", [
    '[]',
    '{}',
    '{"signal_plan": []}',
    '{"signal_plan": {"phases": []}}',
    '{"signal_plan": {"intersection_id": "", "phases": []}}',
    '{"signal_plan": {"intersection_id": "X", "phases": {}}}',
    '{"signal_plan": {"intersection_id": "X", "phases": [5]}}',
    '{"signal_plan": {"intersection_id": "X", "phases": [{"order": 1, "green_s": 5, "yellow_s": 0, "all_red_s": 0}]}}',
    '{"signal_plan": {"intersection_id": "X", "phases": [{"order": 1, "movement_ids": "SN", "green_s": 5, "yellow_s": 0, "all_red_s": 0}]}}',
    '{"signal_plan": {"intersection_id": "X", "phases": [{"order": 1, "movement_ids": [1], "green_s": 5, "yellow_s": 0, "all_red_s": 0}]}}',
    '{"signal_plan": {"intersection_id": "X", "phases": [{"order": 1.5, "movement_ids": [], "green_s": 5, "yellow_s": 0, "all_red_s": 0}]}}',
    '{"signal_plan": {"intersection_id": "X", "phases": [{"order": 1, "movement_ids": [], "green_s": "5", "yellow_s": 0, "all_red_s": 0}]}}',
    '{"signal_plan": {"intersection_id": "X", "phases": [{"order": 1, "movement_ids": [], "green_s": 5, "yellow_s": 0}]}}',
])
def test_format_errors(tmp_path, text):
    f = tmp_path / "bad.json"
    f.write_text(text)
    with pytest.raises(SignalFormatError):
        load_signal_plan(f)


def test_malformed_json(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("{not json")
    with pytest.raises(SignalFormatError, match="malformed"):
        load_signal_plan(f)


# --- service -------------------------------------------------------------

def test_service_provides_valid_plan(network):
    svc = SignalService()
    p = plan(phase())
    assert svc.validate_signal_plan(p, network).is_valid
    svc.set_signal_plan(p, network)
    got = svc.provide_signal_plan("X")
    assert got == p
    with pytest.raises(dataclasses.FrozenInstanceError):
        got.intersection_id = "Y"
    with pytest.raises(AttributeError):
        got.phases.append(phase(2))


def test_service_blocks_invalid_plan(network):
    svc = SignalService()
    with pytest.raises(SignalPlanBlockedError) as exc:
        svc.set_signal_plan(plan(phase(1, ("SN", "WE"), green=0)), network)
    assert {e.code for e in exc.value.errors} == {"INVALID_GREEN", "CONFLICTING_MOVEMENTS"}
    with pytest.raises(SignalPlanBlockedError):  # nothing was stored
        svc.provide_signal_plan("X")


def test_invalid_replacement_keeps_old_plan(network):
    svc = SignalService()
    good = plan(phase())
    svc.set_signal_plan(good, network)
    with pytest.raises(SignalPlanBlockedError):
        svc.set_signal_plan(plan(phase(green=0)), network)
    assert svc.provide_signal_plan("X") == good


def test_service_missing_plan():
    with pytest.raises(SignalPlanBlockedError) as exc:
        SignalService().provide_signal_plan("X")
    assert [e.code for e in exc.value.errors] == ["SIGNAL_PLAN_NOT_SET"]


def test_service_camel_case_aliases(network):
    svc = SignalService()
    p = plan(phase())
    assert svc.validateSignalPlan(p, network).is_valid
    svc.set_signal_plan(p, network)
    assert svc.provideSignalPlan("X") == p


# --- network changes after set_signal_plan ---------------------------------

def _change_lane_count(n):
    n.segments[0].lane_count = 3


def _add_segment(n):
    n.segments.append(dataclasses.replace(n.segments[0], id="extra"))


def _remove_movement(n):
    n.turning_movements.pop()


def _change_control_type(n):
    n.intersections[1].control_type = ControlType.SIGNALIZED


@pytest.mark.parametrize("change", [_change_lane_count, _add_segment, _remove_movement, _change_control_type])
def test_network_change_blocks_provide(network, change):
    svc = SignalService()
    svc.set_signal_plan(plan(phase()), network)
    change(network)
    with pytest.raises(SignalPlanBlockedError) as exc:
        svc.provide_signal_plan("X")
    [issue] = exc.value.errors
    assert (issue.code, issue.element_type, issue.element_id) == (
        "NETWORK_CHANGED_SINCE_VALIDATION", "signal_plan", "X")
    assert "set_signal_plan" in issue.message


def test_unchanged_network_provides_plan(network):
    svc = SignalService()
    p = plan(phase())
    svc.set_signal_plan(p, network)
    assert svc.provide_signal_plan("X") == p
    assert svc.provide_signal_plan("X") == p


def test_set_again_after_change_unblocks(network):
    svc = SignalService()
    p = plan(phase())
    svc.set_signal_plan(p, network)
    _change_lane_count(network)
    with pytest.raises(SignalPlanBlockedError):
        svc.provide_signal_plan("X")
    svc.set_signal_plan(p, network)
    assert svc.provide_signal_plan("X") == p


def test_network_change_blocks_every_plan_until_each_is_set_again(network):
    network.intersections[1].control_type = ControlType.SIGNALIZED  # N
    network.turning_movements.append(TurningMovement("NN", "N", "N_out", "N_in"))
    svc = SignalService()
    px, pn = plan(phase()), plan(phase(1, ("NN",)), iid="N")
    svc.set_signal_plan(px, network)
    svc.set_signal_plan(pn, network)
    _change_lane_count(network)
    for iid in ("X", "N"):
        with pytest.raises(SignalPlanBlockedError):
            svc.provide_signal_plan(iid)
    svc.set_signal_plan(px, network)
    assert svc.provide_signal_plan("X") == px
    with pytest.raises(SignalPlanBlockedError):  # N was not set again
        svc.provide_signal_plan("N")
    svc.set_signal_plan(pn, network)
    assert svc.provide_signal_plan("N") == pn
