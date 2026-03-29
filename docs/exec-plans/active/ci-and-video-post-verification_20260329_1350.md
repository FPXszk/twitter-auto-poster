# ci and video post verification plan

## Overview

Investigate the repeatedly failing `ci.yml` workflow, apply the minimal fix that restores green CI, and verify whether the repository's X video posting path can complete a real post. The current evidence already points to an environment mismatch in CI and an unverified live path for `post_video.yml`.

Confirmed findings so far:

- Latest failing CI run: `23705956816` (`.github/workflows/ci.yml`, commit `98680852355fab1575086b6f2ce25beb252bdf69`)
- The failure occurs in `Run unit tests`, not in shell/YAML validation
- Job logs show missing runtime dependencies during test import:
  - `yfinance`
  - `pandas`
  - `xlrd`
  - `twitter_cli`
- Current `ci.yml` installs only `pyyaml`, so CI does not match the dependency surface required by the existing test suite
- `post_video.yml` exists and the repository has a local/manual video posting entry point, but no completed `post_video.yml` runs were found during this investigation
- `tests/test_post_video.py` currently validates helper behavior and a mocked live-post path, but it does not prove that a real GitHub Actions live post has succeeded

## Goal

1. Restore `ci.yml` by making its test environment consistent with the repository's existing test imports
2. Verify whether the video posting path can successfully publish a real X post, and fix any directly related defects if the live check fails

## Non-goals

- No expansion of automated video generation or scheduled video posting
- No broad dependency-management refactor unless it is required to make CI reliable
- No unrelated cleanup of legacy workflows or test modules
- No live tweet unless explicitly approved by the user during the PLAN approval step

## Files expected to be involved

- `.github/workflows/ci.yml`
  - likely update validation dependency installation for the existing test suite
- `.github/workflows/post_video.yml`
  - only if the live/manual verification reveals a workflow-specific defect
- `python/post_video.py`
  - only if live/manual verification reveals a runtime defect in the CLI entry point
- `python/update_tickers_jp.py`
  - not expected to change first, but included because its import path is part of the current CI dependency failure (`xlrd`)
- `scripts/lib/post_video.py`
  - only if live/manual verification reveals a runtime defect in the video publish helper
- `tests/test_post_video.py`
  - extend first if a video-posting bug is found and needs a regression test
- `README.md`
  - update only if operator instructions must change because of the fix
- `docs/exec-plans/active/ci-and-video-post-verification_20260329_1350.md`
  - this execution plan

## Scope notes

- Existing active exec-plans were checked and none overlap directly with this CI + video verification task; current active plans are research/other operational topics rather than CI dependency restoration or `post_video.yml` verification
- The initial CI root cause appears to be workflow dependency setup, so start there before touching application logic
- The video-post verification should prefer the existing manual `post_video.yml` path so the real operational workflow is tested, not just a local mock
- The repository has no `requirements.txt`, `pyproject.toml`, `setup.py`, or `setup.cfg`, so the default plan is to keep the fix narrow by updating `ci.yml` with the smallest complete dependency set required by the current tests rather than introducing a new dependency-management scheme unless that becomes necessary during implementation

## Test strategy

### RED

- Treat the current failing GitHub Actions run as the initial RED signal for CI
- Reproduce the CI dependency mismatch locally in a clean Python environment if needed
- If the live video-post check reveals a runtime defect, add or extend a failing regression test in `tests/test_post_video.py` before fixing production code

### GREEN

- Update the minimal workflow/runtime surface needed to make CI pass
- Re-run the repository validation commands locally
- Execute a manual `post_video.yml` run:
  - first in `dry_run` via `gh workflow run post_video.yml -f text='...' -f video_url='...' -f dry_run=true`
  - then in live mode only if explicitly approved by the user

### REFACTOR

- Keep fixes narrow
- Only extract/shared dependency handling if the same CI problem would otherwise remain fragile
- Preserve the existing text/image posting path untouched

## Validation commands

- `python3 -m unittest discover -s tests`
- `python3 -m py_compile $(find python scripts/lib -type f -name '*.py' ! -path '*/.*' ! -path '*/.venv/*' | sort)`
- `bash -n $(find scripts -type f -name '*.sh' | sort)`
- YAML parse for `config/*.yaml` and `.github/workflows/*.yml`
- `git diff --check`
- If `.github/workflows/ci.yml` changes, verify locally first, then confirm the next automatic CI run on `main` is green (there is no `workflow_dispatch` for `ci.yml`)
- If video posting changes are made, run `post_video.yml` dry-run and live-run verification as appropriate
- For `post_video.yml`, treat success as:
  - dry-run: artifact/result JSON shows `ok: true`, `action: dry_run_video`, and no runtime error
  - live-run: artifact/result JSON shows `ok: true`, `action: post_video`, and a non-empty tweet ID / URL

## Risks / watch-outs

- Installing too many ad hoc packages in CI can mask the real dependency boundary; prefer the smallest complete set that matches the current tests
- A live video post is an external side effect and must not happen without explicit approval
- Video posting depends on valid X cookies/secrets and a reachable MP4 asset; choose a stable, publicly reachable small MP4 URL for workflow dispatch, and treat asset/download failures separately from posting-code failures
- GitHub-hosted runner behavior can differ from the local environment, so workflow verification must include at least one GitHub Actions rerun

## Implementation steps

- [x] 1. Confirm the exact dependency gap in `ci.yml` and decide the minimal install set that matches the existing tests
- [x] 2. Apply the CI fix using TDD discipline where possible (existing RED from failing CI; add regression coverage first if code changes become necessary)
- [x] 3. Run local validation commands and confirm the failure is not reproducible anymore
- [ ] 4. Trigger or monitor a fresh CI run to verify the workflow fix on GitHub Actions
- [ ] 5. Verify the video posting path via `post_video.yml` dry-run, then perform a live example post only if the user explicitly approves it
- [x] 6. If the live post path fails, add/extend regression tests first, then fix the smallest relevant code/workflow surface and re-verify
- [ ] 7. Update directly affected documentation only if behavior or operator steps changed
