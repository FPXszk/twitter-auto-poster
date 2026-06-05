from __future__ import annotations

import importlib.util
import json
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DOWNLOADER_PATH = Path(__file__).resolve().with_name("tiktok_downloader.py")
downloader_spec = importlib.util.spec_from_file_location("repo_tiktok_downloader_for_reference_audio", DOWNLOADER_PATH)
if downloader_spec is None or downloader_spec.loader is None:
    raise RuntimeError(f"failed to load tiktok downloader helper from {DOWNLOADER_PATH}")
downloader_module = importlib.util.module_from_spec(downloader_spec)
sys.modules[downloader_spec.name] = downloader_module
downloader_spec.loader.exec_module(downloader_module)

download_tiktok_video_job = downloader_module.download_tiktok_video_job

NORMALIZER_PATH = Path(__file__).resolve().with_name("tiktok_video_normalizer.py")
normalizer_spec = importlib.util.spec_from_file_location("repo_tiktok_video_normalizer_for_reference_audio", NORMALIZER_PATH)
if normalizer_spec is None or normalizer_spec.loader is None:
    raise RuntimeError(f"failed to load tiktok video normalizer helper from {NORMALIZER_PATH}")
normalizer_module = importlib.util.module_from_spec(normalizer_spec)
sys.modules[normalizer_spec.name] = normalizer_module
normalizer_spec.loader.exec_module(normalizer_module)

probe_video = normalizer_module.probe_video

logger = logging.getLogger(__name__)


@dataclass
class TikTokReferenceAudioJob:
    ok: bool
    input_url: str
    resolved_url: str
    video_id: str
    output_dir: str
    source_video_path: str
    audio_path: str
    audio_ffprobe_json_path: str
    processing_log_path: str
    summary_path: str
    audio_codec: str
    duration_seconds: float
    size_bytes: int
    download_result_path: str
    error_code: str = ""
    message: str = ""
    reused_existing: bool = False
    processing_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ffmpeg_bin() -> str:
    value = shutil.which("ffmpeg")
    if not value:
        raise RuntimeError("ffmpeg is required for TikTok reference audio extraction")
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


def extract_reference_audio_from_tiktok(
    video_url: str,
    output_root: str | Path,
    *,
    cookies_from_browser: str = "",
    cookies_file: str | Path | None = None,
    force: bool = False,
) -> TikTokReferenceAudioJob:
    output_dir = Path(output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.perf_counter()

    download_job = download_tiktok_video_job(
        video_url,
        output_dir,
        cookies_from_browser=cookies_from_browser,
        cookies_file=cookies_file,
        dry_run=False,
        force=force,
    )
    if not download_job.ok:
        raise RuntimeError(download_job.message or "TikTok video download failed for reference audio extraction")

    video_dir = Path(download_job.output_path).parent
    audio_path = video_dir / "reference_audio.m4a"
    audio_ffprobe_json_path = video_dir / "reference_audio.ffprobe.json"
    log_path = video_dir / "reference_audio.log"
    summary_path = video_dir / "reference_audio.json"

    if audio_path.exists() and not force:
        audio_probe = probe_video(audio_path, ffprobe_json_path=audio_ffprobe_json_path)
        if str(audio_probe.get("audio_codec") or "").lower() == "aac":
            _validate_decoding(audio_path, log_path=log_path)
            payload = TikTokReferenceAudioJob(
                ok=True,
                input_url=download_job.input_url,
                resolved_url=download_job.resolved_url,
                video_id=download_job.video_id,
                output_dir=str(video_dir),
                source_video_path=str(download_job.output_path),
                audio_path=str(audio_path),
                audio_ffprobe_json_path=str(audio_ffprobe_json_path),
                processing_log_path=str(log_path),
                summary_path=str(summary_path),
                audio_codec=str(audio_probe.get("audio_codec") or ""),
                duration_seconds=float(audio_probe.get("duration_seconds") or 0.0),
                size_bytes=int(audio_probe.get("size_bytes") or 0),
                download_result_path=str(download_job.result_path),
                reused_existing=True,
                processing_seconds=round(time.perf_counter() - started_at, 6),
                message="reused existing TikTok reference audio",
            )
            _write_json(summary_path, payload.to_dict())
            return payload

    source_video_path = Path(download_job.output_path)
    source_probe = probe_video(
        source_video_path,
        ffprobe_json_path=video_dir / "reference_audio.source.ffprobe.json",
    )
    if str(source_probe.get("audio_codec") or "").lower() == "":
        raise RuntimeError("downloaded TikTok video does not contain an audio stream")

    command = [
        _ffmpeg_bin(),
        "-y",
        "-i",
        str(source_video_path),
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(audio_path),
    ]
    result = _run(command, log_path=log_path)
    if result.returncode != 0 or not audio_path.exists():
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ffmpeg audio extraction failed")

    audio_probe = probe_video(audio_path, ffprobe_json_path=audio_ffprobe_json_path)
    if str(audio_probe.get("audio_codec") or "").lower() != "aac":
        raise RuntimeError("reference audio failed codec validation")
    _validate_decoding(audio_path, log_path=log_path)

    payload = TikTokReferenceAudioJob(
        ok=True,
        input_url=download_job.input_url,
        resolved_url=download_job.resolved_url,
        video_id=download_job.video_id,
        output_dir=str(video_dir),
        source_video_path=str(source_video_path),
        audio_path=str(audio_path),
        audio_ffprobe_json_path=str(audio_ffprobe_json_path),
        processing_log_path=str(log_path),
        summary_path=str(summary_path),
        audio_codec=str(audio_probe.get("audio_codec") or ""),
        duration_seconds=float(audio_probe.get("duration_seconds") or 0.0),
        size_bytes=int(audio_probe.get("size_bytes") or 0),
        download_result_path=str(download_job.result_path),
        processing_seconds=round(time.perf_counter() - started_at, 6),
        message="TikTok reference audio extracted",
    )
    _write_json(summary_path, payload.to_dict())
    logger.info("Reference audio extracted for %s", source_video_path)
    return payload
