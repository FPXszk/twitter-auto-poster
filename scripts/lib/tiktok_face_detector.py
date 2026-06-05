from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)


@dataclass
class FaceDetectionConfig:
    min_confidence: float = 0.5
    preview_interval: int = 30
    max_frames: int = 0


def _lazy_import_cv2():
    import cv2

    return cv2


def _lazy_import_mediapipe():
    import mediapipe as mp

    return mp


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_log(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _normalize_face(raw: Mapping[str, Any]) -> dict[str, float]:
    x = _clamp(float(raw["x"]))
    y = _clamp(float(raw["y"]))
    width = max(0.0, float(raw["width"]))
    height = max(0.0, float(raw["height"]))
    width = min(width, 1.0 - x)
    height = min(height, 1.0 - y)
    return {
        "x": round(x, 6),
        "y": round(y, 6),
        "width": round(width, 6),
        "height": round(height, 6),
        "confidence": round(_clamp(float(raw["confidence"])), 6),
    }


def _sort_faces(faces: list[dict[str, float]]) -> list[dict[str, float]]:
    return sorted(faces, key=lambda item: (item["x"], item["y"], item["width"], item["height"]))


def _default_yunet_model_path() -> Path:
    return Path(__file__).resolve().parents[2] / "models" / "opencv" / "face_detection_yunet_2023mar.onnx"


def _create_detector(min_confidence: float):
    cv2 = _lazy_import_cv2()

    class OpenCvYuNetDetector:
        name = "opencv-yunet-face-detector"
        version = getattr(cv2, "__version__", "")

        def __init__(self, model_path: Path, threshold: float):
            self._detector = cv2.FaceDetectorYN.create(
                str(model_path),
                "",
                (320, 320),
                threshold,
                0.3,
                5000,
            )

        def process(self, frame: Any) -> list[dict[str, float]]:
            height, width = frame.shape[:2]
            self._detector.setInputSize((width, height))
            _retval, detections = self._detector.detect(frame)
            if detections is None or detections.size == 0:
                return []
            faces: list[dict[str, float]] = []
            for detection in detections:
                x, y, box_width, box_height = detection[:4]
                faces.append(
                    _normalize_face(
                        {
                            "x": x / width,
                            "y": y / height,
                            "width": box_width / width,
                            "height": box_height / height,
                            "confidence": detection[-1],
                        }
                    )
                )
            return _sort_faces(faces)

        def close(self) -> None:
            return None

    class OpenCvCascadeDetector:
        name = "opencv-haarcascade-frontalface-default"
        version = getattr(cv2, "__version__", "")

        def __init__(self, threshold: float):
            cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            self._cascade = cv2.CascadeClassifier(str(cascade_path))
            if self._cascade.empty():
                raise RuntimeError(f"failed to load cascade file: {cascade_path}")
            self._threshold = threshold

        def process(self, frame: Any) -> list[dict[str, float]]:
            height, width = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detections = self._cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=max(3, int(round(self._threshold * 10))),
                minSize=(max(24, int(width * 0.08)), max(24, int(height * 0.08))),
            )
            faces: list[dict[str, float]] = []
            for x, y, box_width, box_height in detections:
                faces.append(
                    _normalize_face(
                        {
                            "x": x / width,
                            "y": y / height,
                            "width": box_width / width,
                            "height": box_height / height,
                            "confidence": 1.0,
                        }
                    )
                )
            return _sort_faces(faces)

        def close(self) -> None:
            return None

    yunet_model_path = _default_yunet_model_path()
    if hasattr(cv2, "FaceDetectorYN") and yunet_model_path.exists():
        return OpenCvYuNetDetector(yunet_model_path, min_confidence)

    logger.warning("YuNet model unavailable, falling back to OpenCV cascade detector")
    return OpenCvCascadeDetector(min_confidence)


def _extract_faces(detections: Any) -> list[dict[str, float]]:
    if detections and isinstance(detections, list) and isinstance(detections[0], dict):
        return _sort_faces([_normalize_face(item) for item in detections])
    faces: list[dict[str, float]] = []
    for detection in detections or []:
        score = float((detection.score or [0.0])[0])
        bbox = detection.location_data.relative_bounding_box
        faces.append(
            _normalize_face(
                {
                    "x": bbox.xmin,
                    "y": bbox.ymin,
                    "width": bbox.width,
                    "height": bbox.height,
                    "confidence": score,
                }
            )
        )
    return _sort_faces(faces)


