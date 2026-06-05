from __future__ import annotations

import importlib.util
import json
import logging
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

NORMALIZER_PATH = Path(__file__).resolve().with_name("tiktok_video_normalizer.py")
normalizer_spec = importlib.util.spec_from_file_location("repo_tiktok_video_normalizer_for_overlay", NORMALIZER_PATH)
if normalizer_spec is None or normalizer_spec.loader is None:
    raise RuntimeError(f"failed to load video normalizer helper from {NORMALIZER_PATH}")
normalizer_module = importlib.util.module_from_spec(normalizer_spec)
normalizer_spec.loader.exec_module(normalizer_module)

probe_video = normalizer_module.probe_video

logger = logging.getLogger(__name__)


@dataclass
class FaceOverlayConfig:
    scale: float = 1.6
    anchor_y_ratio: float = 0.5
    jpeg_quality: int = 95


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


def _ffmpeg_bin() -> str:
    value = shutil.which("ffmpeg")
    if not value:
        raise RuntimeError("ffmpeg is required for TikTok face overlay")
    return value


def _run(command: list[str], *, log_path: Path) -> subprocess.CompletedProcess[str]:
    _append_log(log_path, f"$ {' '.join(command)}\n")
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.stdout:
        _append_log(log_path, f"[stdout]\n{result.stdout}\n")
    if result.stderr:
        _append_log(log_path, f"[stderr]\n{result.stderr}\n")
    _append_log(log_path, f"[exit_code] {result.returncode}\n\n")
    return result


