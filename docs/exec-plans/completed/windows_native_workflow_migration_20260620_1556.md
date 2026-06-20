# Windows native workflow migration plan

## Goal

Move the non-posting GitHub Actions workflows from the old `windows-wsl`/bash runtime shape to Windows native PowerShell while keeping live Twitter/X writes out of scope.

## Scope

Files to create:

- `scripts/dev/validate_yaml.py`

Files to modify:

- `.github/workflows/ci.yml`
- `.github/workflows/update_tickers.yml`
- `.github/workflows/update_tickers_jp.yml`

Out of scope:

- Posting workflows such as `post_buz.yml`, `post_pic.yml`, `morning_post.yml`, and `evening_post.yml`.
- Twitter/X live post, delete, reply, quote, like, retweet, follow, or unfollow operations.
- Pushing to GitHub.
- Removing all historical WSL/Linux references from docs and completed plans.

## Steps

- [x] Add a reusable YAML validation script.
- [x] Convert CI to `self-hosted` + `Windows` labels and PowerShell commands.
- [x] Convert stock cache update workflow to Windows venv paths.
- [x] Convert JP ticker update workflow to Windows venv paths.
- [x] Run local Windows native validation commands.
- [x] Move the plan to completed before committing.

## Validation

- `python\.venv\Scripts\python.exe scripts/dev/validate_yaml.py`
- `python\.venv\Scripts\python.exe -m unittest discover -s tests`
- `python\.venv\Scripts\python.exe -m py_compile <repo python files>`
- `bash -n <repo shell files>` when Git Bash is available

## Risks

- The self-hosted GitHub runner must have the standard `Windows` label.
- Bash scripts still exist and require Git Bash for syntax validation until they are migrated or wrapped.
- Ticker update workflows may need network access when they actually run on a business day.
