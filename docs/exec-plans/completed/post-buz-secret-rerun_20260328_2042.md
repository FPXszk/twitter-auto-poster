# post_buz secret rerun verification plan

## Overview

Verify whether updating the repository secret `COPILOT_GITHUB_TOKEN` fixes the current `post_buz.yml` failure mode.

This task is operational. The scope is:

- trigger a fresh `post_buz.yml` live run with `dry_run=false`
- confirm whether the new token passes the Copilot auth preflight
- determine whether the workflow completes successfully
- if it still fails, identify the exact failure point and propose realistic fallback options

## Success criteria

- The new run executes inside the active posting window (`should_run == true`)
- The new run reaches and passes `Run runtime diagnostics`
- The run reaches `Fetch candidates and process mode` and does not fail there due to Copilot auth
- The run either posts successfully or at least reaches candidate processing without Copilot auth failure
- If it fails, the final report must identify whether the remaining issue is:
  - Copilot authentication
  - candidate/summary generation
  - X posting/auth
  - other runtime/environment issue

## Files / resources involved

- `.github/workflows/post_buz.yml`
- recent `post_buz` Actions runs
- logs / run summary / artifacts for the new run
- `docs/exec-plans/active/post-buz-secret-rerun_20260328_2042.md`

## Implementation steps

- [ ] 1. Trigger `post_buz.yml` with `dry_run=false`
- [ ] 2. Confirm the new run uses current `main`
- [ ] 3. Monitor until completion
- [ ] 4. Confirm the run actually entered the posting window and did not silently skip verification
- [ ] 5. Inspect logs, run summary, and artifacts as needed
- [ ] 6. Report whether the secret update fixed the workflow
- [ ] 7. If not fixed, list the most practical alternatives

## Notes / risks

- A passing Copilot auth preflight does not guarantee end-to-end posting success; later steps may still fail for unrelated reasons
- A failed run is still useful if it proves the failure moved past the previous auth gate
