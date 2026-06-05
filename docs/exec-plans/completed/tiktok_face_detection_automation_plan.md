# TikTok Face Detection and Automation Roadmap

## 0. Current Status

Completed:

```text
Phase 0: Repository investigation and test baseline
Phase 1: TikTok metadata retrieval and video download
Phase 2: Automatic normalization to MP4 / H.264 / AAC / yuv420p
```

Current working flow:

```text
TikTok URL
→ metadata retrieval
→ source.mp4 download
→ ffprobe inspection
→ H.264 / AAC / yuv420p normalization
→ normalized.mp4
→ decode validation
→ Windows playback confirmation
```

All subsequent video processing must use `normalized.mp4`. Keep `source.mp4` unchanged as the original downloaded artifact.

---

# 1. Remaining Roadmap

```text
Phase 3: Face detection
Phase 4: Face tracking
Phase 5: Face-stamp overlay and edited video generation
Phase 6: Video analysis and caption generation
Phase 7: End-to-end dry-run pipeline
Phase 8: Official TikTok API publishing
Phase 9: State management, retry handling, and duplicate prevention
Phase 10: Automated execution and limited production validation
```

Complete and manually validate one phase before moving to the next. Do not implement multiple phases at once.

---

# 2. Phase 3: Face Detection Only

## 2.1 Objective

Read `normalized.mp4` and detect human faces in every frame.

This phase must only produce detection data and preview artifacts. It must not:

- modify the video
- add stamps
- track identities between frames
- generate captions
- publish anything
- change GitHub Actions

## 2.2 Processing Flow

```text
normalized.mp4
→ open video
→ read every frame
→ run face detection
→ record coordinates and confidence
→ generate periodic preview images
→ write detections.json
→ write summary.json
→ write detect.log
```

## 2.3 Recommended Detector

First candidate:

```text
MediaPipe Face Detection
```

Reasons:

- practical on CPU
- easy Python integration
- suitable for initial validation
- supports frontal and moderately rotated faces
- works with OpenCV frame processing

Before installation, verify compatibility with the repository's Python version. If incompatible, use another maintained CPU-compatible detector and document the reason.

Fallback candidates:

```text
OpenCV DNN face detector
YOLO-based face detector
```

Do not introduce a GPU-only dependency in the first implementation.

## 2.4 Dependencies

Candidate installation:

```bash
cd ~/code/twitter-auto-poster
source python/.venv/bin/activate
python3 -m pip install mediapipe opencv-python-headless
```

Verify:

```bash
python3 -c "import cv2; print(cv2.__version__)"
python3 -c "import mediapipe as mp; print(mp.__version__)"
```

Pin versions if required and document them in the project dependency configuration and RUNBOOK.

## 2.5 Proposed CLI

Create:

```text
scripts/tiktok/detect_faces.py
```

Expected command:

```bash
python3 scripts/tiktok/detect_faces.py \
  --input tmp/tiktok-debug/downloads/7617854844279393556/normalized.mp4 \
  --output-dir tmp/tiktok-debug/downloads/7617854844279393556/faces \
  --log-level DEBUG
```

Recommended arguments:

```text
--input INPUT_VIDEO
--output-dir OUTPUT_DIR
--min-confidence MIN_CONFIDENCE
--preview-interval PREVIEW_INTERVAL
--max-frames MAX_FRAMES
--log-level LOG_LEVEL
--force
```

Initial defaults:

```text
min confidence: 0.5
preview interval: 30 frames
max frames: unlimited
```

`--max-frames` is for debugging only. Normal execution should process the entire video.

## 2.6 Output Structure

```text
faces/
├── detections.json
├── summary.json
├── detect.log
└── preview/
    ├── frame_000000.jpg
    ├── frame_000030.jpg
    ├── frame_000060.jpg
    └── ...
```

Do not overwrite unrelated artifacts. Reuse existing output only when the source-video hash and detector configuration match; otherwise require `--force`.

## 2.7 detections.json

Recommended structure:

```json
{
  "schema_version": 1,
  "video_path": "normalized.mp4",
  "video_sha256": "...",
  "detector": {
    "name": "mediapipe-face-detection",
    "version": "...",
    "min_confidence": 0.5
  },
  "video": {
    "width": 1080,
    "height": 1920,
    "fps": 30.0,
    "duration_seconds": 5.0,
    "total_frames": 150
  },
  "frames": [
    {
      "frame_index": 0,
      "timestamp_ms": 0,
      "faces": [
        {
          "x": 0.32,
          "y": 0.16,
          "width": 0.22,
          "height": 0.18,
          "confidence": 0.94
        }
      ]
    }
  ]
}
```

Requirements:

- normalized coordinates from `0.0` to `1.0`
- clamp coordinates to video boundaries
- support multiple faces
- deterministic ordering, preferably left-to-right then top-to-bottom
- preserve confidence
- no identity or name inference

