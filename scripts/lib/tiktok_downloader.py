from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from post_video import validate_video_path

logger = logging.getLogger(__name__)

ALLOWED_TIKTOK_HOSTS = {"www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "tiktok.com"}


def validate_tiktok_url(url: str) -> str:
    """Validate that the URL is a TikTok URL. Returns the cleaned URL."""
    value = str(url or "").strip()
    if not value:
        raise ValueError("empty URL is not a valid TikTok URL")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.netloc not in ALLOWED_TIKTOK_HOSTS:
        raise ValueError(f"not a valid TikTok URL: {value}")
    return value


def download_tiktok_video(
    video_url: str,
    output_dir: str | Path,
    *,
    max_size_bytes: int = 512 * 1024 * 1024,
) -> Path:
    """Download a TikTok video using yt-dlp and validate the result."""
    resolved_url = validate_tiktok_url(video_url)

    ytdlp_bin = shutil.which("yt-dlp")
    if not ytdlp_bin:
        raise RuntimeError("yt-dlp is required for TikTok downloads")

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="tiktok-", dir=output_root))
    template = str(temp_dir / "video.%(ext)s")

    command = [
        ytdlp_bin,
        "--no-progress",
        "--no-playlist",
        "--force-overwrites",
        "-o",
        template,
        resolved_url,
    ]

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"yt-dlp failed: {result.stderr.strip() or result.stdout.strip()}")

    downloaded_files = sorted(temp_dir.glob("*.mp4"))
    if not downloaded_files:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError("yt-dlp did not produce an MP4 file")

    try:
        return validate_video_path(downloaded_files[0], max_size_bytes=max_size_bytes)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