def _validate_decoding(path: Path, *, log_path: Path) -> None:
    result = _run(
        [
            _ffmpeg_bin(),
            "-v",
            "error",
            "-i",
            str(path),
            "-f",
            "null",
            "-",
        ],
        log_path=log_path,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ffmpeg decode validation failed")


def _load_stamp_rgba(stamp_path: Path) -> np.ndarray:
    stamp = Image.open(stamp_path).convert("RGBA")
    return np.array(stamp)


def _compute_overlay_box(
    face: dict[str, Any],
    *,
    frame_width: int,
    frame_height: int,
    scale: float,
    anchor_y_ratio: float,
) -> tuple[int, int, int, int]:
    face_center_x = (float(face["x"]) + float(face["width"]) / 2.0) * frame_width
    face_center_y = (float(face["y"]) + float(face["height"]) * anchor_y_ratio) * frame_height
    overlay_width = max(1, int(round(float(face["width"]) * frame_width * scale)))
    overlay_height = max(1, int(round(float(face["height"]) * frame_height * scale)))
    x1 = int(round(face_center_x - overlay_width / 2.0))
    y1 = int(round(face_center_y - overlay_height / 2.0))
    x2 = x1 + overlay_width
    y2 = y1 + overlay_height
    return x1, y1, x2, y2


def _overlay_stamp_on_frame(
    *,
    frame: np.ndarray,
    stamp_rgba: np.ndarray,
    face: dict[str, Any],
    scale: float,
    anchor_y_ratio: float,
) -> bool:
    frame_height, frame_width = frame.shape[:2]
    x1, y1, x2, y2 = _compute_overlay_box(
        face,
        frame_width=frame_width,
        frame_height=frame_height,
        scale=scale,
        anchor_y_ratio=anchor_y_ratio,
    )
    clipped_x1 = max(0, x1)
    clipped_y1 = max(0, y1)
    clipped_x2 = min(frame_width, x2)
    clipped_y2 = min(frame_height, y2)
    if clipped_x1 >= clipped_x2 or clipped_y1 >= clipped_y2:
        return False

    target_width = max(1, x2 - x1)
    target_height = max(1, y2 - y1)
    resized = Image.fromarray(stamp_rgba, mode="RGBA").resize((target_width, target_height), Image.Resampling.LANCZOS)
    stamp_array = np.array(resized)

    crop_x1 = clipped_x1 - x1
    crop_y1 = clipped_y1 - y1
    crop_x2 = crop_x1 + (clipped_x2 - clipped_x1)
    crop_y2 = crop_y1 + (clipped_y2 - clipped_y1)
    stamp_crop = stamp_array[crop_y1:crop_y2, crop_x1:crop_x2]
    if stamp_crop.size == 0:
        return False

    alpha = stamp_crop[:, :, 3:4].astype(np.float32) / 255.0
    if float(alpha.max()) <= 0.0:
        return False

    stamp_bgr = stamp_crop[:, :, :3][:, :, ::-1].astype(np.float32)
    roi = frame[clipped_y1:clipped_y2, clipped_x1:clipped_x2].astype(np.float32)
    blended = alpha * stamp_bgr + (1.0 - alpha) * roi
    frame[clipped_y1:clipped_y2, clipped_x1:clipped_x2] = np.clip(blended, 0, 255).astype(np.uint8)
    return True


def overlay_faces_on_video(
    input_path: str | Path,
    detections_path: str | Path,
    stamp_path: str | Path,
    output_path: str | Path,
    *,
    scale: float = 1.6,
    anchor_y_ratio: float = 0.5,
    force: bool = False,
) -> dict[str, Any]:
    source = Path(input_path)
    tracked_path = Path(detections_path)
    stamp_file = Path(stamp_path)
    target = Path(output_path)
    if not source.exists():
        raise FileNotFoundError(f"input video not found: {source}")
    if not tracked_path.exists():
        raise FileNotFoundError(f"tracked detections file not found: {tracked_path}")
    if not stamp_file.exists():
        raise FileNotFoundError(f"stamp asset not found: {stamp_file}")

    output_root = target.parent
    summary_path = output_root / "overlay-summary.json"
    coverage_path = output_root / "face-coverage-report.json"
    log_path = output_root / "processing.log"
    source_probe_json_path = output_root / "edited.source.ffprobe.json"
    edited_probe_json_path = output_root / "edited.ffprobe.json"

    if not force and any(path.exists() for path in [target, summary_path, coverage_path, log_path]):
        raise FileExistsError(f"output already exists in: {output_root}")

    config = FaceOverlayConfig(scale=max(0.1, float(scale)), anchor_y_ratio=float(anchor_y_ratio))
    _append_log(
        log_path,
        "input={input}\ndetections={detections}\nstamp={stamp}\nconfig={config}\n".format(
            input=source,
            detections=tracked_path,
            stamp=stamp_file,
            config=json.dumps(asdict(config), ensure_ascii=False),
        ),
    )

    payload = json.loads(tracked_path.read_text(encoding="utf-8"))
    frames = payload.get("frames")
    if not isinstance(frames, list) or not frames:
        raise RuntimeError("tracked detections payload must contain non-empty frames")

    stamp_rgba = _load_stamp_rgba(stamp_file)
    cv2 = _lazy_import_cv2()
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"failed to open input video: {source}")

    started_at = time.perf_counter()
    frames_written = 0
    faces_expected = 0
    faces_covered = 0
    interpolated_faces = 0
    frame_reports: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="tiktok-face-overlay-") as tmpdir:
        temp_root = Path(tmpdir)
        frames_dir = temp_root / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        try:
            frame_index = 0
            while True:
                ok, frame = capture.read()
                if not ok or frame_index >= len(frames):
                    break
                tracked_frame = frames[frame_index]
                expected_faces = list(tracked_frame.get("faces", []))
                frame_covered = 0
                for face in expected_faces:
                    if bool(face.get("interpolated")):
                        interpolated_faces += 1
                    if _overlay_stamp_on_frame(
                        frame=frame,
                        stamp_rgba=stamp_rgba,
                        face=face,
                        scale=config.scale,
                        anchor_y_ratio=config.anchor_y_ratio,
                    ):
                        frame_covered += 1

                frame_path = frames_dir / f"frame_{frame_index:06d}.png"
                if not cv2.imwrite(str(frame_path), frame):
                    raise RuntimeError(f"failed to write overlay frame: {frame_path}")

                faces_expected += len(expected_faces)
                faces_covered += frame_covered
                frames_written += 1
                frame_reports.append(
                    {
                        "frame_index": int(tracked_frame["frame_index"]),
                        "timestamp_ms": int(tracked_frame.get("timestamp_ms", 0)),
                        "expected_faces": len(expected_faces),
                        "covered_faces": frame_covered,
                    }
                )
                frame_index += 1
        finally:
            capture.release()

        if frames_written == 0:
            raise RuntimeError("video contains zero readable frames")

        source_probe = probe_video(source, ffprobe_json_path=source_probe_json_path)
        fps = float(source_probe.get("fps") or 0.0)
        if fps <= 0:
            raise RuntimeError("input video fps must be greater than zero")

        ffmpeg_command = [
            _ffmpeg_bin(),
            "-y",
            "-framerate",
            f"{fps:.6f}",
            "-i",
            str(frames_dir / "frame_%06d.png"),
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "1:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(target),
        ]
        result = _run(ffmpeg_command, log_path=log_path)
        if result.returncode != 0 or not target.exists():
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ffmpeg overlay encode failed")

    edited_probe = probe_video(target, ffprobe_json_path=edited_probe_json_path)
    if edited_probe.get("video_codec") != "h264":
        raise RuntimeError("edited video failed codec validation")
    if edited_probe.get("audio_codec") not in {"", "aac"}:
        raise RuntimeError("edited video failed audio codec validation")
    if edited_probe.get("pix_fmt") != "yuv420p":
        raise RuntimeError("edited video failed pixel format validation")
    if int(source_probe.get("width") or 0) != int(edited_probe.get("width") or 0):
        raise RuntimeError("edited video width mismatch")
    if int(source_probe.get("height") or 0) != int(edited_probe.get("height") or 0):
        raise RuntimeError("edited video height mismatch")
    if abs(float(source_probe.get("duration_seconds") or 0.0) - float(edited_probe.get("duration_seconds") or 0.0)) > 0.1:
        raise RuntimeError("edited video duration mismatch")
    _validate_decoding(target, log_path=log_path)

    coverage_ratio = (faces_covered / faces_expected) if faces_expected else 1.0
    coverage_payload = {
        "ok": coverage_ratio >= 0.99,
        "tracked_detections_path": str(tracked_path),
        "input_video_path": str(source),
        "output_video_path": str(target),
        "expected_faces": faces_expected,
        "covered_faces": faces_covered,
        "coverage_ratio": round(coverage_ratio, 6),
        "frames": frame_reports,
    }
    _write_json(coverage_path, coverage_payload)

    summary_payload = {
        "ok": True,
        "input_video_path": str(source),
        "tracked_detections_path": str(tracked_path),
        "stamp_path": str(stamp_file),
        "output_video_path": str(target),
        "output_summary_path": str(summary_path),
        "coverage_report_path": str(coverage_path),
        "processing_log_path": str(log_path),
        "frames_written": frames_written,
        "faces_expected": faces_expected,
        "faces_covered": faces_covered,
        "coverage_ratio": round(coverage_ratio, 6),
        "interpolated_faces": interpolated_faces,
        "scale": config.scale,
        "processing_seconds": round(time.perf_counter() - started_at, 6),
        "error_code": "",
        "message": "face overlay completed",
    }
    _write_json(summary_path, summary_payload)
    _append_log(
        log_path,
        "frames_written={frames_written}\nfaces_expected={faces_expected}\nfaces_covered={faces_covered}\ncoverage_ratio={coverage_ratio:.6f}\n".format(
            **summary_payload
        ),
    )
    logger.info("Face overlay completed for %s", source)
    return summary_payload
