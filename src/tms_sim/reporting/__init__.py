"""Metrics Service and CSV Report Exporter (SAD §3.4, issue #10)."""
from tms_sim.reporting.export import (
    ExportError,
    export_comparison_csv,
    export_comparison_html,
    export_run_csv,
    export_run_html,
    generate_comparison_csv,
    generate_comparison_html,
    generate_run_csv,
    generate_run_html,
)
from tms_sim.reporting.history import CompletedTrip, HistorySample, SimulationHistoryTracker
from tms_sim.reporting.metrics import SimulationMetrics, compute_metrics

__all__ = [
    "CompletedTrip",
    "ExportError",
    "HistorySample",
    "SimulationHistoryTracker",
    "SimulationMetrics",
    "compute_metrics",
    "export_comparison_csv",
    "export_comparison_html",
    "export_run_csv",
    "export_run_html",
    "generate_comparison_csv",
    "generate_comparison_html",
    "generate_run_csv",
    "generate_run_html",
]
