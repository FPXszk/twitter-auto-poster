# post_buz live verification plan

## Overview

Verify whether the newly fixed `post_buz.yml` workflow succeeds in a real live run after commit `7baa284`.

This task is operational rather than a code-change task. The goal is to dispatch the workflow in live mode, confirm that the new commit is the one being executed, and inspect the result for:

- workflow conclusion
- whether `summary_exhausted` or Copilot auth preflight now surfaces correctly
- whether an actual post path succeeds when a candidate is found
- whether the run summary/artifacts reflect the expected behavior

## Files / resources involved

- `.github/workflows/post_buz.yml`
  - workflow_dispatch input and runtime behavior reference
- GitHub Actions workflow runs for `post_buz.yml`
  - dispatch target and verification source
- `docs/exec-plans/active/post-buz-live-verification_20260328_1903.md`
  - this execution plan

## Scope

- Trigger `post_buz.yml` with `dry_run=false`
- Confirm the created run uses commit `7baa284` on `main`
- Wait for completion and inspect:
  - workflow conclusion
  - job/step statuses
  - logs for preflight/auth/summary behavior
  - run summary and artifacts if needed
- Report whether the live execution succeeded and why

## Acceptance criteria

- `Success` with an actual post path confirms the workflow still works on the happy path after the fix, but does **not** by itself prove the new hidden-error handling path was exercised
- `Failure` with a clear `summary_exhausted` outcome confirms the core fix is surfacing summary-generation exhaustion instead of silently succeeding as `no_candidate`
- `Failure` from the Copilot auth preflight confirms the new preflight guard is working, but is only partial verification of the overall fix
- A true `no_candidate` outcome remains a valid runtime result, but it is inconclusive for proving the new hidden-error path
- A run skipped because the posting window is closed is **not** a valid verification run

## Implementation steps

- [ ] 1. Confirm repository state and target workflow_dispatch parameters
- [ ] 2. Trigger `post_buz.yml` live run with `dry_run=false`
- [ ] 3. Monitor the triggered run until completion
- [ ] 4. Inspect logs, summary, and artifacts to verify expected behavior
- [ ] 5. Summarize the outcome and any residual issues

## Notes / risks

- A live run may legitimately fail because of external runtime conditions such as Copilot auth, X auth, or candidate availability
- The workflow only performs posting work between `08:00` and `24:00` JST; outside that window the run can still end in `success` while effectively doing no verification work
- The workflow uses concurrency group `post-buz` with `cancel-in-progress: false`, so a manual dispatch may queue behind another scheduled/manual run
- Success criteria for this task is accurate verification of the live run outcome, not forcing the workflow to succeed artificially
