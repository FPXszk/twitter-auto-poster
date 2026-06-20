# Windows native initial migration plan

## Goal

Make the repository usable from `C:\00_mycode\twitter-auto-poster` on Windows native without live posting or destructive Twitter/X operations.

## Scope

Files to create:

- `scripts/dev/devinit.ps1`
- `python/tool_paths.py`

Files to modify:

- `.codex/config.toml`
- `justfile`
- `python/auto_follow.py`
- `python/bulk_delete.py`
- `python/twitter_account_diagnostic.py`
- `tests/test_auto_follow.py`
- `tests/test_bulk_delete.py`
- `README.md`

Files to move after verification:

- `docs/exec-plans/active/windows_native_initial_migration_20260620_1507.md`
- `docs/exec-plans/completed/windows_native_initial_migration_20260620_1507.md`

Out of scope:

- GitHub Actions full rewrite from bash to PowerShell.
- Live Twitter/X posting, deletion, likes, follows, replies, quotes, or retweets.
- Pushing to GitHub.

## Steps

- [x] Add a small Python helper for platform-aware CLI defaults.
- [x] Update Python entrypoints that currently default to `python/.venv/bin/twitter`.
- [x] Add a Windows native development initializer that does not depend on bash or tmux.
- [x] Update `justfile` to call the PowerShell initializer and avoid tmux-only commands.
- [x] Update `.codex/config.toml` to point at this Windows repo instead of stale WSL paths.
- [x] Document Windows native setup and forbidden live commands in `README.md`.
- [x] Run focused unit tests for changed Python defaults.
- [x] Run non-destructive dry-run style checks only.
- [x] Move this plan to `docs/exec-plans/completed/`.

## Validation

- `python -m unittest tests.test_auto_follow tests.test_bulk_delete`
- `python -m py_compile python/tool_paths.py python/auto_follow.py python/bulk_delete.py python/twitter_account_diagnostic.py`
- `git status --short`

## Risks

- `twitter` CLI is not currently installed on PATH, so live authentication checks cannot pass until the tool is installed.
- Existing GitHub Actions still assume a `windows-wsl` runner and bash shell; those should be migrated in a separate, focused change.
