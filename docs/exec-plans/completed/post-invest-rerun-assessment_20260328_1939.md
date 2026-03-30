# post_invest rerun assessment plan

## Overview

Assess whether `post_invest.yml` can be manually re-run now, and identify the safest recovery path for Copilot authentication in GitHub Actions.

Current confirmed findings:

- Historical workflow `post_invest.yml` exists in Actions history, and GitHub marks that workflow entry as `deleted`
- Commit `fa81036` renamed `post_invest.yml` to `post_buz.yml` (`R088`)
- Current `main` no longer contains `.github/workflows/post_invest.yml`, but it does contain the renamed successor `.github/workflows/post_buz.yml`
- Therefore:
  - triggering a new `workflow_dispatch` for `post_invest.yml` from current `main` is not possible
  - re-running an existing historical run of `post_invest.yml` is still feasible
  - if the user wants the current successor workflow, the actionable workflow is `post_buz.yml`
- Copilot CLI documentation confirms:
  - supported token sources include `COPILOT_GITHUB_TOKEN`, `GH_TOKEN`, and `GITHUB_TOKEN`
  - supported token types are OAuth (`gho_`), fine-grained PAT (`github_pat_`), and GitHub App user-to-server (`ghu_`)
  - classic PAT (`ghp_`) is explicitly unsupported
- The docs for Actions automation recommend storing a fine-grained PAT with `Copilot Requests` permission as a repository secret rather than relying on the built-in Actions token

## Questions this plan answers

- Can `post_invest.yml` be manually re-run right now from the current repository state, and in what form?
- What is the most practical authentication strategy for Copilot CLI in Actions?
- Why did posting appear to work before but fail now?

## Files / resources involved

- Current workflow inventory under `.github/workflows/`
- Historical Actions workflow metadata for `post_invest.yml`
- Copilot CLI authentication docs
- `docs/exec-plans/active/post-invest-rerun-assessment_20260328_1939.md`

## Recommended direction

- Short-term, the most reliable operational fix is **not** to assume built-in Actions `${{ github.token }}` will work for Copilot CLI
- Preferred order:
  1. If you want to verify the current production path, use the renamed successor workflow `post_buz.yml`
  2. Use a supported token for Copilot CLI in Actions (`github_pat_` with `Copilot Requests`, or a supported GitHub App user-to-server token)
  3. If your plan/account cannot issue such a token, change the workflow implementation so automation no longer depends on Copilot CLI auth for posting-critical paths
  4. Only restore or re-run historical `post_invest.yml` if you specifically need the old invest-category behavior

## Implementation / investigation steps

- [ ] 1. Confirm and document that `post_invest.yml` was renamed to `post_buz.yml` and no longer exists on current `main`
- [ ] 2. Summarize rerun feasibility precisely: historical rerun is possible, fresh dispatch of `post_invest.yml` is not, and the current successor dispatch is `post_buz.yml`
- [ ] 3. Compare the Copilot CLI docs with the current repository auth approach
- [ ] 4. Recommend the safest next action: run `post_buz`, restore old `post_invest`, or change auth strategy
- [ ] 5. Ask the user which path to take next

## Notes / risks

- The environment variable name `GITHUB_TOKEN` is supported by Copilot CLI, but the default Actions `${{ github.token }}` value is a `ghs_` installation token and is not documented as a supported Copilot CLI token type
- A successful historical tweet does not prove the current Copilot auth is valid; X posting auth and Copilot summary auth are separate concerns
