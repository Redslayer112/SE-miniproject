"""SAD Signal Configuration -> Simulation Engine interface: validateSignalPlan(), provideSignalPlan()."""
from __future__ import annotations

import hashlib
import json

from tms_sim.network import Network, ValidationIssue, ValidationResult
from tms_sim.network.serialization import network_to_dict

from .model import SignalPlan
from .validation import validate_signal_plan as _validate


class SignalPlanBlockedError(Exception):
    """Raised when a plan must not be used; carries the blocking errors."""

    def __init__(self, errors: list[ValidationIssue]):
        self.errors = errors
        super().__init__("; ".join(f"{e.code}: {e.message}" for e in errors))


def _fingerprint(network: Network) -> str:
    """Hash of the network's serialized content, so any edit changes it."""
    text = json.dumps(network_to_dict(network), sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SignalService:
    def __init__(self):
        # intersection id -> (plan, network it was validated against, fingerprint at that time)
        self._plans: dict[str, tuple[SignalPlan, Network, str]] = {}

    def validate_signal_plan(self, plan: SignalPlan, network: Network) -> ValidationResult:
        return _validate(plan, network)

    def set_signal_plan(self, plan: SignalPlan, network: Network) -> SignalPlan:
        """Store the plan only if it has no errors.

        Plans are immutable. The network object and a fingerprint of its content are kept with
        each plan, so provide_signal_plan can tell if the network changed afterwards.
        Calling this again with the current network refreshes the fingerprint.
        """
        result = _validate(plan, network)
        if not result.is_valid:
            raise SignalPlanBlockedError(result.errors)
        self._plans[plan.intersection_id] = (plan, network, _fingerprint(network))
        return plan

    def provide_signal_plan(self, intersection_id: str) -> SignalPlan:
        """Return the validated plan, or raise SignalPlanBlockedError if it is missing or the
        network changed since set_signal_plan validated it (call set_signal_plan again)."""
        stored = self._plans.get(intersection_id)
        if stored is None:
            raise SignalPlanBlockedError([ValidationIssue(
                "SIGNAL_PLAN_NOT_SET", f"no validated plan for intersection '{intersection_id}'",
                "signal_plan", intersection_id)])
        plan, network, fingerprint = stored
        if _fingerprint(network) != fingerprint:
            raise SignalPlanBlockedError([ValidationIssue(
                "NETWORK_CHANGED_SINCE_VALIDATION",
                f"the network changed after the plan for '{intersection_id}' was validated; "
                "call set_signal_plan again",
                "signal_plan", intersection_id)])
        return plan

    # SAD names
    validateSignalPlan = validate_signal_plan
    provideSignalPlan = provide_signal_plan
