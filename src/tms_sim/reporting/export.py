"""Simulation metrics and scenario comparison export functionality (Step 5G).

Provides headless, authoritative export utilities for simulation runs and
scenario comparisons to CSV and self-contained HTML reports.
"""
from __future__ import annotations

import csv
import html
import io
from pathlib import Path
from typing import TYPE_CHECKING

from tms_sim.reporting.comparison import (
    ComparisonStatus,
    MetricComparison,
    ScenarioComparison,
    SimulationRunRecord,
)

if TYPE_CHECKING:
    from tms_sim.sim.engine import Engine


class ExportError(Exception):
    """Raised when an export operation fails due to invalid parameters or I/O error."""


def _ensure_run_record(run: SimulationRunRecord | Engine) -> SimulationRunRecord:
    """Validate and convert an input run into a SimulationRunRecord."""
    if isinstance(run, SimulationRunRecord):
        return run

    # If an engine was passed, attempt to construct a SimulationRunRecord
    from tms_sim.sim.engine import Engine
    if isinstance(run, Engine):
        if not getattr(run, "finished", False):
            raise ExportError("Cannot export metrics for an incomplete simulation run.")
        return SimulationRunRecord.from_engine(run)

    raise ValueError(f"Expected a SimulationRunRecord or finished Engine, got {type(run).__name__}.")


def generate_run_csv(run: SimulationRunRecord | Engine) -> str:
    """Generate RFC 4180 compliant CSV string for a completed simulation run."""
    record = _ensure_run_record(run)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)

    # Header
    writer.writerow(["Metric", "Value", "Unit", "Status", "Notes"])

    # Metadata
    writer.writerow(["Scenario Name", record.scenario_name, "", "Available", "Scenario identifier"])
    writer.writerow(["Run Label", record.label, "", "Available", "Simulation run label"])
    writer.writerow(["Run ID", record.run_id, "", "Available", "Unique simulation run snapshot ID"])
    if record.timestamp:
        writer.writerow(["Timestamp", record.timestamp, "", "Available", "Run execution or capture timestamp"])
    writer.writerow(["Run Status", record.metrics.status, "", "Available", "Simulation completion state"])
    writer.writerow(["Simulation Duration", f"{record.metrics.duration:.1f}", "s", "Available", "Configured simulation duration"])
    writer.writerow(["Simulated Time", f"{record.metrics.simulated_time:.1f}", "s", "Available", "Elapsed simulation clock time"])

    # Modeled metrics
    m = record.metrics
    writer.writerow(["Vehicles Generated", str(m.vehicles_generated), "veh", "Available", "Scheduled vehicle demand"])
    writer.writerow(["Total Scheduled Demand", str(m.total_scheduled), "veh", "Available", "Total demand configured in scenario"])
    writer.writerow(["Vehicles Entered", str(m.vehicles_entered), "veh", "Available", "Unique vehicles that entered the network"])
    writer.writerow(["Vehicles Completed", str(m.vehicles_completed), "veh", "Available", "Unique vehicles that completed their journeys"])
    writer.writerow(["Vehicles in Network", str(m.vehicles_in_network), "veh", "Available", "Active vehicles currently inside the network"])

    if m.mean_travel_time is not None:
        writer.writerow(["Mean Travel Time", f"{m.mean_travel_time:.1f}", "s", "Available", "Average completed trip duration"])
    else:
        writer.writerow(["Mean Travel Time", "N/A", "s", "Unavailable", "No completed trips recorded"])

    # Explicitly unmodeled backend metrics (TMS-F-050)
    writer.writerow(["Hourly Throughput", "N/A", "veh/h", "Unavailable", "Not modeled in current simulation engine"])
    writer.writerow(["Average Delay", "N/A", "s", "Unavailable", "Not modeled in current simulation engine"])
    writer.writerow(["Average Queue Length", "N/A", "veh", "Unavailable", "Not modeled in current simulation engine"])

    return output.getvalue()


