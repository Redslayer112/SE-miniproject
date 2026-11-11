# Traffic Management System (Simulation)

**Software Engineering Project · UE24CS341A · PES University**

A Python-based traffic management simulation for modelling road networks, traffic signal plans, vehicle demand, and traffic flow. The project includes network and signal-plan validation, a simulation engine, scenario execution, a SQLite scenario library, run-record persistence, and automated tests.

> **Project Status:** Complete 5th-semester Software Engineering capstone release. Core simulation, interactive network editing, 2D canvas visualization, live metrics dashboards, scenario library, run-record persistence, run comparison, and CSV reporting are fully implemented and verified with 597 passing automated tests. For full project details, see the [Final Project Overview](docs/FINAL_PROJECT_OVERVIEW.md).

## Table of Contents

- [Project Overview](#project-overview)
- [Team Members](#team-members)
- [Current Features](#current-features)
- [Technology Stack](#technology-stack)
- [Project Documentation](#project-documentation)
- [Getting Started](#getting-started)
- [Running the Application](#running-the-application)
- [Running a Simulation](#running-a-simulation)
- [Project Structure](#project-structure)
- [Network Interface](#network-interface)
- [Testing and Continuous Integration](#testing-and-continuous-integration)
- [Development Status and Future Work](#development-status-and-future-work)
- [Institution and Course](#institution-and-course)
- [License](#license)

## Project Overview

The Traffic Management System (Simulation) provides a software environment for modelling and analyzing traffic conditions. It represents road networks, validates traffic signal plans, generates vehicle demand, and executes traffic scenarios.

The project also includes a local SQLite library for storing and managing scenarios and recording simulation runs. These capabilities provide a foundation for comparing traffic behaviour under different configurations and evaluating traffic-flow and signal-management strategies.

## Team Members

| **Team Member** | **SRN** | **Primary Responsibility** |
| --- | --- | --- |
| Venkata Srivaibhav Nukaraju | PES2UG24CS579 | Team Lead, Simulation Engine and Core Model |
| V Vyas | PES2UG24CS569 | Network and Signal-Plan Modelling |
| Vikas N Naik | PES2UG24CS583 | UI, 2D Visualization and UX |
| Vikhyath Bharadwaj K S | PES2UG24CS586 | Metrics, Reporting, QA and Testing |

## Current Features

The following capabilities are represented in the current repository:

- **Road network modelling:** Represents intersections and road segments.
- **Network validation:** Detects invalid network configurations and blocking errors.
- **Traffic signal plans:** Models and validates signal-plan configurations.
- **Vehicle demand generation:** Generates vehicles using scenario demand settings.
- **Simulation engine:** Advances the simulation and tracks vehicle events.
- **Scenario execution:** Loads a scenario, runs the simulation, and prints a summary of results.
- **SQLite scenario library:** Saves, lists, loads, duplicates, renames, and deletes named scenarios.
- **Scenario import and export:** Imports and exports scenarios using versioned JSON with validation.
- **Run-record persistence:** Saves simulation-run records with a snapshot of the scenario and supports listing and loading saved runs.
- **Run analysis:** Displays live and final travel, delay, queue, throughput, and speed metrics; saved runs can be compared and exported as CSV or HTML reports.
- **Scenario library UI:** Opens from **File → Scenario Library** or with **Ctrl+L**.
- **Automated testing:** Tests network validation, signal plans, demand generation, simulation behaviour, scenarios, storage, and UI workflows.
- **Continuous integration:** GitHub Actions runs the test suite on pushes to `main` and pull requests.

### Desktop Workbench & 2D Visualization

The desktop application provides the complete `TMS-Sim` workbench, 2D hardware-accelerated traffic visualization with mouse pan and scroll zoom, interactive network editing and validation, signal plan configuration dialogs, run history and comparison, live summary metrics, CSV reporting, and a scenario-library dialog.

## Technology Stack

| **Component** | **Technology** |
| --- | --- |
| Programming language | Python 3.11 / 3.12 |
| Scenario and run storage | SQLite |
| Scenario interchange format | JSON |
| Desktop UI framework | PySide6 |
| Build and package configuration | `setuptools` and `pyproject.toml` |
| Testing framework | `pytest` |
| Continuous integration | GitHub Actions |
| Version control | Git and GitHub |

PySide6 is declared as the project's runtime dependency. `pytest` and `pytest-qt` are declared as development dependencies.

## Project Documentation

The repository includes the following supporting documents:

| **Document** | **Location** | **Purpose** |
| --- | --- | --- |
| Final Project Overview | [`docs/FINAL_PROJECT_OVERVIEW.md`](docs/FINAL_PROJECT_OVERVIEW.md) | Comprehensive capstone overview, architecture, user workflows, and verified results |
| Requirements Traceability Matrix | [`docs/RTM.csv`](docs/RTM.csv) | Final RTM mapping all functional, non-functional, retired, and deferred requirements |
| Baseline decisions (approved) | [`docs/decisions/0001-baseline-proposal.md`](docs/decisions/0001-baseline-proposal.md) | Team-approved decisions (issue #1) aligning requirements, architecture, and implementation |
| Baseline amendment v1.1 | [`docs/baseline_amendment_v1.1.md`](docs/baseline_amendment_v1.1.md) | Section-by-section changes to the submitted SRS, SAD and STP |
| Test catalogue | [`docs/test_catalogue.md`](docs/test_catalogue.md) | Organizes test cases, verification methods, and requirement coverage |
| Test execution record | [`docs/test_execution_record.md`](docs/test_execution_record.md) | Chronological log of full test suite runs and verified milestones |
| System integration report | [`docs/system_integration_report.md`](docs/system_integration_report.md) | End-to-end integration workflows, resolved defects (SI-D1, SI-D2, SI-D3), and evidence |
| Submission checklist | [`docs/submission_checklist.md`](docs/submission_checklist.md) | Pre-submission verification checklist, demo guidance, and repository audit |
| Deviations log | [`DEVIATIONS.md`](DEVIATIONS.md) | Records differences between the implementation and the SRS, SAD, and STP |

The project also includes the Software Requirements Specification (SRS), Software Architecture and Design Specification (SAD), and Software Test Plan (STP). Refer to the corresponding repository documents for their detailed requirements and design decisions.

## Getting Started

### Prerequisites

- Python 3.11 or later
- `pip`
- Git
- A compatible environment for running PySide6 desktop applications

### 1. Clone the Repository

```bash
git clone https://github.com/Redslayer112/SE-miniproject.git
cd SE-miniproject
```

### 2. Create a Virtual Environment

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Linux or macOS**

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install the Project and Development Dependencies

```bash
python -m pip install -e ".[dev]"
```

This installs the project in editable mode along with its declared development dependencies.

## Running the Application

To launch the desktop workbench, run:

```bash
python -m tms_sim
```

The application opens the `TMS-Sim` workbench. From the application menu, choose **File → Scenario Library** or press **Ctrl+L** to open the scenario library.

## Running a Simulation

To run the included sample scenario in headless mode, execute:

```bash
python -m tms_sim run tests/data/scenario/small_valid_scenario.json
```

The command loads the scenario, executes the simulation, and prints a summary containing the simulated duration, number of generated and entered vehicles, completed vehicles, vehicles remaining in the network, and mean travel time when available.

Example output from a verified run:

```text
simulated 600.0 s | generated 30 | entered 30 | completed 30 | in network 0
mean travel time 16.4 s
```

The numerical results above are an example from one run of the included scenario, not a guarantee for every scenario.

## Project Structure

```text
SE-miniproject/
├── .github/
│   └── workflows/                  # GitHub Actions CI configuration
├── docs/
│   ├── decisions/                  # Architecture & baseline decision records
│   ├── screenshots/                # Application UI & visualization screenshots
│   ├── FINAL_PROJECT_OVERVIEW.md   # Final capstone documentation & workflows
│   ├── RTM.csv                     # Requirements Traceability Matrix
│   ├── test_catalogue.md           # Master test catalogue & requirement mappings
│   ├── test_execution_record.md    # Full test suite execution history
│   ├── system_integration_report.md# Integration test report & defect resolutions
│   └── submission_checklist.md     # Verification & evaluation checklist
├── fixtures/
│   ├── valid/                      # Valid network & scenario test fixtures
│   └── invalid/                    # Malformed test fixtures for validation
├── src/
│   └── tms_sim/
│       ├── network/                # Road network graph models, elements & validation
│       ├── signal/                 # Signal-plan models, phases & controllers
│       ├── sim/                    # Microscopic IDM engine, vehicle dynamics, demand
│       ├── ui/                     # PySide6 Workbench, 2D canvas, dialogs & charts
│       ├── reporting/              # Metrics calculation, aggregators & CSV export
│       └── storage/                # SQLite scenario library & run-record repository
├── tests/
│   ├── unit/                       # Unit tests for core components
│   ├── integration/                # Integration test suites
│   ├── test_ui_*.py                # PySide6 UI and visualization test suites
│   ├── test_system_integration.py  # End-to-end integration workflows (SI-01..SI-08a)
│   └── test_acceptance_scripts.py  # Performance and reliability runner acceptance
├── DEVIATIONS.md                   # Specification deviations & decisions log
├── pyproject.toml                  # Project metadata, entry points & dependencies
└── README.md                       # Repository overview and setup guide
```

## Network Interface

**Reference:** SAD §4.3 — Interface 1: Network Editor → Simulation Engine

The network interface is implemented in `src/tms_sim/network/`. `NetworkService` exposes the documented SAD operations using both the specification's operation names and their Python-style equivalents.

| **SAD operation** | **Python method** | **Behaviour** |
| --- | --- | --- |
| `loadNetwork(path)` | `load_network` | Reads the `network` section from a JSON scenario file. Raises `NetworkFormatError` if the file is structurally invalid. |
| `validateNetwork()` | `validate_network` | Returns a `ValidationResult`. Each issue identifies an error code, element type, and element ID. |
| `provideNetworkState()` | `provide_network_state` | Returns the network or raises `NetworkBlockedError` containing validation errors when blocking issues exist. |

Examples of documented blocking validation errors include:

- `DISCONNECTED_GRAPH`
- `ZERO_LANES`
- `ZERO_LENGTH`
- `NO_RECEIVING_LANE`

A road segment's direction is defined by the edge from `from_intersection` to `to_intersection`.

## Testing and Continuous Integration

Run the automated test suite from the repository root:

```powershell
$env:PYTHONPATH=".;src"
python -m pytest
```

The suite includes tests for:

- Network topology and validation rules
- Signal-plan validation, phases, and cyclic controllers
- Vehicle demand generation and stochastic arrivals
- Microscopic simulation engine, car-following (IDM), and collisions
- Scenario serialization and schema compatibility
- Scenario library and SQLite run-record persistence
- PySide6 desktop workbench, controls, pan/zoom, and canvas painting
- End-to-end system integration workflows (SI-01 through SI-08a)

The latest verified full test run completed with **597 tests passed** under Python 3.12 (and Python 3.11 in CI), with 0 failures, 0 xfailed, and a clean process exit (exit code 0).

### Continuous Integration

GitHub Actions runs the test suite on pushes to `main` and pull requests. The workflow uses Windows and Python 3.11, installs the project with its development dependencies, and runs `pytest`.

## Development Status and Future Work

### Implemented in Final Capstone Release
- **Interactive road network editing:** Add, delete, select, and reposition intersections and directed road segments directly within the PySide6 Workbench.
- **Topological network validation:** Automated checks prevent invalid graph states prior to simulation start.
- **2D traffic visualization:** Real-time rendering of lanes, vehicles, queues, and signal aspects with mouse pan and scroll zoom.
- **Simulation controls:** Full Play, Pause, Step, Stop, and Reset controls with variable speed multipliers (0.5x–4.0x).
- **Traffic metrics & live dashboards:** Real-time HUD and Matplotlib charts tracking delay, throughput, queue lengths, and mean velocities.
- **Run persistence & comparative analytics:** Complete SQLite run history with scenario snapshots, side-by-side run comparisons, and CSV export.

### Future Work & Extensions
- Actuated / adaptive traffic signal control algorithms (e.g., Webster cycle optimization, Green Wave coordination).
- Multi-class vehicle kinematics (buses, trucks, emergency vehicle preemption).
- Ingestion of real-world OpenStreetMap (OSM) or SUMO network files.
- 3D rendering viewport utilizing modern OpenGL/Vulkan pipelines.
- Formal usability studies across wider multi-user cohorts.

## Institution and Course

**Institution:** PES University  
**Course:** Software Engineering  
**Course code:** UE24CS341A

## License

This project is developed for academic purposes as part of the Software Engineering course at PES University.

PySide6 is distributed under the GNU Lesser General Public License (LGPL). Consult the applicable license terms when redistributing the application or its dependencies.
