"""SAD network interface: validateNetwork(), loadNetwork(), provideNetworkState()."""
from __future__ import annotations

from .model import Network
from .serialization import load_network as _load
from .validation import ValidationIssue, ValidationResult, validate


class NetworkBlockedError(Exception):
    """Raised when a run must not start; carries the blocking errors."""

    def __init__(self, errors: list[ValidationIssue]):
        self.errors = errors
        super().__init__("; ".join(f"{e.code}: {e.message}" for e in errors))


class NetworkService:
    def __init__(self, network: Network | None = None):
        self._network = network

    def load_network(self, path) -> Network:
        self._network = _load(path)
        return self._network

    def validate_network(self) -> ValidationResult:
        if self._network is None:
            return ValidationResult([ValidationIssue(
                "NETWORK_NOT_LOADED", "no network has been loaded", "network", "")])
        return validate(self._network)

    def provide_network_state(self) -> Network:
        result = self.validate_network()
        if not result.is_valid:
            raise NetworkBlockedError(result.errors)
        return self._network

    # SAD names
    loadNetwork = load_network
    validateNetwork = validate_network
    provideNetworkState = provide_network_state
