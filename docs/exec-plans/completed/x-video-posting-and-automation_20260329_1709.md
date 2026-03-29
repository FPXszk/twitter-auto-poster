# x video posting and automation plan

## Overview

Apply the most relevant ecosystem ideas to this repository by adding a **repository-native X video posting path**, without importing AGPL code, without adopting Selenium browser automation, and without disrupting the current `twitter-cli` text/image posting flow.

Current confirmed findings:

- The current repository already supports text and image-based X posting through `twitter-cli`
- `scripts/lib/post_media.py` and related tests are image-oriented only; there is no current video asset path
- `scripts/lib/post_publish.sh` posts via `twitter post ... --image ...` and assumes image-only media attachments
- `twitter-cli` help and the local `twitter-cli` skill documentation expose image attachment support but no video attachment option
- `MoneyPrinterV2` does include X posting and YouTube Shorts automation, but its X posting path is Selenium + Firefox-profile based and therefore is not a good fit for this repository
- `twikit` is a plausible video-capable X backend:
  - it supports `upload_media(...)` + `create_tweet(..., media_ids=...)`
  - it supports setting/loading cookies directly
  - it is MIT-licensed
- The user explicitly wants **X video posting**, not YouTube Shorts, for this implementation step

## Goal

Add a safe first slice of X video posting support that fits the current repository architecture and can be operated from both local CLI usage and GitHub Actions.

## Non-goals

- No YouTube Shorts automation in this step
- No Selenium/browser-driven posting
- No AGPL code reuse from `MoneyPrinterV2`
- No automatic video generation pipeline yet
- No replacement of the existing `twitter-cli` text/image publishing path

## Recommended implementation direction

### 1. Add a separate video-capable publishing backend

- Keep `twitter-cli` as the default backend for existing text/image posts
- Add a new Python helper using `twikit` specifically for posting a tweet with an attached local video file
- Reuse existing `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` secrets directly by mapping them to the `auth_token` and `ct0` cookies that `twikit` can load; avoid adding an unnecessary conversion layer beyond constructing the cookie dict/file shape
- Pin `twikit` to a specific version during implementation so the new path is protected from upstream scraping-related breakage, consistent with existing pinned runtime dependencies
- Keep the backend split explicit rather than trying to force video through the current image-only path

### 2. Ship a narrow first-use surface

Implement only a small operator-facing surface:

- **Local/manual command** for posting one X video with caption text
- **Manual GitHub Actions workflow** (`workflow_dispatch`) for posting one X video from a provided video URL or prepared file input path

This keeps the first version useful without coupling it to the current auto-summary candidate-selection flow.

### 3. Borrow the right ideas from the researched ecosystem

From the research, the most relevant ideas to apply are:

- **Backend separation by capability** rather than forcing every media type through one tool
- **Media-pipeline boundaries**: fetch/prepare asset → validate → publish → record result/state
- **MIT-licensed X posting backend** (`twikit`) instead of Selenium automation

## Files likely involved

- `scripts/lib/post_video.py`
  - new: `twikit`-based video upload + tweet posting logic
- `python/post_video.py` and/or `scripts/post_video.sh`
  - new: local/manual entry point for posting one video tweet
- `scripts/lib/post_media.py`
  - do not modify in this first slice; it remains the current image-oriented path
- `scripts/lib/post_publish.sh`
  - keep the existing text/image path intact unless a small shared result helper extraction is clearly useful
- `.github/workflows/`
  - new `workflow_dispatch` workflow for X video posting
- `.github/workflows/ci.yml`
  - likely update validation dependency installation if the new unit tests import `twikit`
- `README.md`
  - document the new local/manual usage if added
- `tests/`
  - new `tests/test_post_video.py` plus any supporting unit tests for cookie loading, asset validation, and publish result handling
- `docs/exec-plans/active/x-video-posting-and-automation_20260329_1709.md`
  - this execution plan

## Proposed first-slice behavior

### Local path

- Add a command that accepts:
  - caption text
  - local video file path
  - required dry-run / validation mode, with dry-run as the safe default during first-run/manual usage
- Validate:
  - file exists
  - primary supported format is MP4
  - extension/type is supported
  - file size constraints are enforced or surfaced clearly
  - duration constraints are enforced or surfaced clearly

### GitHub Actions path

- Add a dedicated `workflow_dispatch` workflow for X video posting
- First version should prefer a simple operator input model, such as:
  - caption text
  - downloadable video URL
  - dry_run boolean
- Workflow responsibilities:
  - install pinned `twikit`
  - download/validate the video asset
  - post to X
  - emit a JSON result artifact or `tmp/` result file consistent with current repo patterns

## Design notes

- Prefer a **new dedicated workflow** over extending `post_buz.yml` immediately, because video posting is a different operational mode than text-summary reposting
- Prefer **new helper modules** over expanding the current shell-heavy publish path too aggressively on the first iteration
- Keep state/result reporting aligned with current repository conventions so future integration into larger flows remains possible
- Align dependency installation with the repository's current workflow pattern, where runtime/test dependencies are installed directly in workflow YAML

## Test and validation strategy

- **RED**
  - add failing unit tests for:
    - cookie conversion / loading shape
    - video asset validation
    - result payload formatting
    - workflow-related helper behavior where practical
- **GREEN**
  - implement the minimal helper + workflow needed to satisfy the tests
- **REFACTOR**
  - simplify helper boundaries and avoid leaking video-specific logic into the current image-only path unless clearly reusable
- validate with existing repository commands plus any directly relevant new tests:
  - `python3 -m unittest discover -s tests`
  - `python3 -m py_compile python/*.py scripts/lib/*.py`
  - `bash -n scripts/*.sh scripts/lib/*.sh scripts/dev/*.sh`
  - YAML parse for modified workflows/configs
  - `git diff --check`

## Implementation steps

- [ ] 1. Add failing tests for X video helper behavior and any new asset/result utilities
- [ ] 2. Pin `twikit`, update any required workflow validation dependencies, and implement a `twikit`-based X video publish helper with cookie loading
- [ ] 3. Add a local/manual command surface for posting a video tweet
- [ ] 4. Add a dedicated manual GitHub Actions workflow for X video posting
- [ ] 5. Update README and any directly related docs
- [ ] 6. Run repository validation and review the changes

## Risks / watch-outs

- `twikit` is scraping-based and therefore carries X ToS and breakage risk
- Cookie mapping must be handled carefully; wrong assumptions could break posting or cause auth failures
- Video upload limits and processing time may differ from image posting and need explicit error surfacing
- Video upload is slower and more failure-prone than image upload, so timeout/error reporting needs to be explicit from the beginning
