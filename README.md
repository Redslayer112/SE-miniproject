# Traffic Management System (Simulation)

**Software Engineering Project · UE24CS341A · PES University**

A Python-based traffic management simulation for modelling road networks, traffic signal plans, vehicle demand, and traffic flow. The project includes network and signal-plan validation, a simulation engine, scenario execution, a SQLite scenario library, run-record persistence, and automated tests.

> **Development status:** Core simulation, scenario storage, and run-record storage are implemented and tested. Metrics, comparison workflows, CSV reporting, and richer interactive visualization remain areas for continued development.

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

### Current UI Limitations

The desktop application provides the `TMS-Sim` workbench, run history and comparison, summary metrics, CSV/HTML reporting, and a scenario-library dialog. Further development can improve interactive network editing and full 2D traffic visualization.

## Technology Stack

| **Component** | **Technology** |
| --- | --- |
| Programming language | Python 3.11 |
| Scenario and run storage | SQLite |
| Scenario interchange format | JSON |
| Desktop UI framework | PySide6 |
| Build and package configuration | `setuptools` and `pyproject.toml` |
| Testing framework | `pytest` |
| Continuous integration | GitHub Actions |
| Version control | Git and GitHub |

PySide6 is declared as the project's runtime dependency. `pytest` is declared as a development dependency.

## Project Documentation

The repository includes the following supporting documents:

| **Document** | **Location** | **Purpose** |
| --- | --- | --- |
| Baseline proposal | `docs/decisions/0001-baseline-proposal.md` | Proposes decisions for aligning requirements, architecture, and implementation |
| Requirements Traceability Matrix draft | `docs/rtm_draft.csv` | Maps requirements to implementation and testing references |
| Test catalogue | `docs/test_catalogue.md` | Organizes test cases and test coverage information |
| Deviations log | `DEVIATIONS.md` | Records differences between the implementation and the SRS, SAD, and STP |

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
│   ├── decisions/                  # Baseline decision proposal
│   ├── rtm_draft.csv               # Requirements traceability draft
│   └── test_catalogue.md           # Test catalogue
├── src/
│   └── tms_sim/
│       ├── network/                # Road network models and validation
│       ├── signal/                 # Signal-plan models and validation
│       ├── sim/                    # Demand generation, engine, scenarios
│       ├── ui/                     # Desktop workbench and scenario library UI
│       └── storage/                # SQLite scenario and run-record storage
├── tests/
│   ├── data/                       # Network, signal and scenario fixtures
│   ├── signal/                     # Signal-plan tests
│   ├── test_demand.py
│   ├── test_engine.py
│   ├── test_network.py
│   ├── test_scenario.py
│   ├── test_store.py               # Scenario and run-store tests
│   ├── test_ui_scenario_library.py # Scenario library UI tests
│   ├── test_ui_polish.py
│   └── test_smoke.py
├── DEVIATIONS.md                   # Specification deviations
├── pyproject.toml                  # Project metadata and dependencies
└── README.md
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

```bash
python -m pytest
```

The suite includes tests for:

- Network validation
- Signal-plan validation and behaviour
- Vehicle demand generation
- Simulation engine functionality
- Scenario execution
- Scenario and run-record storage
- Scenario library UI workflows
- Application workbench behaviour and cleanup

The latest verified full test run completed with **385 tests passed** under Python 3.11, with a successful process exit.

### Continuous Integration

GitHub Actions runs the test suite on pushes to `main` and pull requests. The workflow uses Windows and Python 3.11, installs the project with its development dependencies, and runs `python -m pytest`. The latest workflow run for commit `89b8366` completed successfully.

## Development Status and Future Work

Implementation and testing are ongoing. Future work may include:

- Interactive road network editing.
- Full 2D visualization of traffic flow and signal states.
- Traffic performance metrics and comparison between simulation runs.
- CSV reporting and export of simulation results.
- Additional scenario configurations and traffic models.
- Expanded integration, usability, and performance testing.
- Continued alignment between implementation, requirements, architecture, and the test plan.

Scenario storage and run-record persistence are already implemented. Check `DEVIATIONS.md`, the test catalogue, and project documentation for current implementation status and outstanding deviations.

## Institution and Course

**Institution:** PES University  
**Course:** Software Engineering  
**Course code:** UE24CS341A

## License

This project is developed for academic purposes as part of the Software Engineering course at PES University.

PySide6 is distributed under the GNU Lesser General Public License (LGPL). Consult the applicable license terms when redistributing the application or its dependencies.
