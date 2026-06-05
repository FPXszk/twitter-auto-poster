# TikTok Video Anonymization Roadmap

## 1. Document Purpose

This document is the master implementation plan for the TikTok video acquisition, face anonymization, validation, and iCloud Drive export pipeline in `FPXszk/twitter-auto-poster`.

TikTok upload and publishing are intentionally excluded from automation. The final video is delivered to an iPhone through iCloud Drive, and a human publishes it using the TikTok application.

This roadmap supersedes the old design assumptions concerning automatic caption generation, TikTok OAuth, Content Posting API integration, and automatic publishing.

## 2. Confirmed Final Workflow

```text
GitHub Actions workflow_dispatch
↓
TikTok video URL input
↓
Self-hosted runner on the home PC
↓
Video download
↓
H.264 / AAC / yuv420p normalization
↓
Face detection
↓
Face tracking
↓
Transparent PNG stamp composition
↓
Output quality validation
↓
Copy to Windows iCloud Drive/TikTokReady
↓
iCloud synchronization
↓
Open from the iPhone Files application
↓
Human enters caption, hashtags, and visibility
↓
Human publishes from the TikTok application
```

## 3. Scope

### 3.1 Automated Scope

- Accept a TikTok video URL.
- Validate and normalize the input URL.
- Download the source video.
- Preserve the original downloaded file as `source.mp4`.
- Normalize the working video to H.264, AAC, yuv420p, and MP4.
- Detect human faces in every required frame.
- Associate detections across frames using stable track IDs.
- Smooth face coordinates and compensate for short detection gaps.
- Composite transparent PNG stamps over tracked faces.
- Validate video, audio, container, and face coverage.
- Export successful results to iCloud Drive.
- Record processing state and prevent duplicate work.
- Retry transient failures.
- Publish processing results to the GitHub Actions Summary.
- Store diagnostic artifacts for debugging.

### 3.2 Human Scope

- Review the completed video on the iPhone.
- Save the video locally when required.
- Open the TikTok application.
- Select the completed video.
- Write the caption.
- Add hashtags.
- Confirm the visibility and other posting settings.
- Press the publish button.

### 3.3 Explicitly Excluded

- TikTok Developer Portal approval.
- TikTok Content Posting API.
- OAuth callback handling.
- `video.publish` scope.
- Client Secret, Access Token, and Refresh Token management.
- Browser automation for TikTok publishing.
- Automatic caption generation.
- Automatic hashtag generation.
- Fully unattended public publishing.
- CAPTCHA or access-control bypass.
- Unauthorized redistribution of third-party content.

## 4. Repository and Runtime Context

```text
Repository: FPXszk/twitter-auto-poster
Local repository: ~/code/twitter-auto-poster
Platform: Windows 11 + WSL2 Ubuntu
Python virtual environment: ~/code/twitter-auto-poster/python/.venv
Final video: ready_to_post.mp4
Primary delivery destination: iCloud Drive/TikTokReady
GitHub Actions Artifact: backup and diagnostics only
Initial stamp scale candidate: 1.6
```

## 5. Current Status

| Phase | Name | Status | Review state |
|---|---|---|---|
| 0 | Environment and Baseline Assessment | Completed | Confirmed |
| 1 | TikTok Video Acquisition | Completed | Confirmed |
| 2 | Media Normalization | Completed | Confirmed |
| 3 | Face Detection | Completed | User reviewed and approved |
| 4 | Face Tracking | Completed | Implementation and live validation completed |
| 5 | Face Stamp Composition | Completed | User reviewed current sample video and approved |
| 6 | Final Media Quality Validation | In progress | Core technical and coverage checks exist inside overlay flow; standalone phase remains |
| 7 | iCloud Drive Export | Planned | Destination confirmed |
| 8 | GitHub Actions Integration | Planned | Not reviewed |
| 9 | State Management, Deduplication, and Retry | Planned | Not reviewed |
| 10 | Self-hosted Runner Operations | Planned | Not reviewed |
| 11 | iPhone Manual Publishing Runbook | Planned | Publishing method confirmed |

## 6. Global Engineering Rules

- Work on one phase at a time.
- Do not begin the next phase until the current phase meets its acceptance criteria.
- Preserve `source.mp4`; never overwrite the downloaded original.
- Use `normalized.mp4` as the input to all computer-vision processing.
- Keep video resolution, frame rate, duration, and audio timing unless a documented correction is required.
- Do not silently skip failed frames or damaged media.
- Save enough diagnostics to reproduce every failure.
- Do not place credentials, cookies, tokens, or personal paths in Git.
- Keep configurable paths and thresholds outside hard-coded business logic.
- Add automated tests for deterministic logic and manual review procedures for visual quality.
- Treat face coverage failure as a blocking failure; do not export an unsafe video.
- Prefer small, reviewable changes over broad refactoring.

