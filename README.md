# Traffic Management System (Simulation)

**Software Engineering Project · UE24CS341A · PES University**

A Python-based traffic management simulation for modelling road networks, traffic signal plans, vehicle demand, and traffic flow. The project includes network and signal-plan validation, a simulation engine, scenario execution, and automated tests.

> **Development status:** Implementation and testing in progress. Some planned components, including interactive visualization, storage, and reporting, are not yet implemented.

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

The project aims to support the study of traffic behaviour under different configurations and provide a foundation for evaluating traffic flow and signal-management strategies.

## Team Members

| Team Member | SRN | Primary Responsibility |
|---|---|---|
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
- **Automated testing:** Tests network validation, signal plans, demand generation, simulation behaviour, scenarios, and the application workbench.

### Current UI Limitations

The desktop application currently provides a basic workbench window titled `TMS-Sim`. Interactive network editing, a full 2D traffic visualization, and complete reporting and storage workflows remain future development areas.

## Technology Stack

| Component | Technology |
|---|---|
| Programming language | Python 3.11 or later |
| Desktop UI framework | PySide6 |
| Build and package configuration | `setuptools` and `pyproject.toml` |
| Testing framework | `pytest` |
| Continuous integration | GitHub Actions |
| Version control | Git and GitHub |

PySide6 is declared as the project's runtime dependency. `pytest` is declared as a development dependency.

## Project Documentation

The repository includes the following supporting documents:

| Document | Location | Purpose |
|---|---|---|
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

The application opens the basic `TMS-Sim` workbench window. The current interface is a foundation for future UI development.

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
│   └── workflows/                 # GitHub Actions CI configuration
├── docs/
│   ├── decisions/                  # Baseline decision proposal
│   ├── rtm_draft.csv               # Requirements traceability draft
│   └── test_catalogue.md           # Test catalogue
├── src/
│   └── tms_sim/
│       ├── network/                # Road network models and validation
│       ├── signal/                 # Signal-plan models and validation
│       ├── sim/                    # Demand generation, engine, scenarios
│       ├── ui/                     # Desktop workbench
│       ├── storage/                # Storage package (implementation pending)
│       └── reporting/              # Reporting package (implementation pending)
├── tests/
│   ├── data/                       # Network, signal and scenario fixtures
│   ├── signal/                     # Signal-plan tests
│   ├── test_demand.py
│   ├── test_engine.py
│   ├── test_network.py
│   ├── test_scenario.py
│   └── test_smoke.py
├── DEVIATIONS.md                   # Specification deviations
├── pyproject.toml                  # Project metadata and dependencies
└── README.md
```

## Network Interface

**Reference:** SAD §4.3 — Interface 1: Network Editor → Simulation Engine

The network interface is implemented in `src/tms_sim/network/`. `NetworkService` exposes the documented SAD operations using both the specification's operation names and their Python-style equivalents.

| SAD operation | Python method | Behaviour |
|---|---|---|
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
- Application workbench smoke testing

A verified run on the development environment completed with **146 tests passed**. Test counts may change as the project evolves.

### Continuous Integration

GitHub Actions runs the test suite for pull requests and pushes to `main`. The current workflow uses Windows and Python 3.11, installs the project with its development dependencies, and runs `python -m pytest`.

## Development Status and Future Work

Implementation and testing are ongoing. Future work may include:

- Interactive road network editing.
- Full 2D visualization of traffic flow and signal states.
- Storage and retrieval of scenarios and completed simulation runs.
- Traffic performance metrics and report generation.
- Additional scenario configurations and traffic models.
- Expanded integration, usability, and performance testing.
- Continued alignment between implementation, requirements, architecture, and the test plan.

Implementation status and outstanding deviations should be checked against `DEVIATIONS.md` and the project documentation.

## Institution and Course

**Institution:** PES University  
**Course:** Software Engineering  
**Course code:** UE24CS341A

## License

This project is developed for academic purposes as part of the Software Engineering course at PES University.

PySide6 is distributed under the GNU Lesser General Public License (LGPL). Consult the applicable license terms when redistributing the application or its dependencies.
