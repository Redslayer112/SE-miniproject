# Deviations from SRS / SAD / STP

Running list for the final demo (Part-2 deliverable 2i). Add a row whenever the code differs from a submitted document.

| # | Document ref | Submitted | Implemented | Why | Issue |
|---|---|---|---|---|---|
| 1 | SRS TMS-F-041 | Speed multipliers 0.5×, 1×, 2×, 4×, 8×, unbounded | 0.5×, 1×, 2×, 4× | Issue #7 scoped to these four | #7 |
| 2 | SRS TMS-F-030 | Arrival rates with turning ratios per approach, or an OD matrix | Rates per entry segment, ratios for the first movement only; later intersections take the lowest-id movement | Sprint 1 scope; OD matrix deferred | #6 |
| 3 | SRS §4.2 (stop control) | Stop-controlled intersections | Treated like yield (no full stop before the gap check) | Simpler gap model; needs team decision in #1 | #7 |
| 4 | SRS TMS-F-040 | Documented car-following and gap-acceptance model | IDM + 3 s critical gap, parameters in `docs/decisions/0001` — **proposed, not yet approved** | #1 not signed off yet | #1, #7 |
| 5 | SRS §4.1, §4.8, §5.1 | Accounts, roles, admin, audit log | Not implemented | Scope undecided in #1 (SAD §3.9 / STP §5.1 conflict) | #1 |
| 6 | SAD §4.3 | `generateVehicles(seed, arrivalRates, turningRatios)` | `generate_vehicles(seed, rates, ratios, *, duration_s)` | A duration is needed to bound the arrival stream | #6 |
