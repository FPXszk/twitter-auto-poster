# post_buz hidden error investigation and mitigation plan

## Overview

The latest scheduled `post_buz.yml` run (`run_id: 23681440510`) completed with `success`, but the job log still contains operational errors and warnings that indicate the posting path is not healthy.

The primary hidden error is that Copilot summary generation failed for buz candidates with:

- `copilot CLI failed: Error: Classic Personal Access Tokens (ghp_) are not supported by Copilot.`

Because `scripts/fetch_and_post.sh` currently treats `selected_count == 0` as a normal `no_candidate` outcome and exits with `0`, the workflow can report success even when every candidate failed during summary generation because of an authentication/runtime problem.

Secondary warning noise is also present:

- `Node.js 20 is deprecated ... being forced to run on Node.js 24`

## Confirmed findings

- Workflow file: `.github/workflows/post_buz.yml`
- Latest success run inspected: `23681440510`
- Hidden runtime warnings in the successful run:
  - Copilot summary generation failed for multiple buz candidates because the secret behaves like a classic `ghp_` PAT
  - `no eligible candidates found for category 'buz'` was emitted after those summary failures
  - GitHub-hosted actions emitted Node 20 deprecation warnings under forced Node 24 compatibility mode
- Root masking point:
  - `scripts/fetch_and_post.sh` logs summary-generation warnings, but later converts the situation into `result_mode=no_candidate` and `exit 0`
  - The fix must account for dual ownership of `result_mode`: the Python candidate-building block initializes it, and the later bash branch can overwrite it to `no_candidate`, `post_success`, or `post_failed`

## Files to change

- `scripts/fetch_and_post.sh`
  - Detect the hidden-failure heuristic in the Python payload-building block while all arrays are still in scope:
    - `len(selected_candidates) > 0`
    - `len(post_candidates) == 0`
    - at least one failed `summary_attempts` entry exists
  - When that heuristic matches, write a distinct result mode such as `summary_exhausted`
  - Distinguish a genuine “no candidate matched filters” result from “candidate generation degraded because summaries failed”
  - Make the later bash branch read `result_mode` before defaulting to `no_candidate`, so the new failure mode is not overwritten
  - Return a non-zero exit when all selected buz candidates fail due to summary/provider/runtime issues
  - Preserve the current success path for true no-candidate cases
- `scripts/lib/workflow_summary.py`
  - Surface the new degraded/failure mode clearly in the run summary so the first error is visible
- `.github/workflows/post_buz.yml`
  - Extend the existing runtime diagnostics step so unsupported Copilot auth fails fast with a direct message
  - Only apply the Copilot auth preflight when the configured `summary_provider` is `copilot_cli`
- `README.md`
  - Clarify that `COPILOT_GITHUB_TOKEN` must not be a classic `ghp_` PAT for Actions-based Copilot usage
- `docs/RUNBOOK.md`
  - Add the exact recovery guidance for the hidden Copilot auth failure
- `tests/test_workflow_summary.py`
  - Add RED coverage for the new degraded summary/result-mode rendering
- `tests/test_copilot_summary.py`
  - Extend tests only if we introduce token/auth classification helpers

## Scope and behavior

- Recommended behavior:
  - Fail the workflow when candidate generation is blocked by Copilot auth/runtime problems
  - Keep the workflow successful when there truly are no eligible tweets after filtering/scoring
  - Keep the summary and artifacts diagnostic enough to show the first actionable error quickly
- Keep posting, scoring, and filtering rules unchanged unless they must change to support the fix

## Implementation steps

- [ ] 1. Add a RED test that covers a degraded run summary/result mode for summary-generation failure, separate from a true `no_candidate` result
- [ ] 2. Add coverage for the exit-path decision, either with a small shell-level regression harness or with an explicit validation fixture that proves `summary_exhausted` no longer exits as `0`
- [ ] 3. Update `scripts/fetch_and_post.sh` so the Python payload-building block emits a distinct failure result when `selected_candidates > 0`, `post_candidates == 0`, and summary attempts failed, then make the bash branch honor that result and exit non-zero
- [ ] 4. Update `scripts/lib/workflow_summary.py` so the new failure/degraded result is obvious in the GitHub Actions summary
- [ ] 5. Extend the existing diagnostics step in `.github/workflows/post_buz.yml` so unsupported `ghp_`-style auth fails early only for `copilot_cli` accounts
- [ ] 6. Update `README.md` and `docs/RUNBOOK.md` with the correct `COPILOT_GITHUB_TOKEN` expectations and recovery steps
- [ ] 7. Leave the current Node 20 deprecation warning out of scope for this fix unless a safe repo-local change is found during implementation; otherwise document it as runner-side follow-up noise
- [ ] 8. Run baseline and post-change validation with the repository’s existing checks

## Validation plan

- Baseline before edits:
  - `python3 -m unittest discover -s tests`
  - `python3 -m py_compile scripts/lib/copilot_summary.py scripts/lib/workflow_summary.py`
  - `bash -n scripts/fetch_and_post.sh`
- Focused validation after edits:
  - `python3 -m unittest tests.test_copilot_summary tests.test_workflow_summary`
  - `python3 -m unittest discover -s tests`
  - `python3 -m py_compile scripts/lib/copilot_summary.py scripts/lib/workflow_summary.py`
  - `bash -n scripts/fetch_and_post.sh scripts/lib/common.sh scripts/lib/post_publish.sh`
  - YAML parse check for `.github/workflows/post_buz.yml`
  - `git diff --check`

## Notes / risks

- The workflow currently depends on a repo secret value that cannot be fully validated locally, so the code change should optimize for clear failure messages and testable branching rather than hidden retries
- The Node 20 warning is currently runner-side noise under `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24`; it is lower priority than exposing the hidden Copilot failure correctly