def generate_run_html(run: SimulationRunRecord | Engine) -> str:
    """Generate a self-contained, beautifully styled HTML report for a simulation run."""
    record = _ensure_run_record(run)
    m = record.metrics

    safe_title = html.escape(record.label)
    safe_scenario = html.escape(record.scenario_name)
    safe_status = html.escape(m.status)
    safe_timestamp = html.escape(record.timestamp) if record.timestamp else "N/A"

    travel_time_val = f"{m.mean_travel_time:.1f} s" if m.mean_travel_time is not None else "N/A"
    travel_time_note = "Average completed trip duration" if m.mean_travel_time is not None else "No completed trips"

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Simulation Report — {safe_title}</title>
  <style>
    :root {{
      --primary: #2563eb;
      --primary-light: #eff6ff;
      --text: #1e293b;
      --text-muted: #64748b;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --border: #e2e8f0;
      --success: #16a34a;
      --success-bg: #dcfce7;
      --danger: #dc2626;
      --danger-bg: #fee2e2;
      --warning: #d97706;
      --warning-bg: #fef3c7;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: var(--text);
      background-color: var(--bg);
      line-height: 1.5;
      padding: 2rem 1rem;
    }}
    .container {{
      max-width: 900px;
      margin: 0 auto;
    }}
    .header {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.75rem 2rem;
      margin-bottom: 1.5rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .header h1 {{
      font-size: 1.5rem;
      font-weight: 700;
      color: #0f172a;
      margin-bottom: 0.25rem;
    }}
    .header .subtitle {{
      color: var(--text-muted);
      font-size: 0.95rem;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 1rem;
      margin-top: 1.25rem;
      padding-top: 1.25rem;
      border-top: 1px solid var(--border);
    }}
    .meta-item .label {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      font-weight: 600;
    }}
    .meta-item .value {{
      font-size: 1rem;
      font-weight: 600;
      color: #0f172a;
      margin-top: 0.15rem;
    }}
    .cards-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1.25rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .card .title {{
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
    }}
    .card .metric-val {{
      font-size: 1.75rem;
      font-weight: 700;
      color: #0f172a;
      margin: 0.25rem 0 0.15rem 0;
    }}
    .card .unit {{
      font-size: 0.85rem;
      font-weight: 500;
      color: var(--text-muted);
      margin-left: 0.25rem;
    }}
    .card .hint {{
      font-size: 0.8rem;
      color: var(--text-muted);
    }}
    .table-container {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
      margin-bottom: 1.5rem;
    }}
    .table-header {{
      padding: 1.25rem 1.75rem;
      border-bottom: 1px solid var(--border);
    }}
    .table-header h2 {{
      font-size: 1.15rem;
      font-weight: 700;
      color: #0f172a;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
    }}
    th {{
      background: #f8fafc;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      font-weight: 600;
      padding: 0.75rem 1.5rem;
      border-bottom: 1px solid var(--border);
    }}
    td {{
      padding: 0.85rem 1.5rem;
      border-bottom: 1px solid var(--border);
      font-size: 0.9rem;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    .badge {{
      display: inline-block;
      padding: 0.2rem 0.55rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
    }}
    .badge-available {{ background: var(--success-bg); color: var(--success); }}
    .badge-unavailable {{ background: #f1f5f9; color: #94a3b8; }}
    .footer {{
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-top: 2rem;
    }}
    @media print {{
      body {{ background: #ffffff; padding: 0; }}
      .header, .card, .table-container {{ box-shadow: none; border-color: #cbd5e1; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Simulation Run Report</h1>
      <div class="subtitle">{safe_title}</div>
      <div class="meta-grid">
        <div class="meta-item">
          <div class="label">Scenario</div>
          <div class="value">{safe_scenario}</div>
        </div>
        <div class="meta-item">
          <div class="label">Status</div>
          <div class="value">{safe_status}</div>
        </div>
        <div class="meta-item">
          <div class="label">Simulated Duration</div>
          <div class="value">{m.simulated_time:.1f}s / {m.duration:.1f}s</div>
        </div>
        <div class="meta-item">
          <div class="label">Timestamp</div>
          <div class="value">{safe_timestamp}</div>
        </div>
      </div>
    </div>

    <div class="cards-grid">
      <div class="card">
        <div class="title">Mean Travel Time</div>
        <div class="metric-val">{travel_time_val}</div>
        <div class="hint">{html.escape(travel_time_note)}</div>
      </div>
      <div class="card">
        <div class="title">Vehicles Completed</div>
        <div class="metric-val">{m.vehicles_completed}<span class="unit">veh</span></div>
        <div class="hint">Total journeys finished</div>
      </div>
      <div class="card">
        <div class="title">Active in Network</div>
        <div class="metric-val">{m.vehicles_in_network}<span class="unit">veh</span></div>
        <div class="hint">Vehicles remaining in network</div>
      </div>
      <div class="card">
        <div class="title">Vehicles Entered</div>
        <div class="metric-val">{m.vehicles_entered}<span class="unit">/ {m.vehicles_generated}</span></div>
        <div class="hint">Network utilization</div>
      </div>
    </div>

    <div class="table-container">
      <div class="table-header">
        <h2>Detailed Metrics Summary</h2>
      </div>
      <table>
        <thead>
          <tr>
            <th>Metric</th>
            <th>Value</th>
            <th>Unit</th>
            <th>Status</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Mean Travel Time</strong></td>
            <td>{travel_time_val}</td>
            <td>s</td>
            <td><span class="badge {'badge-available' if m.mean_travel_time is not None else 'badge-unavailable'}">{'Available' if m.mean_travel_time is not None else 'Unavailable'}</span></td>
            <td>Average duration for completed vehicle journeys</td>
          </tr>
          <tr>
            <td><strong>Vehicles Completed</strong></td>
            <td>{m.vehicles_completed}</td>
            <td>veh</td>
            <td><span class="badge badge-available">Available</span></td>
            <td>Total journeys that reached destination</td>
          </tr>
          <tr>
            <td><strong>Vehicles in Network</strong></td>
            <td>{m.vehicles_in_network}</td>
            <td>veh</td>
            <td><span class="badge badge-available">Available</span></td>
            <td>Active vehicles currently traveling inside network</td>
          </tr>
          <tr>
            <td><strong>Vehicles Entered</strong></td>
            <td>{m.vehicles_entered}</td>
            <td>veh</td>
            <td><span class="badge badge-available">Available</span></td>
            <td>Vehicles that successfully spawned into the network</td>
          </tr>
          <tr>
            <td><strong>Vehicles Generated</strong></td>
            <td>{m.vehicles_generated}</td>
            <td>veh</td>
            <td><span class="badge badge-available">Available</span></td>
            <td>Total scheduled vehicles whose depart time arrived</td>
          </tr>
          <tr>
            <td><strong>Total Scheduled Demand</strong></td>
            <td>{m.total_scheduled}</td>
            <td>veh</td>
            <td><span class="badge badge-available">Available</span></td>
            <td>Total vehicle trips defined in scenario demand schedule</td>
          </tr>
          <tr>
            <td><strong>Simulation Duration</strong></td>
            <td>{m.duration:.1f}</td>
            <td>s</td>
            <td><span class="badge badge-available">Available</span></td>
            <td>Configured simulation time horizon</td>
          </tr>
          <tr>
            <td><strong>Hourly Throughput</strong></td>
            <td>N/A</td>
            <td>veh/h</td>
            <td><span class="badge badge-unavailable">Not Modeled</span></td>
            <td>Not tracked by current simulation engine</td>
          </tr>
          <tr>
            <td><strong>Average Delay</strong></td>
            <td>N/A</td>
            <td>s</td>
            <td><span class="badge badge-unavailable">Not Modeled</span></td>
            <td>Not tracked by current simulation engine</td>
          </tr>
          <tr>
            <td><strong>Average Queue Length</strong></td>
            <td>N/A</td>
            <td>veh</td>
            <td><span class="badge badge-unavailable">Not Modeled</span></td>
            <td>Not tracked by current simulation engine</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="footer">
      TMS-Sim Desktop Workbench &bull; Authoritative Simulation Export
    </div>
  </div>
</body>
</html>
"""
    return html_doc


def generate_comparison_csv(comparison: ScenarioComparison) -> str:
    """Generate RFC 4180 compliant CSV string for a scenario comparison."""
    if comparison is None or not isinstance(comparison, ScenarioComparison):
        raise ValueError("A valid ScenarioComparison instance is required for export.")

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)

    # Headers
    writer.writerow([
        "Metric",
        "Baseline",
        "Candidate",
        "Absolute Change",
        "Percentage Change",
        "Unit",
        "Status",
        "Notes",
    ])

    # Metadata rows
    writer.writerow([
        "Run Label",
        comparison.baseline.label,
        comparison.candidate.label,
        "N/A",
        "N/A",
        "",
        "Available",
        "Simulation run labels",
    ])
    writer.writerow([
        "Scenario Name",
        comparison.baseline.scenario_name,
        comparison.candidate.scenario_name,
        "N/A",
        "N/A",
        "",
        "Available",
        "Scenario identifiers",
    ])

    dur_b = comparison.baseline.metrics.duration
    dur_c = comparison.candidate.metrics.duration
    dur_diff = dur_c - dur_b
    writer.writerow([
        "Simulation Duration",
        f"{dur_b:.1f}",
        f"{dur_c:.1f}",
        f"{dur_diff:+.1f}" if dur_diff != 0 else "0.0",
        "N/A",
        "s",
        "Compatible" if comparison.duration_compatible else "Incompatible",
        comparison.warning or "Configured simulation durations match",
    ])

    # Metrics rows
    for m in comparison.metrics:
        if m.baseline_value is None:
            base_str = "N/A"
        elif isinstance(m.baseline_value, float):
            base_str = f"{m.baseline_value:.1f}"
        else:
            base_str = str(m.baseline_value)

        if m.candidate_value is None:
            cand_str = "N/A"
        elif isinstance(m.candidate_value, float):
            cand_str = f"{m.candidate_value:.1f}"
        else:
            cand_str = str(m.candidate_value)

        if m.absolute_change is None:
            abs_str = "N/A"
        else:
            is_int_metric = isinstance(m.baseline_value, int) and isinstance(m.candidate_value, int)
            abs_val = int(m.absolute_change) if is_int_metric else m.absolute_change
            if abs_val > 0:
                abs_str = f"+{abs_val}"
            else:
                abs_str = f"{abs_val}"

        if m.percent_change is None:
            if m.is_available and m.baseline_value == 0:
                pct_str = "N/A (base 0)"
            else:
                pct_str = "N/A"
        elif m.percent_change > 0:
            pct_str = f"+{m.percent_change:.1f}%"
        else:
            pct_str = f"{m.percent_change:.1f}%"

        writer.writerow([
            m.name,
            base_str,
            cand_str,
            abs_str,
            pct_str,
            m.unit,
            m.status.value,
            m.note,
        ])

    return output.getvalue()


def generate_comparison_html(comparison: ScenarioComparison) -> str:
    """Generate a self-contained, beautifully styled HTML report for a scenario comparison."""
    if comparison is None or not isinstance(comparison, ScenarioComparison):
        raise ValueError("A valid ScenarioComparison instance is required for export.")

    base = comparison.baseline
    cand = comparison.candidate

    safe_base_label = html.escape(base.label)
    safe_cand_label = html.escape(cand.label)
    safe_base_scen = html.escape(base.scenario_name)
    safe_cand_scen = html.escape(cand.scenario_name)

    warning_html = ""
    if comparison.warning:
        warning_html = f"""
    <div class="warning-banner">
      <strong>Warning:</strong> {html.escape(comparison.warning)}
    </div>
"""

    rows_html = []
    for m in comparison.metrics:
        safe_name = html.escape(m.name)
        safe_unit = html.escape(m.unit)
        safe_note = html.escape(m.note)

        base_str = f"{m.baseline_value:.1f}" if isinstance(m.baseline_value, float) else (str(m.baseline_value) if m.baseline_value is not None else "&mdash;")
        cand_str = f"{m.candidate_value:.1f}" if isinstance(m.candidate_value, float) else (str(m.candidate_value) if m.candidate_value is not None else "&mdash;")

        if m.absolute_change is not None:
            is_int_metric = isinstance(m.baseline_value, int) and isinstance(m.candidate_value, int)
            abs_val = int(m.absolute_change) if is_int_metric else m.absolute_change
            abs_prefix = "+" if abs_val > 0 else ""
            abs_str = f"{abs_prefix}{abs_val}"
        else:
            abs_str = "&mdash;"

        if m.percent_change is not None:
            pct_prefix = "+" if m.percent_change > 0 else ""
            pct_str = f"{pct_prefix}{m.percent_change:.1f}%"
        elif m.is_available and m.baseline_value == 0:
            pct_str = "N/A (base 0)"
        else:
            pct_str = "&mdash;"

        # Status badge styling
        if m.status == ComparisonStatus.IMPROVED:
            badge = '<span class="badge badge-improved">Improved</span>'
        elif m.status == ComparisonStatus.REGRESSED:
            badge = '<span class="badge badge-regressed">Regressed</span>'
        elif m.status == ComparisonStatus.UNCHANGED:
            badge = '<span class="badge badge-unchanged">Unchanged</span>'
        else:
            badge = '<span class="badge badge-unavailable">Not Modeled</span>'

        rows_html.append(f"""
          <tr>
            <td><strong>{safe_name}</strong></td>
            <td>{base_str}</td>
            <td>{cand_str}</td>
            <td>{abs_str}</td>
            <td>{pct_str}</td>
            <td>{safe_unit}</td>
            <td>{badge}</td>
            <td class="text-muted">{safe_note}</td>
          </tr>
""")

    tbody_html = "".join(rows_html)

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Scenario Comparison Report — TMS-Sim</title>
  <style>
    :root {{
      --primary: #2563eb;
      --primary-light: #eff6ff;
      --candidate: #7c3aed;
      --text: #1e293b;
      --text-muted: #64748b;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --border: #e2e8f0;
      --success: #16a34a;
      --success-bg: #dcfce7;
      --danger: #dc2626;
      --danger-bg: #fee2e2;
      --warning: #b45309;
      --warning-bg: #fffbeb;
      --warning-border: #fde68a;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: var(--text);
      background-color: var(--bg);
      line-height: 1.5;
      padding: 2rem 1rem;
    }}
    .container {{
      max-width: 1000px;
      margin: 0 auto;
    }}
    .header {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.75rem 2rem;
      margin-bottom: 1.5rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .header h1 {{
      font-size: 1.5rem;
      font-weight: 700;
      color: #0f172a;
      margin-bottom: 0.25rem;
    }}
    .header .subtitle {{
      color: var(--text-muted);
      font-size: 0.95rem;
    }}
    .runs-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.25rem;
      margin-top: 1.25rem;
      padding-top: 1.25rem;
      border-top: 1px solid var(--border);
    }}
    .run-box {{
      padding: 1rem;
      border-radius: 8px;
    }}
    .run-box.baseline {{
      background: #eff6ff;
      border: 1px solid #bfdbfe;
    }}
    .run-box.candidate {{
      background: #f5f3ff;
      border: 1px solid #ddd6fe;
    }}
    .run-box .role {{
      font-size: 0.75rem;
      text-transform: uppercase;
      font-weight: 700;
      letter-spacing: 0.05em;
      margin-bottom: 0.25rem;
    }}
    .run-box.baseline .role {{ color: #1d4ed8; }}
    .run-box.candidate .role {{ color: #6d28d9; }}
    .run-box .name {{
      font-size: 1.05rem;
      font-weight: 700;
      color: #0f172a;
    }}
    .run-box .scen {{
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-top: 0.2rem;
    }}
    .warning-banner {{
      background: var(--warning-bg);
      border: 1px solid var(--warning-border);
      color: var(--warning);
      border-radius: 8px;
      padding: 0.85rem 1.25rem;
      font-size: 0.9rem;
      margin-bottom: 1.5rem;
    }}
    .table-container {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
      margin-bottom: 1.5rem;
    }}
    .table-header {{
      padding: 1.25rem 1.75rem;
      border-bottom: 1px solid var(--border);
    }}
    .table-header h2 {{
      font-size: 1.15rem;
      font-weight: 700;
      color: #0f172a;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
    }}
    th {{
      background: #f8fafc;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      font-weight: 600;
      padding: 0.75rem 1.25rem;
      border-bottom: 1px solid var(--border);
    }}
    td {{
      padding: 0.85rem 1.25rem;
      border-bottom: 1px solid var(--border);
      font-size: 0.9rem;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    .text-muted {{ color: var(--text-muted); font-size: 0.8rem; }}
    .badge {{
      display: inline-block;
      padding: 0.2rem 0.6rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 700;
      text-align: center;
    }}
    .badge-improved {{ background: var(--success-bg); color: var(--success); }}
    .badge-regressed {{ background: var(--danger-bg); color: var(--danger); }}
    .badge-unchanged {{ background: #f1f5f9; color: #475569; }}
    .badge-unavailable {{ background: #f8fafc; color: #94a3b8; }}
    .footer {{
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-top: 2rem;
    }}
    @media print {{
      body {{ background: #ffffff; padding: 0; }}
      .header, .table-container {{ box-shadow: none; border-color: #cbd5e1; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Simulation Scenario Comparison Report</h1>
      <div class="subtitle">Performance and efficiency evaluation between baseline and candidate runs</div>
      <div class="runs-grid">
        <div class="run-box baseline">
          <div class="role">Baseline Reference</div>
          <div class="name">{safe_base_label}</div>
          <div class="scen">Scenario: {safe_base_scen} &bull; Duration: {base.metrics.duration:.1f}s</div>
        </div>
        <div class="run-box candidate">
          <div class="role">Candidate Run</div>
          <div class="name">{safe_cand_label}</div>
          <div class="scen">Scenario: {safe_cand_scen} &bull; Duration: {cand.metrics.duration:.1f}s</div>
        </div>
      </div>
    </div>

    {warning_html}

    <div class="table-container">
      <div class="table-header">
        <h2>Comparative Metrics Evaluation</h2>
      </div>
      <table>
        <thead>
          <tr>
            <th>Metric</th>
            <th>Baseline</th>
            <th>Candidate</th>
            <th>Abs Change</th>
            <th>% Change</th>
            <th>Unit</th>
            <th>Assessment</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {tbody_html}
        </tbody>
      </table>
    </div>

    <div class="footer">
      TMS-Sim Desktop Workbench &bull; Authoritative Scenario Comparison
    </div>
  </div>
</body>
</html>
"""
    return html_doc


def _write_file_atomically(content: str, dest: Path) -> Path:
    """Safely write UTF-8 text content to the destination path."""
    dest = Path(dest)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Write to temporary file in the same directory then replace
        temp_dest = dest.with_name(f".{dest.name}.tmp")
        temp_dest.write_text(content, encoding="utf-8")
        temp_dest.replace(dest)
        return dest
    except OSError as exc:
        raise ExportError(f"Failed to write export file to '{dest}': {exc}") from exc


def export_run_csv(run: SimulationRunRecord | Engine, path: str | Path) -> Path:
    """Export a simulation run's metrics to a UTF-8 CSV file."""
    dest = Path(path)
    content = generate_run_csv(run)
    return _write_file_atomically(content, dest)


def export_run_html(run: SimulationRunRecord | Engine, path: str | Path) -> Path:
    """Export a simulation run's metrics to a self-contained HTML report."""
    dest = Path(path)
    content = generate_run_html(run)
    return _write_file_atomically(content, dest)


def export_comparison_csv(comparison: ScenarioComparison, path: str | Path) -> Path:
    """Export a scenario comparison report to a UTF-8 CSV file."""
    dest = Path(path)
    content = generate_comparison_csv(comparison)
    return _write_file_atomically(content, dest)


def export_comparison_html(comparison: ScenarioComparison, path: str | Path) -> Path:
    """Export a scenario comparison report to a self-contained HTML report."""
    dest = Path(path)
    content = generate_comparison_html(comparison)
    return _write_file_atomically(content, dest)