---

# Phase 0 — Environment and Baseline Assessment

## Objective

Understand the existing repository, dependencies, processing flow, and test baseline before changing production code.

## Planned Work

- Inspect repository guidance files and current TikTok-related modules.
- Record Python, yt-dlp, ffmpeg, and ffprobe versions.
- Confirm WSL and Windows path interoperability.
- Run the existing test suite and preserve baseline results.
- Document the existing TikTok pipeline and generated files.
- Establish a temporary debug workspace under `tmp/tiktok-debug/`.

## Deliverables

- Environment inventory.
- Baseline test result.
- Existing-flow description.
- List of known constraints and risks.

## Acceptance Criteria

- Required commands are available.
- Existing tests pass or known pre-existing failures are documented.
- Current processing flow is understood before implementation begins.

## Status

Completed.

---

# Phase 1 — TikTok Video Acquisition

## Objective

Reliably accept a TikTok URL and download one source video without mixing the operation with publishing logic.

## Planned Work

- Validate supported TikTok URLs.
- Resolve redirect or shortened URLs when applicable.
- Retrieve metadata before downloading.
- Download the selected video with yt-dlp.
- Save the unmodified source as `source.mp4`.
- Save metadata, ffprobe output, logs, and a structured result file.
- Classify download failures and retain the failing command output.

## Primary Outputs

```text
source.mp4
metadata.json
ffprobe.json
source.info.json
result.json
download.log
```

## Acceptance Criteria

- A valid test URL produces `source.mp4`.
- Invalid URLs fail with a clear error.
- The original file remains unchanged.
- Metadata and diagnostic logs are sufficient to reproduce failures.

## Status

Completed.

---

# Phase 2 — Media Normalization

## Objective

Produce a stable, broadly compatible input video for all later processing.

## Planned Work

- Inspect the source with ffprobe.
- Avoid unnecessary re-encoding when the source already satisfies requirements.
- Otherwise convert to:
  - MP4 container
  - H.264/AVC video
  - AAC audio or valid no-audio output
  - yuv420p pixel format
  - `+faststart`
- Preserve source resolution, frame rate, aspect ratio, duration, and audio synchronization.
- Run ffprobe validation after normalization.
- Run a full ffmpeg decode test.

## Primary Output

```text
normalized.mp4
```

## Acceptance Criteria

- Video codec is H.264.
- Audio codec is AAC or the file is intentionally silent.
- Pixel format is yuv420p.
- The file decodes without errors.
- Windows playback succeeds.
- Source resolution and frame rate are preserved.

## Status

Completed.

---

# Phase 3 — Face Detection

## Objective

Detect faces in `normalized.mp4` and save frame-level face coordinates and confidence values in a reproducible format.

## Implemented Work

- Open `normalized.mp4` and inspect the required frames.
- Run the selected face detector.
- Convert detections into consistent pixel coordinates.
- Save frame number, timestamp, bounding box, and confidence.
- Represent frames with no detections explicitly.
- Produce visual or structured diagnostics suitable for human review.
- Test representative conditions including frontal faces, side faces, small faces, multiple people, and no-face video.

## Primary Output

```text
detections.json
```

## Required Data Model

Each detection should contain at least:

```json
{
  "frame_index": 0,
  "timestamp_ms": 0,
  "bbox": {
    "x": 0,
    "y": 0,
    "width": 0,
    "height": 0
  },
  "confidence": 0.0
}
```

Additional detector-specific information may be stored without breaking the stable fields above.

## Acceptance Criteria

- The detector processes the complete target video.
- Bounding boxes remain inside the frame.
- Multiple faces can be recorded in one frame.
- No-face frames are handled normally.
- Output is deterministic enough for tracking tests.
- Human visual review finds no blocking detection defect in the approved test set.

## Status

Completed. User review has been performed and approval has been given.

---

# Phase 4 — Face Tracking

## Objective

Associate frame-level detections belonging to the same person, create stable track IDs, smooth movement, and bridge short detection gaps.

## Planned Work

### 4.1 Input Validation

- Validate `detections.json` schema and video metadata.
- Reject mismatched frame counts, invalid coordinates, and unsupported versions.
- Preserve original detector output for comparison.

### 4.2 Detection Association

