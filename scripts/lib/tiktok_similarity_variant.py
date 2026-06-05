from __future__ import annotations

import json
import importlib.util
import logging
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import sys

NORMALIZER_PATH = Path(__file__).resolve().with_name("tiktok_video_normalizer.py")
normalizer_spec = importlib.util.spec_from_file_location("repo_tiktok_video_normalizer_for_similarity_variant", NORMALIZER_PATH)
if normalizer_spec is None or normalizer_spec.loader is None:
    raise RuntimeError(f"failed to load tiktok video normalizer helper from {NORMALIZER_PATH}")
normalizer_module = importlib.util.module_from_spec(normalizer_spec)
sys.modules[normalizer_spec.name] = normalizer_module
normalizer_spec.loader.exec_module(normalizer_module)

probe_video = normalizer_module.probe_video

logger = logging.getLogger(__name__)


@dataclass
class SimilarityVariantConfig:
    horizontal_flip: bool = True
    speed: float = 0.8
    brightness: float = -0.12
    contrast: float = 0.95
    saturation: float = 0.92
    mosaic_bottom_ratio: float = 0.15
    mosaic_block_size: int = 24
    crf: int = 18
    preset: str = "medium"


def _ffmpeg_bin() -> str:
    value = shutil.which("ffmpeg")
    if not value:
        raise RuntimeError("ffmpeg is required for TikTok similarity variant generation")
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


def _build_filter_complex(config: SimilarityVariantConfig) -> str:
    video_steps: list[str] = []
    if config.horizontal_flip:
        video_steps.append("hflip")
    video_steps.append(f"setpts={(1.0 / config.speed):.6f}*PTS")
    video_steps.append(
        "eq=brightness={brightness:.6f}:contrast={contrast:.6f}:saturation={saturation:.6f}".format(
            brightness=config.brightness,
            contrast=config.contrast,
            saturation=config.saturation,
        )
    )

    start_ratio = 1.0 - config.mosaic_bottom_ratio
    mosaic_block = int(config.mosaic_block_size)
    video_head = ",".join(video_steps)
    return (
        f"[0:v]{video_head},split=2[base][mosaic_src];"
        f"[mosaic_src]"
        f"crop=iw:ih*{config.mosaic_bottom_ratio:.6f}:0:ih*{start_ratio:.6f},"
        f"scale=w='max(1,trunc(iw/{mosaic_block}))':h='max(1,trunc(ih/{mosaic_block}))':flags=neighbor,"
        f"scale=w=iw*{mosaic_block}:h=ih*{mosaic_block}:flags=neighbor"
        f"[mosaic];"
        f"[base][mosaic]overlay=0:H-h[v]"
    )