## 2.8 summary.json

Recommended structure:

```json
{
  "ok": true,
  "video_path": "normalized.mp4",
  "total_frames": 150,
  "processed_frames": 150,
  "frames_with_faces": 142,
  "frames_without_faces": 8,
  "total_detections": 156,
  "max_faces_in_frame": 2,
  "average_faces_per_processed_frame": 1.04,
  "minimum_confidence_observed": 0.71,
  "maximum_confidence_observed": 0.99,
  "processing_seconds": 4.8,
  "preview_images_written": 5,
  "error_code": "",
  "message": "face detection completed"
}
```

A video with no human faces must still return success.

## 2.9 Preview Images

Write preview images at the configured interval with:

- frame number
- timestamp
- bounding boxes
- confidence values

Preview images are for human review only and must not become the source of truth for later processing.

## 2.10 Initial Processing Policy

For the current five-second, 30-fps test video:

```text
5 seconds × 30 fps ≈ 150 frames
```

Process every frame. Do not optimize by frame skipping until detection quality is established.

## 2.11 Known Detection Limits

Document likely failures with:

- profile faces
- partially covered faces
- very small faces
- fast motion and blur
- dark scenes
- back-facing heads
- edge-of-frame faces
- photos, posters, or screens
- heavily filtered faces

For privacy processing, false negatives are more serious than false positives. Never allow public auto-publishing based only on detector success.

## 2.12 Manual Test Set

Use only self-owned or authorized videos.

### Test A: No human face

Examples: animal, landscape, object.

Expected:

```text
total_detections = 0
ok = true
```

The current rabbit video is suitable.

### Test B: One frontal face

Expected: approximately one face in most frames.

### Test C: Profile face

Expected: detection in a useful percentage of frames.

### Test D: Multiple people

Expected: multiple detections in the same frame.

### Test E: Temporary occlusion

Expected: detection may temporarily disappear. This will be handled in Phase 4.

## 2.13 Unit Tests

Add tests for:

```text
missing input
invalid video
zero readable frames
detector initialization failure
single face
multiple faces
no face
normalized coordinate conversion
boundary clamping
deterministic ordering
confidence filtering
preview interval
summary generation
JSON schema fields
existing-output reuse
force overwrite
log generation
```

Network access must not be required. Mock the detector where appropriate.

## 2.14 Regression Tests

Existing tests must continue to pass:

```bash
python3 -m unittest \
  tests.test_tiktok_downloader \
  tests.test_tiktok_download_cli \
  tests.test_tiktok_pipeline
```

Add the new tests:

```bash
python3 -m unittest \
  tests.test_tiktok_face_detector \
  tests.test_tiktok_downloader \
  tests.test_tiktok_download_cli \
  tests.test_tiktok_pipeline
```

Also run syntax validation on changed Python files.

## 2.15 Manual Debug Procedure

```bash
VIDEO_DIR="tmp/tiktok-debug/downloads/7617854844279393556"

python3 scripts/tiktok/detect_faces.py \
  --input "$VIDEO_DIR/normalized.mp4" \
  --output-dir "$VIDEO_DIR/faces" \
  --log-level DEBUG
```

List outputs:

```bash
find "$VIDEO_DIR/faces" \
  -type f \
  -printf '%p  %s bytes\n' \
  | sort
```

Inspect summary:

```bash
cat "$VIDEO_DIR/faces/summary.json"
```

Or:

```bash
jq . "$VIDEO_DIR/faces/summary.json"
```

Inspect the first frames:

```bash
python3 - <<'PY'
import json
from pathlib import Path

path = Path("tmp/tiktok-debug/downloads/7617854844279393556/faces/detections.json")
data = json.loads(path.read_text(encoding="utf-8"))
print(json.dumps(data["frames"][:5], ensure_ascii=False, indent=2))
PY
```

Open previews in Windows:

```bash
explorer.exe "$(wslpath -w "$VIDEO_DIR/faces/preview")"
```

Human review points:

- boxes align with faces
- face-free frames do not contain excessive false positives
- small faces are not consistently missed
- multiple faces are all detected
- coordinates remain inside frame boundaries
- source video remains unchanged
- logs contain no secrets

## 2.16 Phase 3 Completion Criteria

```text
[ ] normalized.mp4 accepted as input
[ ] source video never modified
[ ] all frames processed
[ ] zero-face video succeeds
[ ] multiple faces supported
[ ] detections.json generated
[ ] summary.json generated
[ ] detect.log generated
[ ] preview images generated
[ ] coordinates normalized
[ ] confidence values saved
[ ] unit tests pass
[ ] existing TikTok tests pass
[ ] preview images reviewed by a human
[ ] detector limitations documented
```

