# twikit ClientTransaction compatibility fix

## Overview

The live `post_video.yml` run 23711885202 failed with `"Couldn't get KEY_BYTE indices"` in twikit 2.3.3's `ClientTransaction.get_indices()`. Twitter changed the structure of `ondemand.s.js` around 2026-03-18, breaking the regex patterns that twikit uses to extract KEY_BYTE indices (confirmed by twikit issue #408).

This plan implements a repo-local compatibility shim that monkey-patches `ClientTransaction.get_indices()` with fallback regex patterns before `twikit.Client()` is instantiated.

## Parent plan

This is step 6 of `ci-and-video-post-verification_20260329_1350.md`.

## Goal

Make live video posting robust against Twitter's ondemand.s.js structure changes without modifying twikit source or adding new dependencies.

## Non-goals

- No broad refactor of posting logic
- No change to dry-run behavior
- No new package additions
- No modification of twikit package files in the venv

## Files to create

- `scripts/lib/twikit_compat.py` — Compatibility shim with fallback regex patterns and monkey-patch function
- `tests/test_twikit_compat.py` — Regression tests for the compat layer

## Files to modify

- `scripts/lib/post_video.py` — Call `patch_twikit_transaction()` in `_default_client_factory()`
- `docs/exec-plans/active/ci-and-video-post-verification_20260329_1350.md` — Update step 6 checkbox

## Out of scope

- Existing dry-run tests and behavior (must remain unchanged)
- Other posting workflows (text, image, reply, quote)
- CI workflow changes (already fixed locally)

## Root cause analysis

twikit 2.3.3 `ClientTransaction.get_indices()` uses two regex patterns:

1. `ON_DEMAND_FILE_REGEX`: Extracts the hash from `"ondemand.s":"HASH"` in the homepage HTML
2. `INDICES_REGEX`: `(\(\w{1}\[(\d{1,2})\],\s*16\))+` — Extracts indices from patterns like `(e[12], 16)` in the ondemand JS file

Twitter changed the JS structure so that indices now appear in `parseInt(e[12], 16)` format (and potentially other variants). The original regex fails to match, yielding an empty list, which triggers the exception.

## Fix approach

Create `scripts/lib/twikit_compat.py` that:

1. Saves a reference to the original `ClientTransaction.get_indices`
2. Replaces it with a wrapper that:
   - Tries the original implementation first
   - On "KEY_BYTE" failure, falls back to alternative regex patterns:
     - `parseInt(\w+\[(\d{1,3})\], 16)` — matches `parseInt(e[12], 16)`
     - `\(\w+\[(\d{1,3})\],\s*16\)` — broader version of original
   - Also tries alternative ondemand hash extraction patterns
   - Also tries alternative URL suffixes (with/without trailing `a`)
3. Is idempotent (safe to call multiple times)

Modify `scripts/lib/post_video.py` `_default_client_factory()` to call the patch before `Client()`.

## Test strategy

### RED

- `test_extract_indices_from_js_matches_parseint_format` — fails until `_extract_indices_from_js()` exists
- `test_extract_ondemand_hash_alternatives` — fails until `_extract_ondemand_hash()` exists
- `test_patch_replaces_get_indices` — fails until monkey-patching works
- `test_robust_get_indices_fallback_on_key_byte_error` — fails until fallback logic exists
- `test_robust_get_indices_passthrough_on_success` — ensures original path still works

### GREEN

- Implement `twikit_compat.py` with the above functions
- Apply the patch in `post_video.py`

### REFACTOR

- Clean up, ensure idempotency, verify no test regressions

## Validation commands

- `python3 -m unittest discover -s tests -p 'test_twikit_compat.py' -v`
- `python3 -m unittest discover -s tests -p 'test_post_video.py' -v`
- `python3 -m unittest discover -s tests -v`
- `python3 -m py_compile scripts/lib/twikit_compat.py`

## Risks

- The alternative regex patterns may not cover all future Twitter changes — but they cover the known 2026-03-18 change
- Full verification requires a real GitHub Actions live rerun after commit/push
- The monkey-patch approach is fragile if twikit's internal class structure changes, but this is acceptable given the pinned version (2.3.3)
