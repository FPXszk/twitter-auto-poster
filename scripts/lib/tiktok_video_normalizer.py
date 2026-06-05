from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_log(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _coerce_float(value: Any) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        if "/" in text:
            left, right = text.split("/", 1)
            return float(left) / float(right)
        return float(text)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ffmpeg_bin() -> str:
    value = shutil.which("ffmpeg")
    if not value:
        raise RuntimeError("ffmpeg is required for TikTok video normalization")
    return value


def _ffprobe_bin() -> str:
    value = shutil.which("ffprobe")
    if not value:
        raise RuntimeError("ffprobe is required for TikTok video normalization")
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


def probe_video(path: str | Path, *, ffprobe_json_path: str | Path) -> dict[str, Any]:
    video_path = Path(path)
    result = subprocess.run(
        [
            _ffprobe_bin(),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not str(result.stdout or "").strip():
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")

    payload = json.loads(result.stdout)
    _write_json(Path(ffprobe_json_path), payload)

    streams = payload.get("streams") or []
    format_info = payload.get("format") or {}
    video_stream = next((item for item in streams if str(item.get("codec_type")) == "video"), {})
    audio_stream = next((item for item in streams if str(item.get("codec_type")) == "audio"), {})

    return {
        "container": str(format_info.get("format_name") or ""),
        "video_codec": str(video_stream.get("codec_name") or "").strip().lower(),
        "audio_codec": str(audio_stream.get("codec_name") or "").strip().lower(),
        "pix_fmt": str(video_stream.get("pix_fmt") or "").strip().lower(),
        "width": _coerce_int(video_stream.get("width")),
        "height": _coerce_int(video_stream.get("height")),
        "fps": _coerce_float(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")),
        "duration_seconds": _coerce_float(format_info.get("duration")),
        "size_bytes": _coerce_int(format_info.get("size")) or video_path.stat().st_size,
    }


def is_normalized_video(metadata: Mapping[str, Any]) -> bool:
    container = str(metadata.get("container") or "").lower()
    video_codec = str(metadata.get("video_codec") or "").lower()
    audio_codec = str(metadata.get("audio_codec") or "").lower()
    pix_fmt = str(metadata.get("pix_fmt") or "").lower()
    return (
        "mp4" in container
        and video_codec == "h264"
        and pix_fmt == "yuv420p"
        and (audio_codec in {"", "aac"})
    )


def normalize_video(
    source_path: str | Path,
    normalized_path: str | Path,
    *,
    log_path: str | Path,
) -> Path:
    source = Path(source_path)
    target = Path(normalized_path)
    tmp_path = target.with_name(f"{target.stem}.tmp{target.suffix}")
    if tmp_path.exists():
        tmp_path.unlink()

    result = _run(
        [
            _ffmpeg_bin(),
            "-y",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
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
            str(tmp_path),
        ],
        log_path=Path(log_path),
    )
    if result.returncode != 0 or not tmp_path.exists():
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ffmpeg normalization failed")
    tmp_path.replace(target)
    return target


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


def ensure_normalized_video(
    source_path: str | Path,
    normalized_path: str | Path,
    *,
    source_ffprobe_json_path: str | Path,
    normalized_ffprobe_json_path: str | Path,
    log_path: str | Path,
) -> dict[str, Any]:
    source = Path(source_path)
    normalized = Path(normalized_path)
    log_file = Path(log_path)
    started_at = time.perf_counter()

    source_probe = probe_video(source, ffprobe_json_path=source_ffprobe_json_path)
    source_sha256 = _sha256(source)

    normalization_applied = False
    normalization_reason = "already-normalized"
    if normalized.exists():
        normalized_probe = probe_video(normalized, ffprobe_json_path=normalized_ffprobe_json_path)
        if is_normalized_video(normalized_probe) and normalized.stat().st_mtime >= source.stat().st_mtime:
            _validate_decoding(normalized, log_path=log_file)
            return {
                "source_path": str(source),
                "normalized_path": str(normalized),
                "source_sha256": source_sha256,
                "source_ffprobe_json_path": str(source_ffprobe_json_path),
                "normalized_ffprobe_json_path": str(normalized_ffprobe_json_path),
                "normalize_log_path": str(log_file),
                "normalization_applied": False,
                "normalization_reason": "reused-existing",
                "processing_seconds": time.perf_counter() - started_at,
                **{f"source_{key}": value for key, value in source_probe.items()},
                **{f"normalized_{key}": value for key, value in normalized_probe.items()},
            }

    if is_normalized_video(source_probe):
        tmp_path = normalized.with_name(f"{normalized.stem}.tmp{normalized.suffix}")
        if tmp_path.exists():
            tmp_path.unlink()
        shutil.copy2(source, tmp_path)
        tmp_path.replace(normalized)
        normalization_reason = "copied-normalized-source"
    else:
        normalize_video(source, normalized, log_path=log_file)
        normalization_applied = True
        normalization_reason = "re-encoded"

    normalized_probe = probe_video(normalized, ffprobe_json_path=normalized_ffprobe_json_path)
    if not is_normalized_video(normalized_probe):
        raise RuntimeError("normalized video failed codec validation")
    if abs(source_probe["duration_seconds"] - normalized_probe["duration_seconds"]) > 0.1:
        raise RuntimeError("normalized video duration mismatch")
    if source_probe["width"] != normalized_probe["width"] or source_probe["height"] != normalized_probe["height"]:
        raise RuntimeError("normalized video dimension mismatch")

    _validate_decoding(normalized, log_path=log_file)

    return {
        "source_path": str(source),
        "normalized_path": str(normalized),
        "source_sha256": source_sha256,
        "source_ffprobe_json_path": str(source_ffprobe_json_path),
        "normalized_ffprobe_json_path": str(normalized_ffprobe_json_path),
        "normalize_log_path": str(log_file),
        "normalization_applied": normalization_applied,
        "normalization_reason": normalization_reason,
        "processing_seconds": time.perf_counter() - started_at,
        **{f"source_{key}": value for key, value in source_probe.items()},
        **{f"normalized_{key}": value for key, value in normalized_probe.items()},
    }
