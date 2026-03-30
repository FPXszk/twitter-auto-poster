# post_buz visibility fix plan

## Overview

Recent successful `post_buz.yml` runs did execute real posts, but that fact is not visible from the GitHub Actions summary.

Confirmed evidence from existing artifacts and logs:

- run `23724963469` posted tweet ID `2038439962035556640`
- run `23721687704` posted tweet ID `2038400046257840374`
- current summary code only renders the source tweet ID and the internal `post_result_file` path, not the posted tweet ID / URL

The user-facing problem is therefore observability, not an obvious dry-run misconfiguration or total post failure.

## Goal

1. Make successful `post_buz.yml` runs show the actual posted tweet ID and URL in the GitHub Actions summary.
2. Preserve existing failure/no-candidate/skip behavior.
3. Add regression tests so future summary changes do not hide the posted tweet again.

## Out of scope

- No source selection algorithm changes
- No auth/cookie rotation work unless new evidence appears during implementation
- No workflow schedule changes
- No forced live rerun before the summary/reporting fix is in place

## Files to create / modify

- `docs/exec-plans/active/post-buz-visibility-fix_20260330_0520.md` (this plan)
- `scripts/lib/workflow_summary.py`
- `tests/test_workflow_summary.py`

## No-overlap check

Checked current active plans in `docs/exec-plans/active/`:

- `post-buz-posting-investigation_20260330_0412.md` overlaps in subject but is investigation-only; this plan is the implementation follow-up
- `post-buz-live-verification_20260328_1903.md` is historical overlap and should remain reference-only
- `post-video-live-verification_20260330_0331.md` is unrelated
- research-only plans are unrelated

## Proposed implementation

Implement the smallest safe fix in `scripts/lib/workflow_summary.py`:

1. Add a helper in `scripts/lib/workflow_summary.py` that reads the JSON payload referenced by `payload["post_result_file"]` when present.
2. Reuse `post_feedback.extract_posted_tweet_id` for tweet ID extraction instead of duplicating payload-shape logic.
3. Prefer the existing `data.url` from the post result payload for the posted tweet URL.
4. Call that helper from `render_run_summary`, accepting the small amount of file I/O there to keep the fix limited to the summary module and its tests.
5. Render the posted tweet ID / URL in the Actions summary when `result_mode == "posted"` or when a valid post result payload exists.
6. Keep the existing `post_result_file` line for low-level debugging.

This avoids changing posting logic and focuses on surfacing already-produced data.

## Test strategy

### RED

- Add/extend `tests/test_workflow_summary.py` with a failing case where a successful payload has `post_result_file` pointing to a post result JSON, and the rendered summary must include the posted tweet ID and URL.
- Add a failing case covering a missing/invalid post result file so the summary degrades safely without crashing.

### GREEN

- Implement the helper and summary rendering in `scripts/lib/workflow_summary.py` with the minimum change needed for the new tests to pass.

### REFACTOR

- Keep the helper isolated and small.
- Reuse existing payload shape conventions instead of inventing a new result schema.

## Validation

- `python -m unittest tests.test_workflow_summary`
- `python -m unittest discover -s tests`
- `python -m coverage run -m unittest discover -s tests && python -m coverage report --fail-under=80`
- `python -m py_compile scripts/lib/workflow_summary.py`

## Risks / watch-outs

- `post_result_file` is an internal runner path; summary rendering must read it at workflow runtime, not assume the path will be valid after artifact download.
- `render_run_summary` currently behaves like a formatting function; adding post-result lookup there is an intentional trade-off to avoid touching workflow YAML for this small fix.
- Some successful-looking runs are legitimate posting-window skips, so the new summary must not mislabel skipped runs as posted.
- The post result payload may vary between single-post and thread-style responses; extraction should handle the current `twitter-cli` payload shape safely.

## Implementation steps

- [ ] 1. Add failing workflow summary tests for posted tweet ID / URL visibility.
- [ ] 2. Implement post result loading/extraction in `scripts/lib/workflow_summary.py`.
- [ ] 3. Make the summary show posted tweet ID / URL while preserving existing lines.
- [ ] 4. Run targeted and full validation commands.
- [ ] 5. Prepare implementation review notes before moving to REVIEW.
