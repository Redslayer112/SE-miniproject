# CI/CD Pipeline

Workflow file: `.github/workflows/ci.yml` (GitHub Actions). Results are on the repository's **Actions** tab and on every pull request. Below the pipeline graph, each run's summary page shows a **scorecard** for every stage (lint counts, test pass rate, coverage, build and smoke-test results) and a combined **Pipeline scorecard**. The scores are produced by `scripts/ci_report.py`.

## Triggers

| Event | What runs |
|---|---|
| Pull request (any branch) | Stages 1–3: lint, test with coverage gate, build and smoke test (CI) |
| Push to `main` (every merge) | Stages 1–3 again, so `main` is re-verified after every merge |
| Push of a version tag `v*` (for example `v1.0`) | Stages 1–3, then stage 4: **Release** (CD) |
| Manual (`workflow_dispatch`) | Stages 1–3, started from the Actions tab |

A newer push to the same pull request cancels the older run.

## Stages

```
pull request / push to main / tag v*
        │
        ├── 1 · Lint ─────────────────┐   ruff: syntax errors and undefined names
        ├── 2 · Test (Windows, 3.11) ─┘   full suite + branch coverage, fails under 80%
        │
        ▼
   3 · Build & smoke test                 sdist + wheel; wheel installed in a clean venv and run headless
        │
        ▼  (tags v* only)
   4 · Release                            GitHub Release: wheel, sdist, SRS/SAD/Test Plan v1.1 PDFs
        │
        ▼  (always, even if a stage fails)
   5 · Scorecard                          one table: every stage's status and score
```

| Stage | Job | Checks | Fails when | Output |
|---|---|---|---|---|
| 1. Static analysis | `1 · Lint` | `ruff check --select E9,F63,F7,F82` on `src`, `tests`, `scripts` | Syntax error, undefined name, invalid comparison or misplaced statement | Annotations on the PR |
| 2. Test | `2 · Test (Windows, Python 3.11)` | `pytest` under `coverage` with branch measurement on `windows-latest` | Any test fails, the process exits non-zero, or statement+branch coverage is below 80% | Coverage table in the run summary; `coverage-report` artifact (XML and HTML) |
| 3. Build | `3 · Build & smoke test` | `python -m build`; the wheel is installed into a fresh virtual environment and runs `python -m tms_sim run` on the sample scenario | The package does not build or install, or the run does not complete 30 vehicles | Build and smoke output in the run summary; `dist` artifact (wheel and sdist) |
| 4. Release (CD) | `4 · Release` | Tag name equals `v` + the version in `pyproject.toml` | Tag and version disagree | GitHub Release with generated notes, the package, and the v1.1 documents |
| 5. Report | `5 · Scorecard` | Collects every stage's result and scores | Never blocks | Pipeline scorecard in the run summary |

Stage 3 runs only if stages 1 and 2 both pass. Stage 4 runs only if stage 3 passes and the ref is a `v*` tag. Stage 5 always runs.

## Scores shown on each run

| Stage | Scores |
|---|---|
| 1 · Lint | Files checked, blocking errors (must be 0), pyflakes warnings (unused imports and variables), share of warning-free files, most frequent warning codes |
| 2 · Test | Tests run, passed, failed, skipped, pass rate, duration; statement, branch and combined coverage against the 80% gate; per-file coverage (expandable) |
| 3 · Build & smoke test | Wheel and sdist with sizes; vehicles completed by the installed wheel (expected 30) and mean travel time |
| 4 · Release | Link to the published release |
| 5 · Scorecard | All of the above in one table, with a status per stage |

Reference values on 12 Nov 2026 (local run of the same commands): 0 blocking lint errors, 64 pyflakes warnings, 55/72 files warning-free (76.4%); 597/597 tests passed; coverage 88.4% statements, 74.9% branches, 85.5% combined; wheel 102.6 KB; 30/30 vehicles, 16.4 s mean travel time.

## Development flow

1. The assigned member creates a branch and opens a pull request that names its issue (`Closes #N`).
2. The pipeline runs on the pull request; its result is shown on the PR.
3. The repository owner reviews and merges only when the pipeline is green.
4. The merge to `main` triggers the pipeline again.
5. A release is cut by tagging `main`:
   ```
   git checkout main && git pull
   git tag v1.0
   git push origin v1.0
   ```
   The `4 · Release` job then publishes the GitHub Release. Bump `version` in `pyproject.toml` before tagging a new release.

## Why these choices

- **Windows is the test platform** because the SRS targets Windows (TMS-NF-004). The suite also passes on Linux with Qt offscreen when run locally; a Linux CI job was tried and removed because the process aborted inside Qt during one Workbench integration test (`test_run_after_network_modification_is_auto_captured`) on the hosted Ubuntu runner only. The same test passes on Windows CI and on a local Linux machine, so it is recorded as a CI-environment limitation rather than a product defect.
- **Lint only fails on real errors.** A full style check reports about 60 existing issues (mostly unused imports), so the gate is limited to defects that break code.
- **Coverage gate at 80%.** Measured statement+branch coverage is 86% (597 tests), so the gate catches a real drop without failing on noise.
- **The build is smoke-tested,** not only built, so a packaging mistake (a missing module or entry point) fails CI instead of reaching a release.
- **Deployment is a GitHub Release,** because TMS-Sim is a desktop application with no server to deploy to. Users install the wheel with `pip install tms_sim-1.0-py3-none-any.whl` and run `python -m tms_sim`.

## History

| Change | PR |
|---|---|
| First workflow: `pytest` on Windows, Python 3.11 (issue #13) | #14 |
| Prints the pytest process exit code | #24 |
| Explicit Qt teardown fixes an intermittent non-zero exit after all tests pass | #25 |
| Full CI/CD: lint, coverage gate, build and smoke test, tag-driven release, per-stage scorecards | #48 |
