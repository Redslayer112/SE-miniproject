import pytest

from tms_sim.network import ControlType, Intersection, Network, Segment, TurningMovement

# Four-way signalized intersection X at the origin, neighbours N, S, E, W 100 m away.
# Movement id = approach letter + exit letter, e.g. "SN" is S -> X -> N.
# Left-hand traffic: from S, N is straight on, E is a right turn, W is a left turn.
_NEIGHBOURS = {"N": (0, 100), "S": (0, -100), "E": (100, 0), "W": (-100, 0)}
_EXITS = {"S": "NEW", "N": "SWE", "E": "WNS", "W": "ESN"}  # through, right, left


@pytest.fixture
def network():
    inters = [Intersection("X", (0, 0), ControlType.SIGNALIZED)]
    inters += [Intersection(k, pos, ControlType.UNCONTROLLED) for k, pos in _NEIGHBOURS.items()]
    segs = []
    for k in _NEIGHBOURS:
        segs.append(Segment(f"{k}_in", k, "X", 100, 1, 13.9))
        segs.append(Segment(f"{k}_out", "X", k, 100, 1, 13.9))
    moves = [TurningMovement(f"{a}{b}", "X", f"{a}_in", f"{b}_out")
             for a, exits in _EXITS.items() for b in exits]
    return Network(inters, segs, moves)
