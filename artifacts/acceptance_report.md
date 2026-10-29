# Preliminary System Acceptance Test Report

- Generated (UTC): 2026-10-29T06:06:07.797093+00:00
- Python version: 3.13.7
- Platform: Windows-11-10.0.26300-SP0
- GUI scenario: C:\Users\vikhy\OneDrive\Documents\Desktop\sem-5\ALL-LAB\SE-LAB\SE-miniproject\fixtures\valid\performance_10_intersections.json

## 1. Headless load-test results

| Run | Simulated seconds | Elapsed seconds | CPU seconds | Peak Python memory (bytes) | Generated | Completed | In network |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3600.10 | 2.337051 | 1.984375 | 371453 | 470 | 469 | 1 |
| 2 | 3600.10 | 1.574534 | 1.546875 | 227667 | 470 | 469 | 1 |
| 3 | 3600.10 | 1.597480 | 1.578125 | 226771 | 470 | 469 | 1 |

## 2. GUI performance measurement

- Simulation finished: **YES**
- Simulated duration: 3600.1 seconds
- Wall-clock measurement duration: 1130.5 seconds
- Vehicles generated: 470
- Vehicles remaining in network: 1
- Recorded FPS samples: 1130
- Mean sampled FPS: 15.98
- Median sampled FPS: 16.00
- Minimum sampled FPS: 0.30
- Maximum sampled FPS: 16.60
- Samples at or above 15 FPS: 1116
- Samples below 15 FPS: 14
- Percentage of samples at or above 15 FPS: 98.76%
- Final full-interval FPS: 9.66
- Final average frame-render time: 3.27 ms

## 3. Preliminary checks

- Headless vehicle-count repeatability: PASS
- GUI simulation reached finished state: OBSERVED
- GUI FPS acceptance: **NOT PASSED / NEEDS REVIEW**; final full-interval FPS must be reconciled with the agreed criterion.
- GUI mean sampled FPS is descriptive only and does not replace the agreed acceptance measurement.
- Total process RAM: NOT MEASURED
- TC-DEM-02 same-seed comparison of all required metrics: NOT YET VERIFIED
- TC-REL-01, TC-UX-01, and TC-PORT-01: NOT YET VERIFIED
- Full analyst workflow: NOT YET VERIFIED

## 4. Limitations and follow-up

The headless load test and GUI performance test are separate measurements. Traced Python memory is not total process RAM. The scenario used a demand rate of 500 vehicles/hour but generated 470 vehicles in the observed runs. The GUI completed the configured simulation, with one vehicle remaining in the network. Acceptance thresholds and the required FPS aggregation method must be confirmed against the approved requirements before sign-off.

## 5. Sign-off

- Tester: Pending
- Reviewer: Pending
- Final acceptance: Pending
