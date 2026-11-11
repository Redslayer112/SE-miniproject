# Baseline amendment v1.1 — SRS, SAD and STP

**Applies to:** `PES2UG24CS579_569_583_586_SRS.pdf` (identifies itself as v0.2), `PES2UG24CS579_569_583_586_SAD.pdf` (v1.0), `PES2UG24CS579_569 _583_586_Test_Plan.pdf` (STP v1.0).
**Authority:** decisions approved by all four teammates on issue #1, recorded with rationale in [`decisions/0001-baseline-proposal.md`](decisions/0001-baseline-proposal.md).
**Rule:** where this amendment and a submitted PDF disagree, this amendment wins. The PDFs are kept unchanged as submitted, and this file is the change record for the final demo. Code-level differences that remain are listed in [`../DEVIATIONS.md`](../DEVIATIONS.md).

## SRS

| Section | Amendment | #1 item |
|---|---|---|
| Cover / revision history | The authoritative revision is **v1.0**. The PDF's "0.2 (Simplified draft)" label and its v0.2 history row are kept as history | 2 |
| §1.2 Scope, §4.1, §4.8, §5.1 | User accounts, roles, administration and the audit log are **out of scope for v1**. TMS-Sim is a local, single-Analyst desktop application. Security in v1 is limited to validating every scenario file before use and keeping data on the local disk | 1 |
| §2.4 Operating environment | Storage is **SQLite** (stdlib `sqlite3`) for the scenario library and completed runs, plus versioned JSON (`schema_version` "1.0") for import/export | 5 |
| §4.4 Traffic demand | Schema: `demand.arrival_rates_vehicles_per_hour` {entry segment: veh/h ≥ 0}, `demand.turning_ratios` {movement id: ratio; each entry's ratios sum to 1 ±1e-6}, `simulation.seed`, `simulation.duration_s` > 0, `simulation.time_step_s` 0.1–1.0 s | 5 |
| §4.4 (TMS-F-031) | Retired: no requirement text. One vehicle type, length 5.0 m | 4, 6 |
| §4.3 (TMS-F-021) | Retired: no requirement text. Control is fixed-time only | 4 |
| §4.5 TMS-F-040 | Car-following is the IDM with `v0` = segment speed limit, `a_max` 1.5 m/s², `b` 2.0 m/s², `s0` 2.0 m, `T` 1.5 s, braking floor 9 m/s², vehicle length 5.0 m. Signals: only green is green. A vehicle that physically cannot stop when the light changes may clear on yellow. Gap acceptance: 3.0 s critical gap at stop- and yield-controlled intersections (see decision record 6–6b) | 6 |
| §4.3 TMS-F-022 | Conflicting movements: crossing or merging paths conflict. The same-approach exception applies only toward different receiving segments. A missing position is a located error. Left-hand traffic, y-up coordinates | 9 |
| §5 TMS-NF-001..004 | Measurable criteria: FPS = average over the full one-hour run on the reference hardware (i5-11400H, 16 GB). The reference scenario is `fixtures/valid/performance_10_intersections.json`. Reliability = three clean one-hour runs. Usability = moderated new-user test. Portability = clean Windows 10 and 11 runs | 3 |
| §8 RTM | Superseded by `docs/RTM.csv` | 4 |

## SAD

| Section | Amendment | #1 item |
|---|---|---|
| §3.6 Technology stack & data stores | SQLite (stdlib) for the library and runs; versioned JSON for exchange. No other runtime dependency besides PySide6 | 5 |
| §3.9 Security architecture | Access control deferred (see SRS §4.1 above). Boundary checks are scenario schema and version validation before any data is used | 1 |
| §4.3 API design | Interfaces as implemented: `NetworkService` (`validateNetwork`/`loadNetwork`/`provideNetworkState`), `SignalService` (`validateSignalPlan(plan, network)`/`provideSignalPlan`), `generate_vehicles(seed, rates, ratios, *, duration_s)`, the `Engine` controls and `events`, and `ScenarioStore` (`saveScenario`/`loadScenario`/`listScenarios`/`saveRun`, plus duplicate/rename/delete/import/export). The validation result is a list of issues (element id, element type, code, message, severity). Valid means zero errors, and warnings never block a run | 8 |
| §4.6 Open issues | The component interfaces are finalised by this amendment | 8 |

## STP

| Section | Amendment | #1 item |
|---|---|---|
| §5.1 Security validation | Limited to safe local input and storage: oversized, malformed and wrong-version scenario files are rejected before parsing or storing | 1 |
| §6 Test environment, *Tools* | **GitHub Issues and GitHub Actions** (Windows, Python 3.11) replace Jira. The test framework is pytest | 7 |
| §7 Test schedule | Replace the September dates: execution follows the sprints. Sprint 1 ran 19–27 Oct 2026 and Sprint 2 runs 27 Oct–6 Nov 2026. Acceptance evidence is in `docs/test_execution_record.md` and `artifacts/` | 7 |
| §13 Traceability | Superseded by `docs/RTM.csv`, which adds rows for TMS-F-011/013/042/051/052 | 4 |
| §14 Metrics & reporting | Each test row reports pass/fail plus the pytest process exit status from CI | 3 |
