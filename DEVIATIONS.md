# Deviations from SRS / SAD / STP

Running list for the final demo (Part-2 deliverable 2i). Add a row whenever the code differs from a submitted document.

| # | Document ref | Submitted | Implemented | Why | Issue |
|---|---|---|---|---|---|
| 1 | SRS TMS-F-041 | Speed multipliers 0.5×, 1×, 2×, 4×, 8×, unbounded | 0.5×, 1×, 2×, 4× | Issue #7 scoped to these four | #7 |
| 2 | SRS TMS-F-030 | Arrival rates with turning ratios per approach, or an OD matrix | Rates per entry segment, ratios for the first movement only; later intersections take the lowest-id movement | Sprint 1 scope; OD matrix deferred | #6 |
| 3 | SRS §4.2 (stop control) | Stop-controlled intersections | Treated like yield (no full stop before the gap check) | Simpler gap model; confirmed in #1 (item 6b) | #7 |
| 4 | SRS TMS-F-040 | Documented car-following and gap-acceptance model | IDM + 3 s critical gap, single 5 m vehicle, `v0` = speed limit (no override); values in `docs/decisions/0001` | Approved in #1 (items 6, 6a, 6b) | #1, #7 |
| 5 | SRS §4.1, §4.8, §5.1 | Accounts, roles, admin, audit log | Not implemented | Deferred for v1 by team decision (#1 item 1): local single-Analyst app | #1 |
| 6 | SAD §4.3 | `generateVehicles(seed, arrivalRates, turningRatios)` | `generate_vehicles(seed, rates, ratios, *, duration_s)` | A duration is needed to bound the arrival stream | #6 |
| 7 | SRS TMS-F-061 | Share scenarios/runs read-only | Not implemented; library is local to one machine | Single-user desktop scope (#1 item 1) | #9 |
| 8 | SRS TMS-NF-001 / STP TC-PERF-01 | Reference scenario ≥ 15 FPS over a full one-hour 1× GUI run | Not accepted: the one recorded 1× run stalled at 2,123.6 s simulated (cause undetermined); 4× diagnostic runs completed | Blocker logged in `artifacts/issue12/defect_log.md`; needs an interaction-free foreground rerun | #12 |
| 9 | SRS TMS-NF-002 / STP TC-REL-01 | Three clean one-hour GUI runs | 1 of 3 clean (4×, seed 42); seeds 43/44 were paused by mouse input | Evidence in `artifacts/issue12/`; rerun without interaction | #12 |
| 10 | SRS TMS-NF-003 / STP TC-UX-01 | Moderated usability test with new users | Not performed | No new-user participants were available in the project window | #12 |
| 11 | SRS TMS-NF-004 / STP TC-PORT-01 | Clean Windows 10 and Windows 11 machines | Not performed on clean machines; the suite runs on GitHub Actions Windows (Python 3.11) and on team laptops | No clean test machines available | #12 |
| 12 | SRS TMS-F-021, TMS-F-031 | Listed in SRS §6.3 ranges | Retired (no requirement text): fixed-time control only, one 5 m vehicle type | #1 item 4 | #1 |
| 13 | STP TC-REL-01 | Reliability validation through GUI execution | Three independently supervised headless simulation-engine runs using seeds 42, 43 and 44; GUI, Workbench and operating-system reliability are not established | Headless execution approved by the project owner and collaborator in Issue #12; provides repeatable engine-level reliability evidence without claiming GUI reliability | #12 |