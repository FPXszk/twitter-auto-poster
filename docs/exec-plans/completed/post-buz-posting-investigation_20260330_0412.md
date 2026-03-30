# post_buz posting investigation plan

## Overview

Investigate whether recent `post_buz.yml` runs that concluded with `success` actually created X posts, or whether they ended successfully for another reason such as posting-window skip, no candidate selection, or other non-posting outcomes.

This investigation is prompted by the observation that recent `post_video.yml` live posting hit X `AuthorizationError (226)` at `CreateTweet`, raising the question of whether the text-posting workflow may also be affected.

This plan supersedes the open overlap in:

- `docs/exec-plans/active/post-buz-live-verification_20260328_1903.md`

## Goal

1. Determine what recent successful `post_buz.yml` runs actually did.
2. Confirm whether those runs produced tweet IDs / URLs or ended successfully without posting.
3. Assess whether there is evidence that X-side automation detection is also affecting `post_buz`.
4. If the evidence is inconclusive, identify the smallest next verification step rather than guessing.

## Out of scope

- No production code edits in this investigation pass
- No deletion or cleanup of existing posts
- No unrelated workflow changes
- No forced live rerun unless the evidence from existing runs is insufficient and a follow-up plan is approved

## Files and resources to inspect

- `.github/workflows/post_buz.yml`
- `scripts/lib/workflow_summary.py`
- `scripts/fetch_and_post.sh`
- recent GitHub Actions runs for `post_buz.yml`
- run summaries, job logs, and `buz-run` artifacts from selected runs

## No-overlap check

Checked current active plans:

- `automation-ecosystem-research_20260329_1626.md` — research only, no overlap
- `post-buz-live-verification_20260328_1903.md` — overlapping, superseded by this investigation plan
- `post-buz-secret-rerun_20260328_2042.md` — related history but different execution step; use only as reference
- `post-invest-rerun-assessment_20260328_1939.md` — `post_invest` only, no overlap
- `post-video-live-verification_20260330_0331.md` — `post_video` only, no overlap
- `skill-article-deepresearch_20260329_1410.md` — research only, no overlap

## Test strategy

### RED

- Treat evidence of `success` runs without tweet ID / URL as the initial red signal for “workflow success does not imply posting success.”
- Treat any explicit X-side authorization / automation rejection in logs as red evidence for the automation-detection hypothesis.

### GREEN

- A positive conclusion for “posting succeeded” requires evidence such as non-empty tweet ID / URL in artifacts, summary payloads, or logs.
- A positive conclusion for “no posting happened” requires evidence such as posting-window skip, no-candidate outcome, or artifact fields showing no tweet IDs.
- A positive conclusion for “automation detection affects post_buz” requires direct evidence from the `post_buz` path, not inference from `post_video` alone.

### REFACTOR

- Not applicable unless this investigation uncovers a concrete bug that needs a separate fix task.

## Validation commands / checks

- `gh run list --workflow post_buz.yml --limit 10` — identify recent runs
- for selected runs: `gh run view <run_id>` and inspect job logs / summary
- for selected runs: `gh run download <run_id> -n buz-run -D tmp/post-buz-<run_id>` and inspect artifact payloads for tweet ID / URL evidence
- inspect `scripts/lib/workflow_summary.py` / `scripts/fetch_and_post.sh` only as needed to interpret artifact fields and success conditions

## Risks / watch-outs

- `post_buz.yml` can legitimately conclude `success` without posting anything, so workflow conclusion alone is not enough evidence.
- Scheduled runs may execute outside the effective posting path or may have no candidate.
- Artifacts/summaries may be incomplete for older runs, so multiple recent runs may need comparison.
- Avoid over-inferring from `post_video` behavior; the two workflows share X posting surface but not necessarily identical code paths.

## Implementation steps

- [ ] 0. Move `docs/exec-plans/active/post-buz-live-verification_20260328_1903.md` to `docs/exec-plans/completed/` as superseded by this plan.
- [ ] 1. Review recent successful `post_buz.yml` runs and identify representative candidates to inspect.
- [ ] 2. Download artifacts / read summaries and logs for those runs to determine whether tweet IDs / URLs were produced.
- [ ] 3. Inspect the workflow and helper scripts only as needed to interpret ambiguous outcomes.
- [ ] 4. Summarize whether there is evidence of real posting, silent non-posting success, or X automation-detection impact.
- [ ] 5. If evidence remains inconclusive, stop with a targeted follow-up verification recommendation.