def _write_preview(
    *,
    frame: Any,
    faces: list[dict[str, float]],
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
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            canvas,
            f'{face["confidence"]:.2f}',
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
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


def detect_faces_in_video(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    min_confidence: float = 0.5,
    preview_interval: int = 30,
    max_frames: int = 0,
    force: bool = False,
    detector_factory: Callable[[float], Any] | None = None,
) -> dict[str, Any]:
    cv2 = _lazy_import_cv2()
    source = Path(input_path)
    if not source.exists():
        raise FileNotFoundError(f"input video not found: {source}")

    out_dir = Path(output_dir)
    detections_path = out_dir / "detections.json"
    summary_path = out_dir / "summary.json"
    log_path = out_dir / "detect.log"
    preview_dir = out_dir / "preview"

    if not force and any(path.exists() for path in [detections_path, summary_path, log_path]):
        raise FileExistsError(f"output already exists: {out_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    config = FaceDetectionConfig(
        min_confidence=float(min_confidence),
        preview_interval=max(1, int(preview_interval)),
        max_frames=max(0, int(max_frames)),
    )
    _append_log(log_path, f"input={source}\nconfig={json.dumps(asdict(config), ensure_ascii=False)}\n")

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"failed to open video: {source}")

    detector = (detector_factory or _create_detector)(config.min_confidence)
    started_at = time.perf_counter()

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    total_frames_hint = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    frames: list[dict[str, Any]] = []
    processed_frames = 0
    frames_with_faces = 0
    total_detections = 0
    max_faces_in_frame = 0
    min_seen_confidence = 1.0
    max_seen_confidence = 0.0
    preview_images_written = 0

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break

            frame_index = processed_frames
            if config.max_frames and frame_index >= config.max_frames:
                break

            result = detector.process(frame)
            faces = _extract_faces(getattr(result, "detections", result))
            timestamp_ms = int(round((frame_index / fps) * 1000)) if fps > 0 else 0

            frames.append(
                {
                    "frame_index": frame_index,
                    "timestamp_ms": timestamp_ms,
                    "faces": faces,
                }
            )
            processed_frames += 1
            total_detections += len(faces)
            max_faces_in_frame = max(max_faces_in_frame, len(faces))
            if faces:
                frames_with_faces += 1
                min_seen_confidence = min(min_seen_confidence, min(face["confidence"] for face in faces))
                max_seen_confidence = max(max_seen_confidence, max(face["confidence"] for face in faces))

            if frame_index % config.preview_interval == 0:
                _write_preview(
                    frame=frame,
                    faces=faces,
                    frame_index=frame_index,
                    timestamp_ms=timestamp_ms,
                    preview_path=preview_dir / f"frame_{frame_index:06d}.jpg",
                )
                preview_images_written += 1
    finally:
        capture.release()
        close_method = getattr(detector, "close", None)
        if callable(close_method):
            close_method()

    if processed_frames == 0:
        raise RuntimeError("video contains zero readable frames")

    video_sha256 = _sha256(source)
    detections_payload = {
        "schema_version": 1,
        "video_path": str(source),
        "video_sha256": video_sha256,
        "detector": {
            "name": getattr(detector, "name", "face-detector"),
            "version": getattr(detector, "version", getattr(cv2, "__version__", "")),
            "min_confidence": config.min_confidence,
        },
        "video": {
            "width": width,
            "height": height,
            "fps": fps,
            "duration_seconds": round(processed_frames / fps, 6) if fps > 0 else 0.0,
            "total_frames": processed_frames,
        },
        "frames": frames,
    }
    _write_json(detections_path, detections_payload)

    summary_payload = {
        "ok": True,
        "video_path": str(source),
        "total_frames": total_frames_hint or processed_frames,
        "processed_frames": processed_frames,
        "frames_with_faces": frames_with_faces,
        "frames_without_faces": processed_frames - frames_with_faces,
        "total_detections": total_detections,
        "max_faces_in_frame": max_faces_in_frame,
        "average_faces_per_processed_frame": round(total_detections / processed_frames, 6),
        "minimum_confidence_observed": round(min_seen_confidence, 6) if total_detections else 0.0,
        "maximum_confidence_observed": round(max_seen_confidence, 6) if total_detections else 0.0,
        "processing_seconds": round(time.perf_counter() - started_at, 6),
        "preview_images_written": preview_images_written,
        "error_code": "",
        "message": "face detection completed",
    }
    _write_json(summary_path, summary_payload)
    _append_log(log_path, f"processed_frames={processed_frames}\ntotal_detections={total_detections}\n")
    logger.info("Face detection completed for %s", source)
    return summary_payload