- Match detections between adjacent frames using a documented strategy.
- Initial matching candidates may use:
  - Intersection over Union.
  - Center-point distance.
  - Bounding-box size change.
  - Motion prediction.
  - Confidence score.
- Prevent one detection from being assigned to multiple tracks.
- Start a new track only when no valid existing match is available.

### 4.3 Track Lifecycle

- Assign a stable `track_id` to each face sequence.
- Maintain active, temporarily missing, completed, and discarded track states.
- Allow a configurable number of missing frames before ending a track.
- Avoid merging two different people during crossings or close contact.
- Avoid fragmenting one person into many short tracks.

### 4.4 Coordinate Smoothing

- Apply temporal smoothing to center position and box size.
- Use configurable smoothing parameters.
- Keep enough responsiveness for sudden head movement.
- Do not let the smoothed box lag far enough to expose the face.

### 4.5 Gap Interpolation

- Interpolate only short gaps bounded by valid detections from the same track.
- Limit interpolation by configurable maximum gap length.
- Mark interpolated observations explicitly.
- Do not invent long face trajectories after the subject leaves the frame.

### 4.6 Diagnostics

- Generate track statistics.
- Record track start frame, end frame, observed frames, interpolated frames, and confidence summary.
- Produce an optional debug video or frame overlay showing track IDs and boxes.
- Log unmatched detections, terminated tracks, and ambiguous associations.

## Primary Output

```text
tracked_detections.json
```

## Recommended Stable Fields

```json
{
  "frame_index": 0,
  "timestamp_ms": 0,
  "track_id": 1,
  "bbox": {
    "x": 0,
    "y": 0,
    "width": 0,
    "height": 0
  },
  "confidence": 0.0,
  "source": "detected",
  "interpolated": false
}
```

## Required Tests

- One stationary face.
- One moving face.
- Fast head movement.
- Temporary occlusion.
- Face leaving and re-entering the frame.
- Two faces moving independently.
- Two faces crossing.
- Small and low-confidence detections.
- No-face video.
- Detection gaps shorter and longer than the interpolation threshold.

## Acceptance Criteria

- A face keeps the same track ID during ordinary motion.
- Short detector gaps do not cause visible stamp disappearance.
- Different people are not routinely merged into one track.
- Coordinate smoothing reduces jitter without creating unsafe lag.
- All interpolated records are distinguishable from detector records.
- Debug visualization supports human review.
- Unit and integration tests pass.
- User review approves representative tracking output before Phase 5 begins.

## Status

Completed. Implementation and live validation have been completed on the representative sample video.

---

# Phase 5 — Face Stamp Composition

## Objective

Render transparent PNG stamps over all tracked face regions and produce the candidate final video.

## Planned Work

- Load `normalized.mp4` and `tracked_detections.json`.
- Load a selected transparent PNG stamp.
- Position each stamp using the tracked face center.
- Scale the stamp relative to face dimensions.
- Use `1.6` as the initial scale candidate, configurable through CLI and workflow input.
- Preserve the stamp aspect ratio and alpha channel.
- Clip overlays safely at frame boundaries.
- Support multiple simultaneous tracks.
- Preserve source audio without unintended re-timing.
- Encode the output as H.264/AAC/yuv420p MP4.
- Add `+faststart`.

## Primary Output

```text
ready_to_post.mp4
```

## Required Tests

- One face near the center.
- Face near every frame edge.
- Multiple faces.
- Fast motion.
- Face size changes.
- Temporary interpolation segments.
- No-face video.
- Transparent stamp with irregular alpha edges.

## Acceptance Criteria

- Every accepted track is covered by a stamp.
- The stamp remains large enough to hide the complete face.
- The stamp does not jitter excessively.
- Multiple faces are independently covered.
- Audio remains present and synchronized.
- Resolution, frame rate, and duration remain within documented tolerances.
- Human review approves the rendered output.

## Status

Completed. The current sample output has been rendered, validated, and approved for visual quality.

---

# Phase 6 — Final Media Quality Validation

## Objective

Block unsafe or damaged output before it is copied to iCloud Drive.

## Planned Work

### 6.1 Technical Validation

- Confirm the file exists and is non-empty.
- Inspect the output with ffprobe.
- Confirm MP4, H.264, AAC or intentional silence, and yuv420p.
- Confirm width, height, frame rate, and duration against normalized input.
- Run a complete ffmpeg decode test.
- Confirm audio stream duration and synchronization tolerance.

### 6.2 Face Coverage Validation

- Compare tracked face boxes with rendered stamp regions.
- Verify minimum coverage margin.
- Detect missing overlay frames.
- Detect stamps with invalid size or coordinates.
- Fail closed when required face coverage cannot be proven.

