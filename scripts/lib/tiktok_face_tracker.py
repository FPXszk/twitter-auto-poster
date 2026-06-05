from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FaceTrackingConfig:
    smoothing_alpha: float = 0.3
    max_gap_frames: int = 5
    min_iou: float = 0.05
    max_center_distance: float = 0.2
    max_area_ratio: float = 3.0
    preview_interval: int = 30


def _lazy_import_cv2():
    import cv2

    return cv2


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_log(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _round_face(face: dict[str, Any]) -> dict[str, Any]:
    return {
        "track_id": int(face["track_id"]),
        "x": round(_clamp(float(face["x"])), 6),
        "y": round(_clamp(float(face["y"])), 6),
        "width": round(_clamp(float(face["width"]), 0.0, 1.0), 6),
        "height": round(_clamp(float(face["height"]), 0.0, 1.0), 6),
        "confidence": round(_clamp(float(face["confidence"])), 6),
        "interpolated": bool(face.get("interpolated", False)),
    }


def _center(face: dict[str, float]) -> tuple[float, float]:
    return (face["x"] + face["width"] / 2.0, face["y"] + face["height"] / 2.0)


def _center_distance(left: dict[str, float], right: dict[str, float]) -> float:
    left_x, left_y = _center(left)
    right_x, right_y = _center(right)
    return ((left_x - right_x) ** 2 + (left_y - right_y) ** 2) ** 0.5


def _area(face: dict[str, float]) -> float:
    return max(0.0, face["width"] * face["height"])


def _area_ratio(left: dict[str, float], right: dict[str, float]) -> float:
    left_area = max(_area(left), 1e-9)
    right_area = max(_area(right), 1e-9)
    larger = max(left_area, right_area)
    smaller = min(left_area, right_area)
    return larger / smaller


def _iou(left: dict[str, float], right: dict[str, float]) -> float:
    left_x2 = left["x"] + left["width"]
    left_y2 = left["y"] + left["height"]
    right_x2 = right["x"] + right["width"]
    right_y2 = right["y"] + right["height"]

    overlap_x1 = max(left["x"], right["x"])
    overlap_y1 = max(left["y"], right["y"])
    overlap_x2 = min(left_x2, right_x2)
    overlap_y2 = min(left_y2, right_y2)
    overlap_width = max(0.0, overlap_x2 - overlap_x1)
    overlap_height = max(0.0, overlap_y2 - overlap_y1)
    overlap = overlap_width * overlap_height
    union = _area(left) + _area(right) - overlap
    if union <= 0:
        return 0.0
    return overlap / union


def _smooth_face(previous: dict[str, float], current: dict[str, float], alpha: float) -> dict[str, float]:
    keep = 1.0 - alpha
    return {
        "x": previous["x"] * keep + current["x"] * alpha,
        "y": previous["y"] * keep + current["y"] * alpha,
        "width": previous["width"] * keep + current["width"] * alpha,
        "height": previous["height"] * keep + current["height"] * alpha,
        "confidence": current["confidence"],
    }


def _interpolate_face(
    previous: dict[str, float],
    current: dict[str, float],
    track_id: int,
    ratio: float,
) -> dict[str, Any]:
    return _round_face(
        {
            "track_id": track_id,
            "x": previous["x"] + (current["x"] - previous["x"]) * ratio,
            "y": previous["y"] + (current["y"] - previous["y"]) * ratio,
            "width": previous["width"] + (current["width"] - previous["width"]) * ratio,
            "height": previous["height"] + (current["height"] - previous["height"]) * ratio,
            "confidence": previous["confidence"] + (current["confidence"] - previous["confidence"]) * ratio,
            "interpolated": True,
        }
    )


def _make_output_frames(input_frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "frame_index": int(frame["frame_index"]),
            "timestamp_ms": int(frame.get("timestamp_ms", 0)),
            "faces": [],
        }
        for frame in input_frames
    ]


def _sort_output_faces(frames: list[dict[str, Any]]) -> None:
    for frame in frames:
        frame["faces"] = sorted(
            (_round_face(face) for face in frame["faces"]),
            key=lambda item: (item["track_id"], item["x"], item["y"]),
        )


