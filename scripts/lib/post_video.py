from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

SUMMARY_COMMON_PATH = Path(__file__).resolve().parents[2] / "python" / "summary_common.py"
summary_common_spec = importlib.util.spec_from_file_location("repo_summary_common", SUMMARY_COMMON_PATH)
if summary_common_spec is None or summary_common_spec.loader is None:
    raise RuntimeError(f"failed to load summary helper from {SUMMARY_COMMON_PATH}")
summary_common_module = importlib.util.module_from_spec(summary_common_spec)
sys.modules[summary_common_spec.name] = summary_common_module
summary_common_spec.loader.exec_module(summary_common_module)

MAX_TWITTER_CLI_POST_LENGTH = summary_common_module.MAX_TWITTER_CLI_POST_LENGTH
estimate_x_weighted_length = summary_common_module.estimate_x_weighted_length

DEFAULT_MAX_VIDEO_BYTES = 512 * 1024 * 1024
DEFAULT_VIDEO_SUFFIX = ".mp4"
REJECTED_MP4_BRANDS = {
    b"qt  ",
    b"M4A ",
    b"M4B ",
    b"M4P ",
}
VIDEO_MARKERS = (b"moov", b"mdat")
VIDEO_TRACK_MARKER = b"vide"


def normalize_tweet_text(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        raise ValueError("tweet text must not be empty")
    weighted_length = estimate_x_weighted_length(normalized)
    if weighted_length > MAX_TWITTER_CLI_POST_LENGTH:
        raise ValueError(
            f"tweet text exceeds {MAX_TWITTER_CLI_POST_LENGTH} weighted chars ({weighted_length})"
        )
    return normalized


def _looks_like_mp4_video(path: Path) -> bool:
    with path.open("rb") as handle:
        sample = handle.read(65536)
    if len(sample) < 12:
        return False
    if sample[4:8] != b"ftyp" or sample[8:12] in REJECTED_MP4_BRANDS:
        return False
    if VIDEO_TRACK_MARKER in sample and any(marker in sample for marker in VIDEO_MARKERS):
        return True
    return path.stat().st_size > len(sample)


def _ffprobe_has_video_stream(path: Path) -> bool | None:
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return None
    result = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    return "video" in result.stdout.split()


def build_twikit_cookies(env: Mapping[str, str] | None = None) -> dict[str, str]:
    values = os.environ if env is None else env
    auth_token = str(values.get("TWITTER_AUTH_TOKEN") or "").strip()
    ct0 = str(values.get("TWITTER_CT0") or "").strip()
    missing: list[str] = []
    if not auth_token:
        missing.append("TWITTER_AUTH_TOKEN")
    if not ct0:
        missing.append("TWITTER_CT0")
    if missing:
        raise ValueError(f"missing required Twitter cookie environment variables: {', '.join(missing)}")
    return {
        "auth_token": auth_token,
        "ct0": ct0,
    }


def validate_video_path(video_path: str | Path, *, max_size_bytes: int = DEFAULT_MAX_VIDEO_BYTES) -> Path:
    path = Path(video_path).expanduser()
    if not path.exists():
        raise ValueError(f"video file not found: {path}")
    if not path.is_file():
        raise ValueError(f"video path is not a file: {path}")
    if path.suffix.lower() != DEFAULT_VIDEO_SUFFIX:
        raise ValueError("video file must be an MP4 (.mp4)")
    size_bytes = path.stat().st_size
    if size_bytes <= 0:
        raise ValueError("video file must not be empty")
    if size_bytes > max_size_bytes:
        max_mb = max_size_bytes // (1024 * 1024)
        actual_mb = size_bytes / (1024 * 1024)
        raise ValueError(
            f"video file size ({actual_mb:.1f} MB) exceeds limit ({max_mb} MB)"
        )
    ffprobe_has_video_stream = _ffprobe_has_video_stream(path)
    if ffprobe_has_video_stream is False:
        raise ValueError("video file does not contain a playable MP4 video stream")
    if ffprobe_has_video_stream is None and not _looks_like_mp4_video(path):
        raise ValueError("video file does not appear to be a valid MP4 video")
    return path.resolve()


def _tweet_id_from_result(tweet: Any) -> str:
    if isinstance(tweet, Mapping):
        for key in ("id", "rest_id", "tweet_id", "id_str"):
            value = str(tweet.get(key) or "").strip()
            if value:
                return value
        return ""

    for attribute in ("id", "rest_id", "tweet_id", "id_str"):
        value = str(getattr(tweet, attribute, "") or "").strip()
        if value:
            return value
    return ""


def build_post_video_success_payload(
    *,
    tweet_id: str,
    tweet_text: str,
    video_path: str | Path,
    dry_run: bool,
) -> dict[str, Any]:
    normalized_id = str(tweet_id or "").strip()
    ids = [normalized_id] if normalized_id else []
    action = "dry_run_video" if dry_run else "post_video"
    message = "dry-run validated video post" if dry_run else f"posted video tweet {normalized_id}"
    normalized_text = normalize_tweet_text(tweet_text)
    normalized_video_path = str(Path(video_path))
    return {
        "ok": True,
        "data": {
            "success": True,
            "action": action,
            "id": normalized_id,
            "url": f"https://x.com/i/status/{normalized_id}" if normalized_id else "",
            "tweet_ids": ids,
            "tweet_count": len(ids),
            "dry_run": dry_run,
            "text": normalized_text,
            "video_path": normalized_video_path,
            "media_type": "video",
        },
        "message": message,
    }


def build_post_video_failure_payload(
    *,
    message: str,
    tweet_text: str,
    video_path: str | Path,
    dry_run: bool,
) -> dict[str, Any]:
    normalized_text = str(tweet_text or "").strip()
    normalized_video_path = str(Path(video_path))
    action = "dry_run_video" if dry_run else "post_video"
    return {
        "ok": False,
        "data": {
            "success": False,
            "action": action,
            "id": "",
            "url": "",
            "tweet_ids": [],
            "tweet_count": 0,
            "dry_run": dry_run,
            "text": normalized_text,
            "video_path": normalized_video_path,
            "media_type": "video",
        },
        "message": str(message or "video post failed"),
    }


def write_post_video_result(output_path: str | Path, payload: Mapping[str, Any]) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _default_client_factory() -> Any:
    try:
        from twikit import Client
    except ImportError as error:
        raise RuntimeError("twikit is required for video posting. Install twikit==2.3.3.") from error
    from twikit_compat import patch_twikit_transaction
    patch_twikit_transaction()
    return Client("en-US")


async def post_video_tweet_async(
    *,
    tweet_text: str,
    video_path: str | Path,
    dry_run: bool,
    env: Mapping[str, str] | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    normalized_text = normalize_tweet_text(tweet_text)
    normalized_video_path = validate_video_path(video_path)
    if dry_run:
        return build_post_video_success_payload(
            tweet_id="",
            tweet_text=normalized_text,
            video_path=normalized_video_path,
            dry_run=True,
        )

    cookies = build_twikit_cookies(env)
    client = (client_factory or _default_client_factory)()
    http_client = getattr(client, "http", None)
    client.set_cookies(cookies, clear_cookies=True)

    try:
        media_id = await client.upload_media(str(normalized_video_path), wait_for_completion=True)
        tweet = await client.create_tweet(text=normalized_text, media_ids=[media_id])
    finally:
        close = getattr(http_client, "aclose", None)
        if callable(close):
            await close()

    tweet_id = _tweet_id_from_result(tweet)
    if not tweet_id:
        raise RuntimeError("twikit did not return a tweet id")

    return build_post_video_success_payload(
        tweet_id=tweet_id,
        tweet_text=normalized_text,
        video_path=normalized_video_path,
        dry_run=False,
    )


def post_video_tweet(
    *,
    tweet_text: str,
    video_path: str | Path,
    dry_run: bool,
    env: Mapping[str, str] | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        post_video_tweet_async(
            tweet_text=tweet_text,
            video_path=video_path,
            dry_run=dry_run,
            env=env,
            client_factory=client_factory,
        )
    )
