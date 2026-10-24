"""python -m tms_sim                 -> workbench window
python -m tms_sim run SCENARIO    -> headless run, prints a summary (no Qt needed)"""
import sys


def run(path: str) -> int:
    from tms_sim.network import NetworkBlockedError, NetworkFormatError
    from tms_sim.signal import SignalPlanBlockedError
    from tms_sim.sim.demand import DemandError
    from tms_sim.sim.scenario import load_scenario

    try:
        engine = load_scenario(path)
    except (NetworkBlockedError, SignalPlanBlockedError) as e:
        print("run blocked:", *(f"  {i.code}: {i.message}" for i in e.errors), sep="\n", file=sys.stderr)
        return 1
    except (NetworkFormatError, DemandError, ValueError, OSError) as e:
        print(f"cannot load scenario: {e}", file=sys.stderr)
        return 1
    engine.start()
    engine.set_speed(4)
    while not engine.finished:
        engine.advance(engine.p.dt)
    exits = [e for e in engine.events if e[2] == "exit"]
    spawns = {e[1]: e[0] for e in engine.events if e[2] == "spawn"}
    travel = [t - spawns[v] for t, v, *_ in exits]
    print(f"simulated {engine.time:.1f} s | generated {len(engine.vehicles)} | entered {len(spawns)} "
          f"| completed {len(exits)} | in network {len(engine.cars)}")
    if travel:
        print(f"mean travel time {sum(travel) / len(travel):.1f} s")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["run"] and len(sys.argv) == 3:
        raise SystemExit(run(sys.argv[2]))
    from tms_sim.ui.app import main

    raise SystemExit(main())