### 6.3 Human Review Package

- Produce a validation summary.
- Produce representative sampled frames or a low-cost debug preview when needed.
- Include warnings for borderline confidence, long interpolation, or unusual track behavior.

## Primary Outputs

```text
validation_result.json
validation.log
```

## Acceptance Criteria

- All technical checks pass.
- No decode errors are present.
- Face coverage checks pass for every required tracked frame.
- Output is not exported when any blocking check fails.
- Failure reason is clear and actionable.

---

# Phase 7 — iCloud Drive Export

## Objective

Copy only validated output to a Windows iCloud Drive synchronization folder that is accessible from the iPhone Files application.

## Confirmed Destination

```text
Windows example:
C:\Users\<WindowsUser>\iCloudDrive\TikTokReady

WSL example:
/mnt/c/Users/<WindowsUser>/iCloudDrive/TikTokReady
```

The actual path must be discovered on the target PC and provided through configuration, not hard-coded in source code.

## Planned Work

- Introduce an environment variable such as:

```bash
TIKTOK_EXPORT_DIR=/mnt/c/Users/<WindowsUser>/iCloudDrive/TikTokReady
```

- Validate that the destination exists and is writable.
- Create an isolated directory per video ID and processing date.
- Copy through a temporary filename and rename atomically when complete.
- Preserve checksums and file sizes.
- Update `result.json` only after a verified copy.
- Avoid overwriting an existing completed export unless `force=true`.
- Record the final Windows and WSL paths without exposing unrelated personal paths in logs.

## Export Layout

```text
TikTokReady/
└── YYYY-MM-DD_<video_id>/
    ├── ready_to_post.mp4
    ├── source_url.txt
    ├── result.json
    └── README.txt
```

## Acceptance Criteria

- Only validated videos are exported.
- The exported checksum matches the local completed file.
- The video becomes visible in the iPhone Files application after iCloud synchronization.
- Re-running without `force` does not unexpectedly overwrite an existing export.
- Export failures leave no apparently complete partial video.

---

# Phase 8 — GitHub Actions Integration

## Objective

Allow the pipeline to be started from GitHub on a PC or smartphone and executed on the home self-hosted runner.

## Planned Workflow Inputs

```yaml
workflow_dispatch:
  inputs:
    tiktok_url:
      description: "TikTok video URL"
      required: true
      type: string

    force:
      description: "Reprocess an existing video"
      required: true
      default: false
      type: boolean

    stamp_type:
      description: "Stamp asset identifier"
      required: true
      default: "default"
      type: string

    stamp_scale:
      description: "Face stamp scale"
      required: true
      default: "1.6"
      type: string
```

## Runner Labels

```yaml
runs-on:
  - self-hosted
  - windows-wsl
  - tiktok-video
```

## Planned Work

- Validate workflow inputs before execution.
- Run the existing pipeline through one supported CLI entry point.
- Set strict shell error handling.
- Capture logs and structured outputs for every phase.
- Always publish a GitHub Actions Summary.
- Upload diagnostic artifacts on failure.
- Optionally upload the final video artifact as backup, not as the primary delivery method.
- Prevent secrets and sensitive paths from appearing in logs.

## Actions Summary

The summary should include:

```text
Result
Video ID
Current/final phase
Detected face count
Track count
Validation result
Cloud export destination
Output filename
Processing duration
Failure category and reason, when applicable
```

## Acceptance Criteria

- The workflow can be started from GitHub mobile or desktop.
- The URL reaches the self-hosted runner correctly.
- Success and failure are visible without opening raw logs.
- Failure artifacts are available for diagnosis.
- The workflow does not perform TikTok upload or publishing.

---

# Phase 9 — State Management, Deduplication, and Retry

## Objective

Make execution resumable, prevent unintended duplicate processing, and safely retry transient failures.

## State Model

```text
CREATED
DOWNLOADED
NORMALIZED
FACE_DETECTED
FACE_TRACKED
STAMPED
VALIDATED
EXPORTED
FAILED
```

## Stored Information

- Original TikTok URL.
- Canonical URL.
- TikTok video ID.
- Source video SHA-256.
- Processing timestamps.
- Current and previous states.
- Failure phase, category, and message.
- Generated file paths.
- Configuration values affecting output.
- Detector, tracker, and stamp version identifiers.
- Export checksum and destination.

## Planned Work

