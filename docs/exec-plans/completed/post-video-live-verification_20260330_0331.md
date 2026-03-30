# post video live verification plan

## Overview

Verify whether the current `main` branch can complete a real live `post_video.yml` run after the CI/fallback fixes landed in `37ada07`.

This is a verification-only follow-up to:

- `docs/exec-plans/completed/ci-and-video-post-finalization_20260330_0855.md`

## Goal

1. Dispatch `post_video.yml` with `dry_run=false` on `main`.
2. Monitor the workflow to completion.
3. Confirm whether the run produced a real tweet ID and URL.
4. If it fails, capture the exact runtime blocker without making unrelated changes.

## Out of scope

- No production code edits unless a new blocker is discovered and separately approved
- No unrelated workflow changes
- No cleanup of unrelated active plans
- No additional tweet posting beyond the single requested verification run

## Files and artifacts to inspect

- `.github/workflows/post_video.yml`
- `docs/exec-plans/active/post-video-live-verification_20260330_0331.md`
- Downloaded workflow artifacts under `tmp/post-video-live-<run-id>/`
- GitHub Actions run logs and summary for the dispatched `post_video.yml` run

## No-overlap check

Checked current active plans:

- `automation-ecosystem-research_20260329_1626.md` — research only, no overlap
- `post-buz-live-verification_20260328_1903.md` — `post_buz` only, no overlap
- `post-buz-secret-rerun_20260328_2042.md` — `post_buz` only, no overlap
- `post-invest-rerun-assessment_20260328_1939.md` — `post_invest` only, no overlap
- `skill-article-deepresearch_20260329_1410.md` — research only, no overlap

## Test strategy

### RED

- Treat a failing live workflow run as the RED signal.
- Do not add code changes during this verification-only task unless a new defect must be fixed in a follow-up task.

### GREEN

- A successful live run means:
  - workflow conclusion is `success`
  - result JSON top-level `ok` is `true`
  - result JSON `data.action` is `post_video`
  - result JSON `data.id` is non-empty
  - result JSON `data.url` is non-empty

### REFACTOR

- Not applicable unless a follow-up bug-fix task is opened.

## Validation commands

- `gh workflow run post_video.yml --ref main -f text='...' -f video_url='...' -f dry_run=false`
- `gh run watch <run-id> --exit-status`
- `gh run download <run-id> -n post-video-run -D tmp/post-video-live-<run-id>`
- inspect `tmp/post-video-live-<run-id>/post-video-result.json`

## Risks / watch-outs

- This task causes a real external side effect: an actual X post may be created.
- The run can still fail because of X-side anti-automation changes, cookie/session expiry, or upstream runtime drift.
- The workflow job has no explicit `timeout-minutes`; GitHub's default 6-hour timeout applies. If the run does not complete within about 15 minutes, cancel it with `gh run cancel <run-id>` and record the latest log output as the blocker.
- If the live run succeeds, the posted tweet should be treated as a deliberate verification artifact, not automatically deleted by this task.

## Implementation steps

- [ ] 1. Dispatch one live `post_video.yml` run on `main` using a known MP4 URL.
- [ ] 2. Wait for the workflow to finish with `gh run watch`. If it does not complete within about 15 minutes, cancel it with `gh run cancel <run-id>` and capture logs.
- [ ] 3. Report the exact success result (tweet ID/URL) or the exact blocker.
- [ ] 4. If further fixes are needed, stop after diagnosis and start a new PLAN step for the bug fix.
