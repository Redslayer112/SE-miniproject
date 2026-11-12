# CI/CD Pipeline

Workflow file: `.github/workflows/ci.yml` (GitHub Actions). Results are on the repository's **Actions** tab and on every pull request.

## Triggers

| Event | What runs |
|---|---|
| Pull request (any branch) | Lint, Windows tests with coverage gate, Linux tests, build and smoke test (CI) |
| Push to `main` (every merge) | The same CI stages, so `main` is always re-verified after a merge |
| Push of a version tag `v*` (for example `v1.0`) | The same CI stages, then **Release** (CD) |
| Manual (`workflow_dispatch`) | The same CI stages, from the Actions tab |

A newer push to the same pull request cancels the older run.

## Stages

```
pull request / push to main / tag v*
        │
        ├── lint ─────────┐   ruff: syntax errors and undefined names
        ├── test ─────────┤   Windows, Python 3.11, full suite + coverage, fails under 80%
        ├── test-linux ───┘   Ubuntu, Python 3.11, full suite, Qt offscreen
        │
        ▼
      build                   sdist + wheel, wheel installed in a clean venv and run headless
        │
        ▼  (only for tags v*)
     release                  GitHub Release: wheel, sdist, SRS/SAD/Test Plan v1.1 PDFs
```

| Stage | Job | Checks | Fails when | Output |
|---|---|---|---|---|
| 1. Static analysis | `lint` | `ruff check --select E9,F63,F7,F82` on `src`, `tests`, `scripts` | Syntax error, undefined name, invalid comparison or misplaced statement | Annotations on the PR |
| 2a. Test (target platform) | `test` | `pytest` under `coverage` with branch measurement on `windows-latest`, Python 3.11 | Any test fails, the process exits non-zero, or statement+branch coverage is below 80% | `coverage-report` artifact (XML and HTML) |
| 2b. Test (portability) | `test-linux` | `pytest` on `ubuntu-latest` with `QT_QPA_PLATFORM=offscreen` | Any test fails | — |
| 3. Build | `build` | `python -m build`; the wheel is installed into a fresh virtual environment and runs `python -m tms_sim run` on the sample scenario | The package does not build, does not install, or the run does not complete 30 vehicles | `dist` artifact (wheel and sdist) |
| 4. Release (CD) | `release` | Tag name equals `v` + the version in `pyproject.toml` | Tag and version disagree | GitHub Release with generated notes, the package, and the v1.1 documents |

`build` runs only if all of stage 1 and 2 pass; `release` runs only if `build` passes and the ref is a `v*` tag.

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
   The `release` job then publishes the GitHub Release. Bump `version` in `pyproject.toml` before tagging a new release.

## Why these choices

- **Windows is the primary test platform** because the SRS targets Windows; Linux runs as a second platform for portability evidence (TMS-NF-004).
- **Lint only fails on real errors.** A full style check reports about 60 existing issues (mostly unused imports), so the gate is limited to defects that break code.
- **Coverage gate at 80%.** Measured statement+branch coverage is 86% (597 tests), so the gate catches a real drop without failing on noise.
- **The build is smoke-tested,** not only built, so a packaging mistake (a missing module or an entry point) fails CI instead of reaching a release.
- **Deployment is a GitHub Release,** because TMS-Sim is a desktop application: there is no server to deploy to. Users install the wheel with `pip install tms_sim-1.0-py3-none-any.whl` and run `python -m tms_sim`.

## History

| Change | PR |
|---|---|
| First workflow: `pytest` on Windows, Python 3.11 (issue #13) | #14 |
| Prints the pytest process exit code | #24 |
| Explicit Qt teardown fixes an intermittent non-zero exit after all tests pass | #25 |
| Full CI/CD: lint, coverage gate, Linux job, build and smoke test, tag-driven release | this change |