- Use video ID as the primary external identity.
- Use SHA-256 to distinguish changed source content.
- Skip an already `EXPORTED` video unless `force=true`.
- Resume only when intermediate files pass integrity checks.
- Retry transient download, filesystem, and synchronization failures.
- Do not retry deterministic validation failures without changed input or configuration.
- Use bounded retry count and backoff.
- Preserve each failure attempt for diagnosis.
- Prevent concurrent jobs from processing the same video simultaneously.

## Acceptance Criteria

- Duplicate non-forced execution exits safely and clearly.
- `force=true` creates a documented new processing attempt.
- Interrupted processing can resume or restart without corrupting outputs.
- Retry behavior is bounded and phase-aware.
- Concurrent duplicate runs are prevented.

---

# Phase 10 — Self-hosted Runner Operations

## Objective

Keep the Windows, WSL, runner, and iCloud synchronization environment reliable enough for routine use.

## Planned Work

- Start required components after Windows sign-in or startup.
- Ensure WSL is available before the runner accepts video jobs.
- Start or restart the self-hosted runner automatically.
- Prevent unwanted sleep during active processing.
- Detect and report runner offline conditions.
- Confirm iCloud for Windows starts automatically.
- Monitor available disk space before processing.
- Rotate logs and clean old temporary files safely.
- Define retention rules for source, intermediate, final, and diagnostic files.
- Add health-check commands and a recovery runbook.
- Test recovery after Windows restart, WSL shutdown, runner failure, and iCloud client restart.

## Acceptance Criteria

- A PC restart restores the required services without manual command entry.
- The runner returns online automatically.
- Active jobs are not interrupted by sleep settings.
- Low disk space blocks new processing before corruption occurs.
- Logs do not grow without limit.
- iCloud export remains available after restart.

---

# Phase 11 — iPhone Manual Publishing Runbook

## Objective

Define a simple and repeatable human procedure for reviewing and publishing the final video.

## Manual Procedure

```text
Open the iPhone Files application
↓
Open iCloud Drive
↓
Open TikTokReady
↓
Open the latest video directory
↓
Review ready_to_post.mp4 completely
↓
Save locally or to Photos when required
↓
Open the TikTok application
↓
Select the video
↓
Enter the caption manually
↓
Add hashtags manually
↓
Confirm visibility, comments, sound, and other settings
↓
Press Publish
```

## Mandatory Human Checks

- Confirm the intended video was selected.
- Confirm every visible face is sufficiently hidden.
- Confirm no stamp exposes a face during fast movement.
- Confirm audio and video are synchronized.
- Confirm caption and hashtags are appropriate.
- Confirm the correct TikTok account is active.
- Confirm the intended visibility setting.

## Acceptance Criteria

- A completed video can be found from the iPhone without using GitHub artifacts.
- The human can review the full video before publishing.
- No automated step presses the TikTok publish button.
- The procedure is understandable without repository knowledge.

---

## 7. Cross-phase Test Matrix

Before routine use, the complete pipeline should be tested with at least:

- One clear frontal face.
- One side face.
- A small or distant face.
- Multiple people.
- Fast motion.
- Temporary occlusion.
- A face entering and leaving the frame.
- A no-face video.
- A silent video.
- A HEVC source video.
- An already H.264-compatible source video.
- A damaged or truncated input.
- An unavailable TikTok URL.
- A duplicate video ID.
- An iCloud destination that is temporarily unavailable.

Each test should record the expected result, actual result, output paths, and reviewer decision.

## 8. Final Definition of Done

The project reaches its initial production-ready state when all of the following are true:

1. A user can start the workflow from GitHub using a TikTok URL.
2. The home self-hosted runner downloads and normalizes the video.
3. Faces are detected, tracked, and covered by transparent PNG stamps.
4. Technical and face-coverage validation pass.
5. Invalid output is blocked from export.
6. Valid output is copied to `iCloud Drive/TikTokReady`.
7. The completed file is accessible from the iPhone Files application.
8. Duplicate processing is prevented unless explicitly forced.
9. Failures are retried only when appropriate and produce useful diagnostics.
10. The runner recovers after normal PC restarts.
11. A human reviews and publishes the video from the TikTok iPhone application.
12. No TikTok publishing API, browser automation, caption generation, or automatic publish operation is present.

## 9. Immediate Next Gate

The current development gate is Phase 4.

Phase 5 must not begin until:

- `tracked_detections.json` is stable and versioned.
- Track IDs are visually verified on representative videos.
- Short detection gaps are handled safely.
- Multi-person tracking does not show blocking identity swaps or merges.
- Coordinate smoothing does not expose faces through excessive lag.
- Automated tests pass.
- The user completes the Phase 4 review and gives approval.