Do not proceed to Phase 4 until all criteria are met.

---

# 3. Phase 4: Face Tracking

## Objective

Associate detections across frames and assign stable `track_id` values.

Goals:

- reduce bounding-box jitter
- bridge brief detector dropouts
- prepare stable coordinates for face-stamp overlay

Do not add stamps in this phase.

## Processing Flow

```text
detections.json
→ match faces across adjacent frames
→ assign track_id
→ smooth boxes
→ fill short gaps
→ write tracked_detections.json
→ generate tracking previews
```

## Initial Tracking Method

Use a lightweight deterministic tracker based on:

```text
bounding-box IoU
center-point distance
size change
previous track state
maximum missing-frame threshold
```

Recommended matching priority:

1. highest IoU
2. smallest normalized center distance
3. smallest size change

## Smoothing

Recommended exponential smoothing:

```text
smoothed = previous × 0.7 + current × 0.3
```

Make the factor configurable.

## Gap Filling

Initial maximum gap:

```text
5 frames
```

At 30 fps this is approximately 0.17 seconds. Mark interpolated entries explicitly.

## Output Example

```json
{
  "frame_index": 30,
  "timestamp_ms": 1000,
  "faces": [
    {
      "track_id": 1,
      "x": 0.31,
      "y": 0.15,
      "width": 0.23,
      "height": 0.19,
      "confidence": 0.91,
      "interpolated": false
    }
  ]
}
```

## Completion Criteria

```text
[ ] stable track_id values
[ ] reduced jitter
[ ] short gaps bridged
[ ] multiple tracks supported
[ ] acceptable ID switching
[ ] tracking JSON generated
[ ] previews generated
[ ] unit tests pass
[ ] human review complete
```

---

# 4. Phase 5: Face-Stamp Overlay

## Objective

Use tracked face coordinates to overlay a transparent PNG stamp on every detected human face.

Inputs:

```text
normalized.mp4
tracked_detections.json
transparent PNG stamp
```

Output:

```text
edited.mp4
```

## Asset Structure

```text
assets/
└── face_stamps/
    └── default.png
```

## Overlay Rules

Initial scale:

```text
face width × 1.4
face height × 1.4
```

Privacy-oriented scale:

```text
face width × 1.6
face height × 1.6
```

Make scale configurable. Clamp overlay coordinates to frame boundaries and support multiple faces.

## Output Format

```text
container: MP4
video codec: H.264
audio codec: AAC
pixel format: yuv420p
movflags: +faststart
```

Reuse the Phase 2 normalization and validation utilities. Preserve resolution, frame rate, duration, audio, and synchronization.

## Proposed CLI

```bash
python3 scripts/tiktok/overlay_faces.py \
  --input "$VIDEO_DIR/normalized.mp4" \
  --detections "$VIDEO_DIR/faces/tracked_detections.json" \
  --stamp assets/face_stamps/default.png \
  --output "$VIDEO_DIR/edited.mp4" \
  --scale 1.6 \
  --log-level DEBUG
```

## Validation

```bash
ffmpeg \
  -v error \
  -i "$VIDEO_DIR/edited.mp4" \
  -f null -
```

Compare source and output:

```text
duration within tolerance
same width and height
equivalent fps
same audio presence
H.264 / AAC / yuv420p
```

## Human Review

Open the folder:

```bash
explorer.exe "$(wslpath -w "$VIDEO_DIR")"
```

Check:

- all faces covered
- no excessive jitter
- stamp follows motion
- temporary occlusion handled acceptably
- multiple people covered
- stamp disappears when face leaves frame
- audio remains synchronized
- duration is unchanged
- output plays without paid HEVC extensions

## Safety Gate

Do not allow automatic public publishing when face coverage is uncertain, tracking is unstable, processing fails, output validation fails, or human review is incomplete.

---

# 5. Phase 6: Video Analysis and Caption Generation

## Objective

Generate a draft caption from video metadata and content. Do not publish automatically.

Inputs may include:

```text
original TikTok title
creator/source attribution
video metadata
audio transcription
sampled frames
OCR results
permission/source information
```

Processing:

```text
extract audio
→ transcribe speech
→ extract representative frames
→ OCR visible text
→ generate caption draft
→ generate hashtags
→ preserve source attribution
→ require human review
```

Outputs:

```text
caption/
├── transcript.txt
├── ocr.json
├── caption.txt
├── caption.json
└── generation.log
```

Caption rules:

- do not invent events
- do not infer identities
- do not expose personal information
- do not copy the original caption verbatim
- preserve required attribution
- avoid exaggerated claims
- require review initially

---

# 6. Phase 7: End-to-End Dry-Run Pipeline

## Objective

Connect completed stages without publishing.