def generate_similarity_variant(
    input_path: str | Path,
    output_path: str | Path,
    *,
    horizontal_flip: bool = True,
    speed: float = 0.8,
    brightness: float = -0.12,
    contrast: float = 0.95,
    saturation: float = 0.92,
    mosaic_bottom_ratio: float = 0.15,
    mosaic_block_size: int = 24,
    crf: int = 18,
    preset: str = "medium",
    audio_input: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    source = Path(input_path)
    target = Path(output_path)
    output_root = target.parent
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "variant-summary.json"
    log_path = output_root / "processing.log"
    source_probe_json_path = output_root / "variant.source.ffprobe.json"
    target_probe_json_path = output_root / "variant.ffprobe.json"
    audio_probe_json_path = output_root / "variant.audio.ffprobe.json"

    if not source.exists():
        raise FileNotFoundError(f"input video not found: {source}")
    if target.exists() and not force:
        raise FileExistsError(f"output already exists: {target}")
    if speed <= 0:
        raise ValueError("speed must be greater than zero")
    if not 0.0 < mosaic_bottom_ratio < 1.0:
        raise ValueError("mosaic_bottom_ratio must be greater than 0.0 and less than 1.0")
    if int(mosaic_block_size) < 2:
        raise ValueError("mosaic_block_size must be greater than or equal to 2")

    config = SimilarityVariantConfig(
        horizontal_flip=bool(horizontal_flip),
        speed=float(speed),
        brightness=float(brightness),
        contrast=float(contrast),
        saturation=float(saturation),
        mosaic_bottom_ratio=float(mosaic_bottom_ratio),
        mosaic_block_size=int(mosaic_block_size),
        crf=int(crf),
        preset=str(preset),
    )
    started_at = time.perf_counter()

    source_probe = probe_video(source, ffprobe_json_path=source_probe_json_path)
    if str(source_probe.get("video_codec") or "") == "":
        raise RuntimeError("input file does not contain a video stream")
    if float(source_probe.get("duration_seconds") or 0.0) <= 0.0:
        raise RuntimeError("input video duration must be greater than zero")

    has_source_audio = str(source_probe.get("audio_codec") or "").lower() != ""
    external_audio_path = Path(audio_input) if audio_input else None
    if external_audio_path is not None:
        if not external_audio_path.exists():
            raise FileNotFoundError(f"audio input not found: {external_audio_path}")
        audio_probe = probe_video(external_audio_path, ffprobe_json_path=audio_probe_json_path)
        if str(audio_probe.get("audio_codec") or "").lower() == "":
            raise RuntimeError("audio input does not contain an audio stream")
    else:
        audio_probe = {}

    filter_complex = _build_filter_complex(config)
    command = [
        _ffmpeg_bin(),
        "-y",
        "-i",
        str(source),
    ]
    if external_audio_path is not None:
        command.extend(["-stream_loop", "-1", "-i", str(external_audio_path)])
    command.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
        ]
    )
    if external_audio_path is not None:
        command.extend(["-map", "1:a:0"])
    else:
        command.extend(["-map", "0:a?"])
    if external_audio_path is None and has_source_audio:
        command.extend(["-filter:a", f"atempo={config.speed:.6f}"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            config.preset,
            "-crf",
            str(config.crf),
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
    )
    result = _run(command, log_path=log_path)
    if result.returncode != 0 or not target.exists():
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ffmpeg variant generation failed")

    target_probe = probe_video(target, ffprobe_json_path=target_probe_json_path)
    if "mp4" not in str(target_probe.get("container") or "").lower():
        raise RuntimeError("variant video failed container validation")
    if str(target_probe.get("video_codec") or "").lower() != "h264":
        raise RuntimeError("variant video failed codec validation")
    if str(target_probe.get("pix_fmt") or "").lower() != "yuv420p":
        raise RuntimeError("variant video failed pixel format validation")
    if external_audio_path is not None or has_source_audio:
        if str(target_probe.get("audio_codec") or "").lower() != "aac":
            raise RuntimeError("variant video failed audio codec validation")
    expected_duration = float(source_probe.get("duration_seconds") or 0.0) / config.speed
    actual_duration = float(target_probe.get("duration_seconds") or 0.0)
    duration_tolerance = max(0.25, expected_duration * 0.03)
    if abs(expected_duration - actual_duration) > duration_tolerance:
        raise RuntimeError("variant video duration mismatch")
    _validate_decoding(target, log_path=log_path)

    payload = {
        "ok": True,
        "input_video_path": str(source),
        "output_video_path": str(target),
        "summary_path": str(summary_path),
        "processing_log_path": str(log_path),
        "source_ffprobe_json_path": str(source_probe_json_path),
        "output_ffprobe_json_path": str(target_probe_json_path),
        "audio_ffprobe_json_path": str(audio_probe_json_path) if external_audio_path is not None else "",
        "used_external_audio": external_audio_path is not None,
        "audio_input_path": str(external_audio_path) if external_audio_path is not None else "",
        "source_audio_followed_speed": external_audio_path is None and has_source_audio,
        "expected_duration_seconds": round(expected_duration, 6),
        "actual_duration_seconds": round(actual_duration, 6),
        "processing_seconds": round(time.perf_counter() - started_at, 6),
        "config": asdict(config),
        "filter_complex": filter_complex,
        "message": "TikTok similarity variant generated",
        "error_code": "",
    }
    _write_json(summary_path, payload)
    _append_log(log_path, f"config={json.dumps(asdict(config), ensure_ascii=False)}\n")
    logger.info("Similarity variant generated for %s", source)
    return payload