def _match_faces(
    *,
    active_tracks: dict[int, dict[str, Any]],
    faces: list[dict[str, float]],
    frame_index: int,
    config: FaceTrackingConfig,
) -> list[tuple[int, int]]:
    candidates: list[tuple[float, float, float, int, int]] = []
    for track_id, track in active_tracks.items():
        gap = frame_index - track["last_frame_index"] - 1
        if gap > config.max_gap_frames:
            continue
        for face_index, face in enumerate(faces):
            last_face = track["last_face"]
            overlap = _iou(last_face, face)
            center_distance = _center_distance(last_face, face)
            area_ratio = _area_ratio(last_face, face)
            if overlap < config.min_iou and center_distance > config.max_center_distance:
                continue
            if area_ratio > config.max_area_ratio:
                continue
            candidates.append((-overlap, center_distance, area_ratio, track_id, face_index))

    matches: list[tuple[int, int]] = []
    used_tracks: set[int] = set()
    used_faces: set[int] = set()
    for _neg_overlap, _distance, _ratio, track_id, face_index in sorted(candidates):
        if track_id in used_tracks or face_index in used_faces:
            continue
        used_tracks.add(track_id)
        used_faces.add(face_index)
        matches.append((track_id, face_index))
    return matches


def _write_preview(
    *,
    frame: Any,
    faces: list[dict[str, Any]],
    frame_index: int,
    timestamp_ms: int,
    preview_path: Path,
) -> None:
    cv2 = _lazy_import_cv2()
    canvas = frame.copy()
    height, width = canvas.shape[:2]
    for face in faces:
        x1 = int(face["x"] * width)
        y1 = int(face["y"] * height)
        x2 = int((face["x"] + face["width"]) * width)
        y2 = int((face["y"] + face["height"]) * height)
        color = (0, 255, 255) if face.get("interpolated") else (0, 255, 0)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        label = f'id={face["track_id"]} {"I" if face.get("interpolated") else "D"}'
        cv2.putText(
            canvas,
            label,
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
            cv2.LINE_AA,
        )
    cv2.putText(
        canvas,
        f"frame={frame_index} time_ms={timestamp_ms}",
        (20, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(preview_path), canvas)


def track_faces_in_detections(
    detections_path: str | Path,
    output_dir: str | Path,
    *,
    smoothing_alpha: float = 0.3,
    max_gap_frames: int = 5,
    min_iou: float = 0.05,
    max_center_distance: float = 0.2,
    max_area_ratio: float = 3.0,
    preview_interval: int = 30,
    force: bool = False,
) -> dict[str, Any]:
    source_path = Path(detections_path)
    if not source_path.exists():
        raise FileNotFoundError(f"detections file not found: {source_path}")

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    input_frames = payload.get("frames")
    if not isinstance(input_frames, list) or not input_frames:
        raise RuntimeError("detections payload must contain non-empty frames")

    output_root = Path(output_dir)
    tracked_path = output_root / "tracked_detections.json"
    summary_path = output_root / "tracking_summary.json"
    log_path = output_root / "track.log"
    preview_dir = output_root / "preview"
    if not force and any(path.exists() for path in [tracked_path, summary_path, log_path]):
        raise FileExistsError(f"output already exists: {output_root}")

    config = FaceTrackingConfig(
        smoothing_alpha=_clamp(float(smoothing_alpha), 0.0, 1.0),
        max_gap_frames=max(0, int(max_gap_frames)),
        min_iou=_clamp(float(min_iou), 0.0, 1.0),
        max_center_distance=max(0.0, float(max_center_distance)),
        max_area_ratio=max(1.0, float(max_area_ratio)),
        preview_interval=max(1, int(preview_interval)),
    )
    _append_log(
        log_path,
        f"input={source_path}\nconfig={json.dumps(asdict(config), ensure_ascii=False)}\n",
    )

    started_at = time.perf_counter()
    tracked_frames = _make_output_frames(input_frames)
    active_tracks: dict[int, dict[str, Any]] = {}
    next_track_id = 1
    matched_detections = 0
    new_tracks_started = 0
    interpolated_faces = 0
    longest_gap_filled = 0

    for frame in input_frames:
        frame_index = int(frame["frame_index"])
        frame_faces = [dict(face) for face in frame.get("faces", [])]
        matches = _match_faces(
            active_tracks=active_tracks,
            faces=frame_faces,
            frame_index=frame_index,
            config=config,
        )

        matched_face_indexes = {face_index for _track_id, face_index in matches}
        for track_id, face_index in matches:
            matched_detections += 1
            current_face = frame_faces[face_index]
            track = active_tracks[track_id]
            smoothed_face = _smooth_face(track["last_face"], current_face, config.smoothing_alpha)
            gap = frame_index - track["last_frame_index"] - 1
            if gap > 0:
                longest_gap_filled = max(longest_gap_filled, gap)
                for offset in range(1, gap + 1):
                    interpolation_ratio = offset / (gap + 1)
                    tracked_frames[track["last_frame_index"] + offset]["faces"].append(
                        _interpolate_face(track["last_face"], smoothed_face, track_id, interpolation_ratio)
                    )
                    interpolated_faces += 1
            tracked_frames[frame_index]["faces"].append(
                _round_face(
                    {
                        "track_id": track_id,
                        **smoothed_face,
                        "interpolated": False,
                    }
                )
            )
            track["last_face"] = smoothed_face
            track["last_frame_index"] = frame_index

        for face_index, face in enumerate(frame_faces):
            if face_index in matched_face_indexes:
                continue
            track_id = next_track_id
            next_track_id += 1
            new_tracks_started += 1
            tracked_frames[frame_index]["faces"].append(
                _round_face(
                    {
                        "track_id": track_id,
                        **face,
                        "interpolated": False,
                    }
                )
            )
            active_tracks[track_id] = {
                "last_face": dict(face),
                "last_frame_index": frame_index,
            }

        expired_track_ids = [
            track_id
            for track_id, track in active_tracks.items()
            if frame_index - track["last_frame_index"] > config.max_gap_frames
        ]
        for track_id in expired_track_ids:
            active_tracks.pop(track_id, None)

    _sort_output_faces(tracked_frames)

    video_path = Path(payload.get("video_path", ""))
    if not video_path.exists():
        raise FileNotFoundError(f"tracked preview source video not found: {video_path}")

    cv2 = _lazy_import_cv2()
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"failed to open preview source video: {video_path}")

    preview_images_written = 0
    try:
        preview_index = 0
        while True:
            ok, frame = capture.read()
            if not ok or preview_index >= len(tracked_frames):
                break
            tracked_frame = tracked_frames[preview_index]
            if preview_index % config.preview_interval == 0:
                _write_preview(
                    frame=frame,
                    faces=tracked_frame["faces"],
                    frame_index=tracked_frame["frame_index"],
                    timestamp_ms=tracked_frame["timestamp_ms"],
                    preview_path=preview_dir / f"frame_{preview_index:06d}.jpg",
                )
                preview_images_written += 1
            preview_index += 1
    finally:
        capture.release()

    tracked_payload = {
        "schema_version": 1,
        "source_detections_path": str(source_path),
        "video_path": str(video_path),
        "video_sha256": payload.get("video_sha256", ""),
        "tracker": {
            "name": "lightweight-iou-center-tracker",
            "smoothing_alpha": config.smoothing_alpha,
            "max_gap_frames": config.max_gap_frames,
            "min_iou": config.min_iou,
            "max_center_distance": config.max_center_distance,
            "max_area_ratio": config.max_area_ratio,
        },
        "video": payload.get("video", {}),
        "frames": tracked_frames,
    }
    _write_json(tracked_path, tracked_payload)

    frames_with_tracks = sum(1 for frame in tracked_frames if frame["faces"])
    frames_with_interpolated_faces = sum(
        1 for frame in tracked_frames if any(face.get("interpolated") for face in frame["faces"])
    )
    total_tracked_faces = sum(len(frame["faces"]) for frame in tracked_frames)
    summary_payload = {
        "ok": True,
        "source_detections_path": str(source_path),
        "video_path": str(video_path),
        "total_frames": len(tracked_frames),
        "frames_with_tracks": frames_with_tracks,
        "frames_without_tracks": len(tracked_frames) - frames_with_tracks,
        "total_tracked_faces": total_tracked_faces,
        "track_count": new_tracks_started,
        "matched_detections": matched_detections,
        "interpolated_faces": interpolated_faces,
        "frames_with_interpolated_faces": frames_with_interpolated_faces,
        "longest_gap_filled": longest_gap_filled,
        "preview_images_written": preview_images_written,
        "processing_seconds": round(time.perf_counter() - started_at, 6),
        "error_code": "",
        "message": "face tracking completed",
    }
    _write_json(summary_path, summary_payload)
    _append_log(
        log_path,
        "track_count={track_count}\nmatched_detections={matched_detections}\ninterpolated_faces={interpolated_faces}\n".format(
            **summary_payload
        ),
    )
    logger.info("Face tracking completed for %s", source_path)
    return summary_payload
