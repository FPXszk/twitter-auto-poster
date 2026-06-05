from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def transform_tracked_detections(
    detections_path: str | Path,
    output_path: str | Path,
    *,
    horizontal_flip: bool = False,
    speed: float = 1.0,
    force: bool = False,
) -> dict[str, Any]:
    source = Path(detections_path)
    target = Path(output_path)
    if not source.exists():
        raise FileNotFoundError(f"tracked detections file not found: {source}")
    if target.exists() and not force:
        raise FileExistsError(f"output already exists: {target}")
    if speed <= 0:
        raise ValueError("speed must be greater than zero")

    started_at = time.perf_counter()
    payload = json.loads(source.read_text(encoding="utf-8"))
    frames = payload.get("frames")
    if not isinstance(frames, list) or not frames:
        raise RuntimeError("tracked detections payload must contain non-empty frames")

    video = dict(payload.get("video") or {})
    fps = float(video.get("fps") or 0.0)
    if fps <= 0:
        raise RuntimeError("tracked detections payload must include video fps")

    base_frames: list[dict[str, Any]] = []
    for frame in frames:
        transformed_faces: list[dict[str, Any]] = []
        for face in list(frame.get("faces") or []):
            x = float(face["x"])
            width = float(face["width"])
            new_x = 1.0 - x - width if horizontal_flip else x
            transformed_faces.append({**face, "x": round(_clamp(new_x), 6)})
        base_frames.append(
            {
                "frame_index": int(frame["frame_index"]),
                "timestamp_ms": int(frame.get("timestamp_ms", 0)),
                "faces": transformed_faces,
            }
        )

    output_frame_count = max(1, int(round(len(base_frames) / speed)))
    transformed_frames: list[dict[str, Any]] = []
    for output_frame_index in range(output_frame_count):
        source_frame_index = min(len(base_frames) - 1, int(round(output_frame_index * speed)))
        source_frame = base_frames[source_frame_index]
        transformed_frames.append(
            {
                "frame_index": output_frame_index,
                "timestamp_ms": int(round((output_frame_index / fps) * 1000.0)),
                "faces": list(source_frame["faces"]),
            }
        )

    if video:
        video["duration_seconds"] = round(output_frame_count / fps, 6)
        video["total_frames"] = output_frame_count

    transformed_payload = {
        **payload,
        "video": video,
        "frames": transformed_frames,
        "transform": {
            "horizontal_flip": bool(horizontal_flip),
            "speed": float(speed),
        },
    }
    _write_json(target, transformed_payload)
    result = {
        "ok": True,
        "input_detections_path": str(source),
        "output_detections_path": str(target),
        "frames": len(transformed_frames),
        "horizontal_flip": bool(horizontal_flip),
        "speed": float(speed),
        "processing_seconds": round(time.perf_counter() - started_at, 6),
        "message": "tracked detections transformed",
    }
    logger.info("Transformed tracked detections for %s", source)
    return result
