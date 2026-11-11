# TC-PERF-01 — Latest full-run performance report

- **Recorded:** 2026-11-03 13:35:19 UTC benchmark start (artifact metadata)
- **Artifact:** `artifacts/issue12/tc_perf_01_full_run_pause_provenance_v1.json`
- **Branch/HEAD inspected:** `issue-12/4x-acceptance` / `5a64be2013aa80844f2909d02e04fe2e8aba67bf` (working-tree instrumentation changes were present; no commit or push was made)
**Status:** **FPS requirement failed; artifact is not acceptance-eligible.**

## Run result

| Field | Actual result |
|---|---|
| Scenario | `fixtures/valid/performance_10_intersections.json` |
| Seed / playback | 42 / 1.0× |
| Requested duration | 3,600 simulated seconds |
| Actual duration / completion | 3,600.1 seconds / finished normally |
| Frames | 72,055 |
| Full-run elapsed interval | 5,437.181 wall seconds between first and last paint |
| Total measurement wall duration | 5,437.47 seconds |
| FPS formula | `(72,055 - 1) / 5,437.181` |
| Full-run average FPS | **13.25** (required: **>= 15**) |
| Other render data | Rolling FPS 15.2; average paint time 2.52 ms; full-run average paint time 3.32 ms |
| Demand | 470 vehicles generated; the fixture configures a rate of 500 vehicles/hour, not a guaranteed realized count of 500 |
| Benchmark process | Exit code 0; `benchmark_execution_succeeded=true`; no execution error |
| Storage and cleanup | No storage errors; isolated temporary DB preflight passed; application cleanup succeeded |
| Engine transitions | stopped → running (`start`); running → stopped (`completion`); no intermediate pause recorded |
| Input evidence | 7 spontaneous external mouse ingress records and 40 target-delivery traces; native-action identity unavailable; `input_recording_unambiguous=false` |
| Overall eligibility | `false`: FPS is below threshold and external input provenance is uncertain |

The measured run reached the requested simulated hour and did not crash or pause. Its measured full-run FPS is below the 15 FPS target. The seven Qt-spontaneous mouse inputs are classified as external to the application; the evidence does not establish whether they came from a person, automation, accessibility software, or another system source. They remain disqualifying. “Not synthesized” in Qt mouse metadata does not establish a human operator.

The artifact reports `platform=Windows-11-10.0.26300-SP0`, Python 3.13.7, and processor string `AMD64 Family 23 Model 160 Stepping 0, AuthenticAMD`. The SRS/STP reference hardware is an Intel i5-11400H system; this artifact does not verify that reference hardware, nor does it report RAM. Treat 13.25 FPS as the result on the recorded host, not as a controlled reference-hardware measurement.

## Historical artifacts

These files are retained unchanged. They are not substitutes for the latest run; earlier acceptance flags predate the current eligibility checks or their run/input conditions differ.

| Artifact | Simulated seconds | FPS | Interpretation |
|---|---:|---:|---|
| `tc_perf_01_full_run_manual.json` | 3,600.1 | 7.85 | Historical complete run |
| `tc_perf_01_full_run_optimized.json` | 3,600.1 | 8.42 | Historical complete run |
| `tc_perf_01_full_run_stage4.json` | 3,600.1 | 8.43 | Historical complete run |
| `tc_perf_01_full_run_incremental_1x.json` | 3,600.1 | 15.98 | Historical complete run; 189 legacy input events, missing final process exit evidence; not a clean acceptance result |
| `tc_perf_01_full_run_final_clean_v2.json` | 3,181.2 | 14.25 | Incomplete; process exit 1; not a final FPS result |
| `tc_perf_01_incremental_5min.json` | 300.1 | 15.92 | Short diagnostic only; not the one-hour criterion |
| `tc_perf_01_full_run_pause_provenance_v1.json` | 3,600.1 | **13.25** | Latest complete run; below target and input provenance uncertain |

The earlier artifacts remain useful for historical comparison, but their legacy `acceptance_eligible` values do not override the current evidence. The 15 FPS threshold and approved full-run formula were not changed.

Two preserved 30-second diagnostics, `tc_perf_01_diagnostic_pause_provenance_30s.json` and `tc_perf_01_diagnostic_30s_fix_validation.json`, were found to have legacy `acceptance_eligible=true` labels. The earlier finalizer omitted the one-hour/1x run-configuration condition. The current finalizer now checks for at least 3,600 requested simulated seconds and requested/actual speed of 1x; regression tests cover 30-second and non-1x candidates. The old JSON artifacts are retained unchanged and must be read as diagnostic only.

## Remaining performance work

TC-PERF-01 is **not passed**. The latest result is below threshold, the run is not acceptance-eligible because external input identity is uncertain, and the artifact does not establish execution on the SRS reference CPU. Do not replace the one-hour criterion with the 300-second or 4× results. Any further one-hour attempt requires a separately agreed, controlled run plan and a new output path; this report does not launch or request that run.
