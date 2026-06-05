from __future__ import annotations

import importlib.util
import json
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

NORMALIZER_PATH = Path(__file__).resolve().with_name("tiktok_video_normalizer.py")
normalizer_spec = importlib.util.spec_from_file_location("repo_tiktok_video_normalizer_for_final_validator", NORMALIZER_PATH)
if normalizer_spec is None or normalizer_spec.loader is None:
    raise RuntimeError(f"failed to load tiktok video normalizer helper from {NORMALIZER_PATH}")
normalizer_module = importlib.util.module_from_spec(normalizer_spec)
sys.modules[normalizer_spec.name] = normalizer_module
normalizer_spec.loader.exec_module(normalizer_module)

probe_video = normalizer_module.probe_video

logger = logging.getLogger(__name__)


def _ffmpeg_bin() -> str:
    value = shutil.which("ffmpeg")
    if not value:
        raise RuntimeError("ffmpeg is required for TikTok final validation")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_log(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


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


def validate_final_video(
    reference_video_path: str | Path,
    candidate_video_path: str | Path,
    *,
    coverage_report_path: str | Path | None = None,
    overlay_summary_path: str | Path | None = None,
    preview_image_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    duration_tolerance_seconds: float = 0.1,
) -> dict[str, Any]:
    reference = Path(reference_video_path)
    candidate = Path(candidate_video_path)
    if not reference.exists():
        raise FileNotFoundError(f"reference video not found: {reference}")
    if not candidate.exists():
        raise FileNotFoundError(f"candidate video not found: {candidate}")

    validation_root = Path(output_dir) if output_dir else candidate.parent
    validation_root.mkdir(parents=True, exist_ok=True)
    result_path = validation_root / "validation_result.json"
    log_path = validation_root / "validation.log"
    reference_probe_json_path = validation_root / "validation.reference.ffprobe.json"
    candidate_probe_json_path = validation_root / "validation.candidate.ffprobe.json"

    started_at = time.perf_counter()
    warnings: list[str] = []
    reference_probe = probe_video(reference, ffprobe_json_path=reference_probe_json_path)
    candidate_probe = probe_video(candidate, ffprobe_json_path=candidate_probe_json_path)

    if candidate.stat().st_size <= 0:
        raise RuntimeError("candidate video is empty")
    if "mp4" not in str(candidate_probe.get("container") or "").lower():
        raise RuntimeError("candidate video failed container validation")
    if str(candidate_probe.get("video_codec") or "").lower() != "h264":
        raise RuntimeError("candidate video failed codec validation")
    if str(candidate_probe.get("pix_fmt") or "").lower() != "yuv420p":
        raise RuntimeError("candidate video failed pixel format validation")
    if str(candidate_probe.get("audio_codec") or "").lower() not in {"", "aac"}:
        raise RuntimeError("candidate video failed audio codec validation")

    for field in ("width", "height"):
        if int(reference_probe.get(field) or 0) != int(candidate_probe.get(field) or 0):
            raise RuntimeError(f"candidate video {field} mismatch")
    if abs(float(reference_probe.get("fps") or 0.0) - float(candidate_probe.get("fps") or 0.0)) > 0.01:
        raise RuntimeError("candidate video fps mismatch")
    if abs(float(reference_probe.get("duration_seconds") or 0.0) - float(candidate_probe.get("duration_seconds") or 0.0)) > float(
        duration_tolerance_seconds
    ):
        raise RuntimeError("candidate video duration mismatch")

    _validate_decoding(candidate, log_path=log_path)

    coverage_payload: dict[str, Any] = {}
    if coverage_report_path is not None:
        coverage_path = Path(coverage_report_path)
        if not coverage_path.exists():
            raise FileNotFoundError(f"coverage report not found: {coverage_path}")
        coverage_payload = json.loads(coverage_path.read_text(encoding="utf-8"))
        if not bool(coverage_payload.get("ok")):
            raise RuntimeError("face coverage report marked output as not ok")
        if float(coverage_payload.get("coverage_ratio") or 0.0) < 0.99:
            raise RuntimeError("face coverage ratio is below threshold")

    overlay_payload: dict[str, Any] = {}
    if overlay_summary_path is not None:
        overlay_path = Path(overlay_summary_path)
        if not overlay_path.exists():
            raise FileNotFoundError(f"overlay summary not found: {overlay_path}")
        overlay_payload = json.loads(overlay_path.read_text(encoding="utf-8"))
        if int(overlay_payload.get("interpolated_faces") or 0) > 0:
            warnings.append("interpolated faces present in overlay summary")

    if preview_image_path is not None:
        preview_path = Path(preview_image_path)
        if not preview_path.exists():
            raise FileNotFoundError(f"preview image not found: {preview_path}")

    payload = {
        "ok": True,
        "reference_video_path": str(reference),
        "candidate_video_path": str(candidate),
        "coverage_report_path": str(coverage_report_path or ""),
        "overlay_summary_path": str(overlay_summary_path or ""),
        "preview_image_path": str(preview_image_path or ""),
        "validation_log_path": str(log_path),
        "reference_ffprobe_json_path": str(reference_probe_json_path),
        "candidate_ffprobe_json_path": str(candidate_probe_json_path),
        "candidate": candidate_probe,
        "reference": reference_probe,
        "coverage_ratio": float(coverage_payload.get("coverage_ratio") or 0.0) if coverage_payload else 0.0,
        "warnings": warnings,
        "processing_seconds": round(time.perf_counter() - started_at, 6),
        "message": "final video validation completed",
        "error_code": "",
    }
    _write_json(result_path, payload)
    logger.info("Final video validation completed for %s", candidate)
    return payload
