from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

POST_VIDEO_PATH = Path(__file__).resolve().with_name("post_video.py")
post_video_spec = importlib.util.spec_from_file_location("repo_post_video_helper_for_tiktok", POST_VIDEO_PATH)
if post_video_spec is None or post_video_spec.loader is None:
    raise RuntimeError(f"failed to load post video helper from {POST_VIDEO_PATH}")
post_video_module = importlib.util.module_from_spec(post_video_spec)
post_video_spec.loader.exec_module(post_video_module)

validate_video_path = post_video_module.validate_video_path

logger = logging.getLogger(__name__)

ALLOWED_TIKTOK_HOSTS = {"www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "tiktok.com"}
DEFAULT_MAX_SIZE_BYTES = 512 * 1024 * 1024
DEFAULT_STRATEGIES = (
    ("bestvideo*+bestaudio/best", "mp4"),
    ("best[ext=mp4]/best", None),
    ("best", None),
)
RETRYABLE_ERROR_MARKERS = (
    "timed out",
    "temporary failure",
    "429",
    "too many requests",
    "unable to download webpage",
)
MEDIA_SIDE_EXTENSIONS = {".json", ".part", ".ytdl"}


@dataclass
class TikTokDownloadJob:
    ok: bool
    input_url: str
    resolved_url: str
    video_id: str
    uploader: str
    title: str
    output_path: str
    container: str
    video_codec: str
    audio_codec: str
    width: int
    height: int
    fps: float
    duration_seconds: float
    size_bytes: int
    yt_dlp_version: str
    download_strategy: str
    metadata_path: str
    command_log_path: str
    info_json_path: str
    ffprobe_json_path: str
    result_path: str
    dry_run: bool
    reused_existing: bool
    stage: str = ""
    error_code: str = ""
    message: str = ""
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_tiktok_url(url: str) -> str:
    """Validate that the URL is a TikTok URL. Returns the cleaned URL."""
    value = str(url or "").strip()
    if not value:
        raise ValueError("empty URL is not a valid TikTok URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc not in ALLOWED_TIKTOK_HOSTS:
        raise ValueError(f"not a valid TikTok URL: {value}")
    return value


def _mask_command(command: list[str], secrets: list[str]) -> str:
    masked: list[str] = []
    for item in command:
        value = str(item)
        for secret in secrets:
            if secret:
                value = value.replace(secret, "***")
        masked.append(value)
    return " ".join(masked)


def _append_log(log_path: Path, content: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(content)


def _safe_id_from_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    compact = str(value or "").strip()
    if not compact:
        return 0
    try:
        return int(float(compact))
    except ValueError:
        return 0


def _coerce_float(value: Any) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    compact = str(value or "").strip()
    if not compact:
        return 0.0
    try:
        if "/" in compact:
            left, right = compact.split("/", 1)
            return float(left) / float(right)
        return float(compact)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _yt_dlp_version(ytdlp_bin: str) -> str:
    result = subprocess.run(
        [ytdlp_bin, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return str(result.stdout or "").strip()


def _ffmpeg_version() -> str:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return ""
    result = subprocess.run(
        [ffmpeg_bin, "-version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    first_line = str(result.stdout or "").splitlines()
    return first_line[0].strip() if first_line else ""


def _build_cookie_args(
    *,
    cookies_from_browser: str = "",
    cookies_file: str | Path | None = None,
) -> tuple[list[str], list[str]]:
    browser = str(cookies_from_browser or "").strip()
    file_path = str(cookies_file or "").strip()
    if browser and file_path:
        raise ValueError("cookies_from_browser and cookies_file are mutually exclusive")
    if browser:
        return ["--cookies-from-browser", browser], [browser]
    if file_path:
        return ["--cookies", file_path], [file_path]
    return [], []


def _run_command(
    command: list[str],
    *,
    log_path: Path,
    secrets: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    secret_values = secrets or []
    _append_log(log_path, f"$ {_mask_command(command, secret_values)}\n")
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.stdout:
        _append_log(log_path, f"[stdout]\n{result.stdout}\n")
    if result.stderr:
        _append_log(log_path, f"[stderr]\n{result.stderr}\n")
    _append_log(log_path, f"[exit_code] {result.returncode}\n\n")
    return result


def _normalize_to_mp4(
    input_path: Path,
    output_path: Path,
    *,
    log_path: Path,
) -> Path:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg is required to normalize non-MP4 TikTok downloads")

    command = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        str(output_path),
    ]
    result = _run_command(command, log_path=log_path)
    if result.returncode != 0 or not output_path.exists():
        error_text = result.stderr.strip() or result.stdout.strip() or "ffmpeg normalization failed"
        raise RuntimeError(error_text)
    return output_path


def _metadata_from_info(info: dict[str, Any], *, input_url: str) -> dict[str, Any]:
    resolved_url = str(
        info.get("webpage_url")
        or info.get("original_url")
        or info.get("url")
        or input_url
    ).strip()
    uploader = str(
        info.get("uploader")
        or info.get("uploader_id")
        or info.get("channel")
        or ""
    ).strip()
    title = str(info.get("title") or "").strip()
    video_id = str(info.get("id") or "").strip()
    if not video_id:
        video_id = _safe_id_from_url(resolved_url or input_url)
    return {
        "input_url": input_url,
        "resolved_url": resolved_url or input_url,
        "video_id": video_id,
        "uploader": uploader,
        "title": title,
        "extractor": str(info.get("extractor") or "").strip(),
        "ext": str(info.get("ext") or "").strip(),
        "format_id": str(info.get("format_id") or "").strip(),
        "format_note": str(info.get("format_note") or "").strip(),
        "ffmpeg_version": _ffmpeg_version(),
    }


def _ffprobe_details(video_path: Path, ffprobe_json_path: Path) -> dict[str, Any]:
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return {
            "container": video_path.suffix.lstrip(".").lower(),
            "video_codec": "",
            "audio_codec": "",
            "width": 0,
            "height": 0,
            "fps": 0.0,
            "duration_seconds": 0.0,
            "size_bytes": video_path.stat().st_size,
        }

    result = subprocess.run(
        [
            ffprobe_bin,
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
        return {
            "container": video_path.suffix.lstrip(".").lower(),
            "video_codec": "",
            "audio_codec": "",
            "width": 0,
            "height": 0,
            "fps": 0.0,
            "duration_seconds": 0.0,
            "size_bytes": video_path.stat().st_size,
        }

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "container": video_path.suffix.lstrip(".").lower(),
            "video_codec": "",
            "audio_codec": "",
            "width": 0,
            "height": 0,
            "fps": 0.0,
            "duration_seconds": 0.0,
            "size_bytes": video_path.stat().st_size,
        }

    _write_json(ffprobe_json_path, payload)

    streams = payload.get("streams") or []
    format_info = payload.get("format") or {}
    video_stream = next(
        (stream for stream in streams if str(stream.get("codec_type") or "") == "video"),
        {},
    )
    audio_stream = next(
        (stream for stream in streams if str(stream.get("codec_type") or "") == "audio"),
        {},
    )

    return {
        "container": str(format_info.get("format_name") or video_path.suffix.lstrip(".")).split(",", 1)[0],
        "video_codec": str(video_stream.get("codec_name") or "").strip(),
        "audio_codec": str(audio_stream.get("codec_name") or "").strip(),
        "width": _coerce_int(video_stream.get("width")),
        "height": _coerce_int(video_stream.get("height")),
        "fps": _coerce_float(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")),
        "duration_seconds": _coerce_float(format_info.get("duration")),
        "size_bytes": _coerce_int(format_info.get("size")) or video_path.stat().st_size,
    }


def _detect_error_code(message: str) -> tuple[str, bool]:
    compact = str(message or "").lower()
    if "login" in compact or "sign in" in compact:
        return "TIKTOK_LOGIN_REQUIRED", False
    if "not available" in compact or "private" in compact:
        return "TIKTOK_UNAVAILABLE", False
    if "404" in compact or "not found" in compact:
        return "TIKTOK_NOT_FOUND", False
    if any(marker in compact for marker in RETRYABLE_ERROR_MARKERS):
        return "TIKTOK_DOWNLOAD_RETRYABLE", True
    return "TIKTOK_DOWNLOAD_FAILED", False


def _build_result(
    *,
    ok: bool,
    input_url: str,
    resolved_url: str,
    video_id: str,
    uploader: str,
    title: str,
    output_path: Path | None,
    metadata_path: Path,
    command_log_path: Path,
    info_json_path: Path,
    ffprobe_json_path: Path,
    result_path: Path,
    yt_dlp_version: str,
    download_strategy: str,
    dry_run: bool,
    reused_existing: bool,
    message: str = "",
    stage: str = "",
    error_code: str = "",
    retryable: bool = False,
) -> TikTokDownloadJob:
    details = {
        "container": "",
        "video_codec": "",
        "audio_codec": "",
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "duration_seconds": 0.0,
        "size_bytes": 0,
    }
    if output_path and output_path.exists():
        details = _ffprobe_details(output_path, ffprobe_json_path)

    return TikTokDownloadJob(
        ok=ok,
        input_url=input_url,
        resolved_url=resolved_url,
        video_id=video_id,
        uploader=uploader,
        title=title,
        output_path=str(output_path) if output_path else "",
        container=str(details["container"]),
        video_codec=str(details["video_codec"]),
        audio_codec=str(details["audio_codec"]),
        width=int(details["width"]),
        height=int(details["height"]),
        fps=float(details["fps"]),
        duration_seconds=float(details["duration_seconds"]),
        size_bytes=int(details["size_bytes"]),
        yt_dlp_version=yt_dlp_version,
        download_strategy=download_strategy,
        metadata_path=str(metadata_path),
        command_log_path=str(command_log_path),
        info_json_path=str(info_json_path),
        ffprobe_json_path=str(ffprobe_json_path),
        result_path=str(result_path),
        dry_run=dry_run,
        reused_existing=reused_existing,
        stage=stage,
        error_code=error_code,
        message=message,
        retryable=retryable,
    )


def _load_existing_job(
    *,
    input_url: str,
    metadata: dict[str, Any],
    source_path: Path,
    metadata_path: Path,
    command_log_path: Path,
    info_json_path: Path,
    ffprobe_json_path: Path,
    result_path: Path,
    yt_dlp_version: str,
) -> TikTokDownloadJob:
    return _build_result(
        ok=True,
        input_url=input_url,
        resolved_url=str(metadata.get("resolved_url") or input_url),
        video_id=str(metadata.get("video_id") or _safe_id_from_url(input_url)),
        uploader=str(metadata.get("uploader") or ""),
        title=str(metadata.get("title") or ""),
        output_path=validate_video_path(source_path),
        metadata_path=metadata_path,
        command_log_path=command_log_path,
        info_json_path=info_json_path,
        ffprobe_json_path=ffprobe_json_path,
        result_path=result_path,
        yt_dlp_version=yt_dlp_version,
        download_strategy="reuse",
        dry_run=False,
        reused_existing=True,
        message="reused existing TikTok source video",
    )


def download_tiktok_video_job(
    video_url: str,
    output_dir: str | Path,
    *,
    max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES,
    cookies_from_browser: str = "",
    cookies_file: str | Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> TikTokDownloadJob:
    resolved_input_url = validate_tiktok_url(video_url)

    ytdlp_bin = shutil.which("yt-dlp")
    if not ytdlp_bin:
        raise RuntimeError("yt-dlp is required for TikTok downloads")

    yt_dlp_version = _yt_dlp_version(ytdlp_bin)
    cookie_args, secrets = _build_cookie_args(
        cookies_from_browser=cookies_from_browser,
        cookies_file=cookies_file,
    )

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="tiktok-info-", dir=output_root))
    preflight_log_path = temp_root / "preflight.log"

    info_command = [
        ytdlp_bin,
        "--no-progress",
        "--no-playlist",
        "--dump-single-json",
        "--skip-download",
        *cookie_args,
        resolved_input_url,
    ]
    info_result = _run_command(info_command, log_path=preflight_log_path, secrets=secrets)
    if info_result.returncode != 0:
        error_text = info_result.stderr.strip() or info_result.stdout.strip()
        code, retryable = _detect_error_code(error_text)
        shutil.rmtree(temp_root, ignore_errors=True)
        raise RuntimeError(f"{code}: {error_text}")

    try:
        raw_info = json.loads(info_result.stdout)
    except json.JSONDecodeError as error:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise RuntimeError(f"TIKTOK_METADATA_INVALID: {error}") from error

    metadata = _metadata_from_info(raw_info, input_url=resolved_input_url)
    job_dir = output_root / metadata["video_id"]
    job_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = job_dir / "metadata.json"
    command_log_path = job_dir / "download.log"
    info_json_path = job_dir / "source.info.json"
    ffprobe_json_path = job_dir / "ffprobe.json"
    result_path = job_dir / "result.json"
    source_path = job_dir / "source.mp4"

    if preflight_log_path.exists():
        shutil.move(str(preflight_log_path), str(command_log_path))
    shutil.rmtree(temp_root, ignore_errors=True)

    metadata["yt_dlp_version"] = yt_dlp_version
    metadata["cookies_from_browser"] = bool(cookies_from_browser)
    metadata["cookies_file"] = bool(cookies_file)
    _write_json(metadata_path, metadata)

    if source_path.exists() and not force and not dry_run:
        job = _load_existing_job(
            input_url=resolved_input_url,
            metadata=metadata,
            source_path=source_path,
            metadata_path=metadata_path,
            command_log_path=command_log_path,
            info_json_path=info_json_path,
            ffprobe_json_path=ffprobe_json_path,
            result_path=result_path,
            yt_dlp_version=yt_dlp_version,
        )
        _write_json(result_path, job.to_dict())
        return job

    if dry_run:
        job = _build_result(
            ok=True,
            input_url=resolved_input_url,
            resolved_url=str(metadata["resolved_url"]),
            video_id=str(metadata["video_id"]),
            uploader=str(metadata["uploader"]),
            title=str(metadata["title"]),
            output_path=None,
            metadata_path=metadata_path,
            command_log_path=command_log_path,
            info_json_path=info_json_path,
            ffprobe_json_path=ffprobe_json_path,
            result_path=result_path,
            yt_dlp_version=yt_dlp_version,
            download_strategy="metadata-only",
            dry_run=True,
            reused_existing=False,
            message="validated TikTok URL and fetched metadata",
        )
        _write_json(result_path, job.to_dict())
        return job

    attempt_errors: list[str] = []
    for index, (fmt, merge_output_format) in enumerate(DEFAULT_STRATEGIES, start=1):
        temp_dir = Path(tempfile.mkdtemp(prefix=f"tiktok-download-{index}-", dir=job_dir))
        output_template = str(temp_dir / "source.%(ext)s")
        command = [
            ytdlp_bin,
            "--no-progress",
            "--no-playlist",
            "--force-overwrites",
            "--write-info-json",
            "--print-json",
            "--format",
            fmt,
            "-o",
            output_template,
            *cookie_args,
        ]
        if merge_output_format:
            command.extend(["--merge-output-format", merge_output_format])
        command.append(resolved_input_url)

        result = _run_command(command, log_path=command_log_path, secrets=secrets)
        if result.returncode != 0:
            error_text = result.stderr.strip() or result.stdout.strip() or f"strategy-{index} failed"
            attempt_errors.append(f"strategy-{index}: {error_text}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            continue

        candidates = sorted(temp_dir.glob("source.*"))
        video_candidates = [
            path for path in candidates if path.suffix.lower() == ".mp4" and not path.name.endswith(".info.json")
        ]
        media_candidates = [
            path
            for path in candidates
            if path.is_file()
            and path.suffix.lower() not in MEDIA_SIDE_EXTENSIONS
            and not path.name.endswith(".info.json")
        ]
        info_candidates = [path for path in candidates if path.name.endswith(".info.json")]
        if not media_candidates:
            attempt_errors.append(f"strategy-{index}: yt-dlp did not produce a media file")
            shutil.rmtree(temp_dir, ignore_errors=True)
            continue

        selected_path = video_candidates[0] if video_candidates else media_candidates[0]
        if selected_path.suffix.lower() != ".mp4":
            normalized_path = temp_dir / "source.mp4"
            try:
                selected_path = _normalize_to_mp4(
                    selected_path,
                    normalized_path,
                    log_path=command_log_path,
                )
            except Exception as error:
                attempt_errors.append(f"strategy-{index}: {error}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                continue
            metadata["normalized_from_ext"] = media_candidates[0].suffix.lower()

        validated_path = validate_video_path(selected_path, max_size_bytes=max_size_bytes)
        shutil.move(str(validated_path), str(source_path))
        if info_candidates:
            shutil.move(str(info_candidates[0]), str(info_json_path))
        else:
            _write_json(info_json_path, raw_info)
        _write_json(metadata_path, metadata)
        shutil.rmtree(temp_dir, ignore_errors=True)

        job = _build_result(
            ok=True,
            input_url=resolved_input_url,
            resolved_url=str(metadata["resolved_url"]),
            video_id=str(metadata["video_id"]),
            uploader=str(metadata["uploader"]),
            title=str(metadata["title"]),
            output_path=source_path.resolve(),
            metadata_path=metadata_path,
            command_log_path=command_log_path,
            info_json_path=info_json_path,
            ffprobe_json_path=ffprobe_json_path,
            result_path=result_path,
            yt_dlp_version=yt_dlp_version,
            download_strategy=f"strategy-{index}",
            dry_run=False,
            reused_existing=False,
            message="downloaded TikTok video",
        )
        _write_json(result_path, job.to_dict())
        return job

    error_text = "; ".join(attempt_errors) if attempt_errors else "download failed"
    error_code, retryable = _detect_error_code(error_text)
    job = _build_result(
        ok=False,
        input_url=resolved_input_url,
        resolved_url=str(metadata["resolved_url"]),
        video_id=str(metadata["video_id"]),
        uploader=str(metadata["uploader"]),
        title=str(metadata["title"]),
        output_path=None,
        metadata_path=metadata_path,
        command_log_path=command_log_path,
        info_json_path=info_json_path,
        ffprobe_json_path=ffprobe_json_path,
        result_path=result_path,
        yt_dlp_version=yt_dlp_version,
        download_strategy="",
        dry_run=False,
        reused_existing=False,
        message=error_text,
        stage="download",
        error_code=error_code,
        retryable=retryable,
    )
    _write_json(result_path, job.to_dict())
    return job


def download_tiktok_video(
    video_url: str,
    output_dir: str | Path,
    *,
    max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES,
) -> Path:
    """Download a TikTok video using yt-dlp and validate the result."""
    job = download_tiktok_video_job(
        video_url,
        output_dir,
        max_size_bytes=max_size_bytes,
    )
    if not job.ok or not job.output_path:
        raise RuntimeError(job.message or "TikTok download failed")
    return Path(job.output_path)