```text
TikTok URL
→ download source.mp4
→ normalize to normalized.mp4
→ detect faces
→ track faces
→ overlay stamp
→ validate edited.mp4
→ generate caption draft
→ produce review artifacts
→ stop
```

Proposed command:

```bash
python3 scripts/tiktok/pipeline.py \
  --url "$TIKTOK_URL" \
  --output-dir tmp/tiktok-jobs \
  --dry-run true
```

Expected structure:

```text
tmp/tiktok-jobs/<job_id>/
├── input.json
├── source/
│   ├── source.mp4
│   ├── normalized.mp4
│   ├── metadata.json
│   ├── ffprobe.json
│   └── normalized.ffprobe.json
├── faces/
│   ├── detections.json
│   ├── tracked_detections.json
│   ├── summary.json
│   └── preview/
├── edited/
│   ├── edited.mp4
│   ├── edited.ffprobe.json
│   └── coverage_report.json
├── caption/
│   ├── transcript.txt
│   ├── caption.txt
│   └── caption.json
├── logs/
└── result.json
```

---

# 7. Phase 8: Official TikTok API Publishing

## Objective

Publish only approved edited videos through TikTok's official posting API.

Before implementation, verify the latest official documentation for:

- TikTok Developer application
- OAuth
- Content Posting API
- `video.publish` scope
- upload initialization
- upload URL
- publish-status polling
- privacy level
- app review
- token refresh
- rate limits

Do not use browser automation as the primary publishing method.

Initial publishing must use the safest available privacy setting. Require explicit `--publish`, explicit privacy level, approved job state, validated edited video, reviewed caption, duplicate check, and valid access token.

---

# 8. Phase 9: State, Retry, and Duplicate Prevention

Recommended states:

```text
CREATED
DOWNLOADED
NORMALIZED
FACE_DETECTED
FACE_TRACKED
EDITED
CAPTION_GENERATED
REVIEW_REQUIRED
APPROVED
PUBLISHING
PUBLISHED
FAILED
REJECTED
```

Store:

- job ID
- source URL and resolved URL
- TikTok video ID
- source, normalized, edited, and caption hashes
- current stage
- last error
- retry count
- publish ID
- published URL
- timestamps
- Git commit SHA
- pipeline version

Never republish an already published source without an explicit override.

---

# 9. Phase 10: Automated Execution

Recommended rollout:

```text
1. local manual execution
2. WSL manual execution
3. self-hosted runner manual execution
4. workflow_dispatch
5. scheduled execution
```

Do not begin with scheduled public posting.

Artifacts must exclude cookies, access tokens, refresh tokens, client secrets, and browser profile data.

---

# 10. Immediate CLI Implementation Request

Give this instruction to the implementation CLI:

```text
Read the original plan.md and all current progress notes.

Phase 0, Phase 1, and Phase 2 are complete.

The current pipeline can:
- retrieve TikTok metadata
- download source.mp4
- inspect the downloaded video
- automatically normalize it to MP4 / H.264 / AAC / yuv420p
- write normalized.mp4
- validate it with ffprobe
- perform decode validation
- play it in Windows without requiring the paid HEVC extension

Implement Phase 3 only: face detection.

Purpose:
Read normalized.mp4 and save human-face bounding boxes and confidence values without modifying the video.

Requirements:
1. Input must be normalized.mp4.
2. Never modify source.mp4 or normalized.mp4.
3. Use MediaPipe Face Detection or another maintained CPU-compatible detector if MediaPipe is incompatible with the current Python version.
4. Process every frame for the initial implementation.
5. Save frame_index and timestamp_ms for each processed frame.
6. Save x, y, width, height, and confidence for each face.
7. Coordinates must be normalized to 0.0–1.0.
8. Support multiple faces.
9. A video with no human faces must complete successfully.
10. Save detections.json.
11. Save summary.json.
12. Save detect.log.
13. Save periodic preview images with face boxes.
14. Add scripts/tiktok/detect_faces.py.
15. Allow output directory selection.
16. Add configurable minimum confidence and preview interval.
17. Add unit tests for detector logic and CLI.
18. Preserve all existing TikTok downloader, normalization, and pipeline tests.
19. Document new dependencies and installation commands.
20. Do not implement face tracking.
21. Do not implement stamp overlay.
22. Do not implement caption generation.
23. Do not implement TikTok publishing.
24. Do not change GitHub Actions.

After implementation, report in Japanese:
- changed files
- selected detector
- dependency versions
- test commands and results
- manual validation commands
- generated artifacts
- known detector limitations
- Go / Conditional Go / No-Go recommendation for Phase 4
```

---

# 11. Final Rule

Implement and validate one phase at a time.

The next action is Phase 3 face detection only. Do not proceed to tracking, stamp overlay, caption generation, publishing, or automation until face-detection output has been reviewed by a human.
