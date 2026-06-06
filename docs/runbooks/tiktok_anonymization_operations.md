# TikTok Anonymization Operations Runbook

## Purpose

This runbook covers the remaining operational phases for the TikTok anonymization pipeline:

- GitHub Actions dispatch on the Windows self-hosted runner
- iCloud Drive delivery
- duplicate prevention and retry behavior
- runner and iCloud environment checks
- iPhone-side manual publishing

## Required configuration

- GitHub repository variable:
  - `TIKTOK_EXPORT_DIR`
    - Windows example: `C:\Users\szk\iCloudDrive\TikTokReady`
- Runner labels:
  - `self-hosted`
  - `windows-wsl`
  - `tiktok-video`
- WSL checkout path:
  - `/home/fpxszk/code/twitter-auto-poster`

## Phase 8: GitHub Actions execution

Workflow file:

- `.github/workflows/tiktok_anonymization.yml`

Dispatch inputs:

- `tiktok_url`
- `force`
- `stamp_type`
- `stamp_scale`

Expected result:

- `tmp/tiktok-pipeline/latest-result.json` is written in the checked-out repository.
- GitHub Actions Summary shows result, video ID, final phase, face count, track count, validation result, export destination, filename, and processing duration.
- Artifacts under `tmp/tiktok-pipeline/` are uploaded for diagnostics.

## Phase 9: State, deduplication, and retry behavior

State files:

- `tmp/tiktok-pipeline/state/<video_id>.json`
- `tmp/tiktok-pipeline/state/<video_id>.lock`

Behavior:

- Non-forced rerun after `EXPORTED` returns the existing export result and does not overwrite files.
- `force=true` creates a new processing attempt in state and a new export directory suffix when needed.
- A lock file prevents concurrent processing of the same video ID.
- Export retries transient filesystem and sync-like failures up to the configured retry count.

## Phase 10: Runner environment checks

Before routine use, verify these items on the Windows host:

1. iCloud for Windows starts automatically after sign-in.
2. `C:\Users\szk\iCloudDrive\TikTokReady` exists and remains synced.
3. WSL starts successfully and can access the repository checkout.
4. The GitHub Actions runner service or runner process returns online after restart.
5. `python/.venv`, `ffmpeg`, and `yt-dlp` are available inside WSL.
6. Disk space is sufficient for source, intermediate, and exported video artifacts.

Recommended manual health check commands in WSL:

```bash
cd /home/fpxszk/code/twitter-auto-poster
python/.venv/bin/python --version
python/.venv/bin/python -m unittest tests.test_tiktok_anonymization_pipeline tests.test_tiktok_export tests.test_tiktok_processing_state tests.test_tiktok_actions_summary
test -d /mnt/c/Users/szk/iCloudDrive/TikTokReady || mkdir -p /mnt/c/Users/szk/iCloudDrive/TikTokReady
```

Restart recovery checklist:

1. Sign in to Windows.
2. Confirm iCloud Drive finishes mounting.
3. Start WSL if it is not already running.
4. Confirm the self-hosted runner is online in GitHub.
5. Trigger the workflow manually with a known-safe sample URL.

## Phase 11: iPhone manual publishing

1. Open the iPhone Files app.
2. Open `iCloud Drive`.
3. Open `TikTokReady`.
4. Open the newest exported directory.
5. Review `ready_to_post.mp4` completely.
6. Open TikTok manually.
7. Select the reviewed video.
8. Enter caption and hashtags manually.
9. Verify account, visibility, comments, and sound settings.
10. Publish manually.

Mandatory human checks:

- Every visible face stays covered through the whole clip.
- Audio and video remain synchronized.
- The correct TikTok account is active.
- The intended visibility setting is selected.
