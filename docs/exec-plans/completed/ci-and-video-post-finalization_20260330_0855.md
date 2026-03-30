# ci and video post finalization plan

## Overview

Resume the interrupted CI / X video posting work after `9868085`, `2eae975`, and `dda1886`, using the current dirty worktree as the starting point instead of redoing completed fixes. The known remaining gap is:

- CI needs the real `twikit==2.3.3` dependency available for `tests/test_twikit_compat.py`
- live `post_video.yml` still needs the runtime path to survive the `ClientTransaction` / `x_client_transaction` breakage that produced `compat: ondemand hash not found`

This plan is the single execution plan for the remaining work and supersedes open overlap in:

- `docs/exec-plans/active/ci-and-video-post-verification_20260329_1350.md`
- `docs/exec-plans/active/twikit-compat-fix_20260330_0010.md`
- `docs/exec-plans/active/xclient-transaction-fallback-fix_20260330_0939.md`

Checked against other active plans in `docs/exec-plans/active/`:

- `automation-ecosystem-research_20260329_1626.md` — research only, no CI/video overlap
- `post-buz-live-verification_20260328_1903.md` — `post_buz` only, no overlap
- `post-buz-secret-rerun_20260328_2042.md` — `post_buz` only, no overlap
- `post-invest-rerun-assessment_20260328_1939.md` — `post_invest` only, no overlap
- `skill-article-deepresearch_20260329_1410.md` — research only, no CI/video overlap

## Current worktree state / starting point

The dirty worktree already contains in-progress edits that should be treated as the implementation starting point, not discarded:

- `.github/workflows/ci.yml` already adds `twikit==2.3.3`
- `.github/workflows/post_video.yml` already adds `XClientTransaction==1.0.2`
- `scripts/lib/post_video.py` already contains an `x_client_transaction` adapter/fallback implementation in progress
- `tests/test_post_video.py` already contains regression coverage for import/setup fallback and adapter-init failure
- `README.md` already documents the runtime dependency changes in progress

So the remaining work begins with verification/gap analysis of these edits, then completion of any missing fixes, validation, workflow reruns, review, and commit/push.

## Goal

1. Make `ci.yml` green with the real test dependency surface.
2. Make `post_video.yml` prefer `XClientTransaction` but fall back safely when its runtime path fails.
3. Cover the discovered regression with tests before final production edits.
4. Finish review, commit, push, and move the related plans to `completed/`.

## Out of scope

- No expansion beyond the existing manual `post_video.yml` workflow
- No changes to non-video posting flows
- No refactor of unrelated workflow/dependency management
- No cleanup of unrelated active plan files

## Files to modify or move

- `.github/workflows/ci.yml`
- `.github/workflows/post_video.yml`
- `scripts/lib/post_video.py`
- `tests/test_post_video.py`
- `README.md`
- `docs/exec-plans/active/ci-and-video-post-finalization_20260330_0855.md`
- Move to `docs/exec-plans/completed/` when done:
  - `docs/exec-plans/active/ci-and-video-post-verification_20260329_1350.md`
  - `docs/exec-plans/active/twikit-compat-fix_20260330_0010.md`
  - `docs/exec-plans/active/xclient-transaction-fallback-fix_20260330_0939.md`
  - `docs/exec-plans/active/ci-and-video-post-finalization_20260330_0855.md`

## Expected impact

- `ci.yml` installs the dependencies required by the current Python tests, including `tests/test_twikit_compat.py`
- `post_video.yml` installs the runtime libraries needed by the current live posting path
- `scripts/lib/post_video.py` uses `XClientTransaction` when it works and explicitly falls back to the repo-local twikit compatibility patch when setup/init fails
- regression coverage protects both the import/setup fallback and the adapter-init failure path

## Test strategy

### RED

- Use the already observed failures as the initial red signal:
  - CI rerun failed because `tests/test_twikit_compat.py` imports `twikit`
  - live rerun failed after the first compat fix with `compat: ondemand hash not found`
- If the current local changes do not already encode the necessary RED coverage, add/adjust failing tests in `tests/test_post_video.py` first.

### GREEN

- Keep the existing `ci.yml` dependency fix if it matches the failing CI signal.
- Complete the minimal runtime fallback in `scripts/lib/post_video.py` so live posting can recover from `x_client_transaction` setup/init failures.
- Update operator docs only where they now describe required runtime dependencies or fallback behavior.

### REFACTOR

- Keep fallback logic narrow and explicit.
- Avoid broad retry machinery or silent error swallowing.
- Recheck that dry-run behavior and payload shape stay unchanged.

## Validation commands

- `python3 -m unittest tests.test_post_video tests.test_twikit_compat -v`
- `python3 -m unittest discover -s tests`
- `python3 -m pip install coverage` if `python3 -m coverage --version` is unavailable in the validation environment, because this repository requires confirming 80%+ coverage before commit
- `python3 -m coverage run -m unittest discover -s tests && python3 -m coverage report --fail-under=80`
- `python3 -m py_compile $(find python scripts/lib -type f -name '*.py' ! -path '*/.*' ! -path '*/.venv/*' | sort)`
- `bash -n $(find scripts -type f -name '*.sh' | sort)`
- YAML parse for `config/*.yaml` and `.github/workflows/*.yml`
- `git diff --check`
- GitHub Actions verification of `ci.yml`
- GitHub Actions verification of `post_video.yml` in dry-run and, if secrets/runtime permit, live mode

## Risks / watch-outs

- Live posting is an external side effect and may still fail for X-side reasons even after the code path is locally correct.
- The adapter fallback may still lose the first live attempt if initialization fails mid-request; the fix must at least restore the original client transaction path deterministically and surface the failure clearly.
- The repo is on `main` with unrelated untracked exec-plan files; commit scope must stay deliberate.

## Implementation steps

- [ ] 1. Confirm the current baseline from the dirty worktree and latest workflow failures without discarding existing edits.
- [ ] 2. Ensure RED coverage exists for:
  - `configure_client_transaction_backend()` fallback on non-`ImportError`
  - `_XClientTransactionAdapter.init()` fallback + original client transaction restore
- [ ] 3. Only if gaps remain after step 2, finish the production/workflow/docs changes needed to satisfy those failures while preserving dry-run behavior.
- [ ] 4. Run local validation, including the targeted tests, full unit suite, syntax checks, YAML validation, and coverage when available.
- [ ] 5. Re-run GitHub Actions until `ci.yml` is green and `post_video.yml` reaches the expected dry-run/live result or a clearly documented external blocker remains.
- [ ] 6. Run a dedicated review sub-agent with `GPT-5.4` on the final diff and address any substantive findings.
- [ ] 7. Add or move the superseded active plans into `docs/exec-plans/completed/` as appropriate for tracked vs. currently untracked files, commit with a Conventional Commit, push `main`, and verify local/remote sync.
