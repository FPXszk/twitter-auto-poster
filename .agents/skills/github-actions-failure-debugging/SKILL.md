---
name: github-actions-failure-debugging
description: Systematic workflow for diagnosing and fixing GitHub Actions failures. Prefer high-signal summaries when available, then structured logs, then raw logs, local reproduction, and verification.
---

# github-actions-failure-debugging — CI Failure Diagnosis Workflow

A structured playbook for diagnosing GitHub Actions workflow failures efficiently. The key principle is: **use the highest-signal tools first**, then fall back to lower-level inspection only as needed.

## When to Use

- A GitHub Actions workflow run has failed
- CI checks on a pull request are red
- A scheduled workflow has stopped working
- You need to understand why a previously green workflow is now failing

## Diagnosis Priority Order

Always follow this order — each level provides progressively more detail:

```text
Level 1: High-signal summaries (GitHub MCP if available)
Level 2: Structured log inspection
Level 3: Raw log analysis
Level 4: Local reproduction
Level 5: Fix and verification
```

## Level 1: High-Signal Summaries (Start Here)

If GitHub MCP summary tools are available, use them to get a structured overview before touching raw logs:

```text
1. summarize_run_log_failures(owner, repo, run_id)
   → Get an AI-summarized view of all failures in the run

2. summarize_job_log_failures(owner, repo, run_id, job_id)
   → Drill into a specific failed job

3. list_workflow_jobs(run_id) with filter: "latest"
   → See which jobs failed vs passed

4. get_workflow_run(run_id)
   → Check trigger event, branch, commit SHA, timing
```

If GitHub MCP tools are not available, use the highest-signal alternative your host provides first:

```text
- GitHub UI run summary
- gh run view / gh run watch / gh run download
- provider-specific workflow summary tools
```

**This level alone resolves most failures.** Common patterns:
- Dependency install timeout → retry or pin versions
- Test assertion failure → summary shows the failing test and assertion
- Secret/permission error → summary shows the access denial
- Syntax error in workflow YAML → summary shows the parse error

## Level 2: Structured Log Inspection

If the summary is insufficient, inspect logs with structure:

```text
1. get_job_logs(owner, repo, job_id, return_content: true, tail_lines: 200)
   → Get the tail of a specific job's logs

2. list_workflow_run_artifacts(run_id)
   → Check if the run produced artifacts (test reports, coverage, etc.)

3. get_workflow_run_logs_url(run_id)
   → Get the full log archive URL if needed
```

**Focus on:**
- Exit codes and error messages
- The step that failed (step name + line range)
- Timing anomalies (steps that took much longer than usual)
- Environment differences (runner OS, tool versions)

## Level 3: Raw Log Analysis

Only if structured tools do not reveal the cause:

```text
1. Download full logs via the logs URL
2. Search for error patterns:
   - "error", "Error", "ERROR"
   - "fatal", "FATAL"
   - "exit code", "Process completed with exit code"
   - "permission denied", "403", "401"
   - "timeout", "timed out"
3. Compare with a recent successful run's logs (same job)
```

## Level 4: Local Reproduction

When the failure cannot be understood from logs alone:

```text
1. Check out the exact commit: git checkout <sha>
2. Reproduce the failing step locally:
   - Run the same commands from the workflow YAML
   - Match environment variables where possible
   - Note: some failures are environment-specific (runner OS, network, secrets)
3. If the failure involves secrets or permissions:
   - Verify secret names match between workflow YAML and repo settings
   - Check if tokens have expired
   - Check if required permissions are set in the workflow YAML
```

**For this repository specifically:**
- For `ci.yml` failures, mirror `.github/workflows/ci.yml` as closely as possible:
  - Unit tests: `python3 -m unittest discover -s tests`
  - Shell validation: syntax-check every `*.sh` under `scripts/`
  - Python validation: compile every `*.py` under `python/` and `scripts/lib/`, excluding hidden paths and `.venv`
  - YAML validation: parse every `config/*.yaml` and `.github/workflows/*.yml`
- For operational workflows such as `post_buz.yml`, `auto_follow.yml`, `auto_like.yml`, `morning_post.yml`, `evening_post.yml`, and `twitter_diagnostic.yml`, reproduce the commands and prerequisites from the failing workflow itself rather than from `ci.yml`
- Operational workflow failures often depend on secrets, schedule windows, restored artifacts, caches, and external service state; check those before assuming the code path alone is broken

## Level 5: Fix and Verification

Once the root cause is identified:

```text
1. Make the minimal fix
2. Validate locally:
   - Run the failing command/test locally
   - Run the full local test suite
   - Syntax-check any modified workflow YAML
3. Push and monitor:
   - Push the fix
   - Watch the workflow run via: list_workflow_runs(workflow_id, branch: "<branch>")
   - Confirm the previously failing job now passes
4. If the fix doesn't work:
   - Go back to Level 1 with the new run_id
   - Compare the new failure with the old one
```

## Common Failure Patterns

| Pattern | Typical Cause | Quick Fix |
|---|---|---|
| `exit code 1` in test step | Test assertion failure | Read test output, fix code or test |
| `exit code 127` | Command not found | Add install step or fix PATH |
| `Resource not accessible by integration` | Missing permissions | Add `permissions:` block to workflow |
| `Bad credentials` / `401` | Expired or wrong token | Rotate secret, check token scope |
| `No space left on device` | Runner disk full | Clean workspace, reduce artifacts |
| `Rate limit exceeded` / `429` | API throttling | Add retry logic or reduce frequency |
| `Timeout` / cancelled after 6h | Hung process or infinite loop | Add `timeout-minutes:` to job/step |
| YAML parse error | Workflow syntax issue | Validate YAML locally |

## Workflow-Specific Notes for This Repository

This repository uses several scheduled workflows (see README for full list). Key debugging notes:

- **`post_buz.yml`**: Depends on `TWITTER_AUTH_TOKEN`, `TWITTER_CT0`, and `COPILOT_GITHUB_TOKEN` secrets. Failure in the post step often means expired Twitter cookies.
- **`auto_follow.yml` / `auto_like.yml`**: Rate-limit sensitive. Failures may be transient — check if retrying resolves it.
- **`ci.yml`**: Usually points to validation or code issues once dependency installation succeeds, but failures before validation steps can still come from runner, network, or package-index problems.
- **State/cache**: Many runtime outputs land under `tmp/`, but persisted state is not limited to `tmp/`. Check workflow-specific paths such as `config/follow_state.json` and any restored artifacts like `stock-cache` when investigating state-dependent failures.
