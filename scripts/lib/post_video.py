from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

SUMMARY_COMMON_PATH = Path(__file__).resolve().parents[2] / "python" / "summary_common.py"
summary_common_spec = importlib.util.spec_from_file_location("repo_summary_common", SUMMARY_COMMON_PATH)
if summary_common_spec is None or summary_common_spec.loader is None:
    raise RuntimeError(f"failed to load summary helper from {SUMMARY_COMMON_PATH}")
summary_common_module = importlib.util.module_from_spec(summary_common_spec)
sys.modules[summary_common_spec.name] = summary_common_module
summary_common_spec.loader.exec_module(summary_common_module)

TWIKIT_COMPAT_PATH = Path(__file__).resolve().with_name("twikit_compat.py")
twikit_compat_spec = importlib.util.spec_from_file_location("repo_twikit_compat", TWIKIT_COMPAT_PATH)
if twikit_compat_spec is None or twikit_compat_spec.loader is None:
    raise RuntimeError(f"failed to load twikit compat helper from {TWIKIT_COMPAT_PATH}")
twikit_compat_module = importlib.util.module_from_spec(twikit_compat_spec)
sys.modules[twikit_compat_spec.name] = twikit_compat_module
twikit_compat_spec.loader.exec_module(twikit_compat_module)

MAX_TWITTER_CLI_POST_LENGTH = summary_common_module.MAX_TWITTER_CLI_POST_LENGTH
estimate_x_weighted_length = summary_common_module.estimate_x_weighted_length
patch_twikit_transaction = twikit_compat_module.patch_twikit_transaction

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


async def _load_x_client_transaction_home_page(
    session: Any,
    headers: dict[str, str],
    *,
    handle_x_migration_async: Callable[[Any], Any],
) -> Any:
    session_headers = getattr(session, "headers", None)
    if session_headers is None or not hasattr(session_headers, "update"):
        return await handle_x_migration_async(session)

    original_headers = dict(session_headers)
    session_headers.update(headers)
    try:
        return await handle_x_migration_async(session)
    finally:
        if hasattr(session_headers, "clear"):
            session_headers.clear()
        session_headers.update(original_headers)


class _XClientTransactionAdapter:
    def __init__(
        self,
        *,
        transaction_cls: Callable[..., Any],
        get_ondemand_file_url: Callable[[Any], str],
        load_home_page: Callable[[Any, dict[str, str]], Any],
        client: Any = None,
        original_client_transaction: Any = None,
    ) -> None:
        self._transaction_cls = transaction_cls
        self._get_ondemand_file_url = get_ondemand_file_url
        self._load_home_page = load_home_page
        self._transaction: Any | None = None
        self.home_page_response: Any = None
        self._client: Any = client
        self._original_client_transaction: Any = original_client_transaction

    async def init(self, session: Any, headers: dict[str, str]) -> None:
        try:
            home_page_response = await self._load_home_page(session, headers)
            ondemand_file_url = self._get_ondemand_file_url(home_page_response)
            ondemand_file_response = await session.request(
                method="GET",
                url=ondemand_file_url,
                headers=headers,
            )
            ondemand_file_text = (
                ondemand_file_response.text
                if hasattr(ondemand_file_response, "text")
                else str(ondemand_file_response)
            )
            self._transaction = self._transaction_cls(
                home_page_response=home_page_response,
                ondemand_file_response=ondemand_file_text,
            )
            self.home_page_response = home_page_response
        except Exception as init_err:
            logger.warning(
                "x_client_transaction adapter init failed (%s), falling back to twikit_compat",
                init_err,
            )
            patch_twikit_transaction()
            if self._client is None or self._original_client_transaction is None:
                raise
            restored_client_transaction = self._original_client_transaction
            self._client.client_transaction = restored_client_transaction
            restored_init = getattr(restored_client_transaction, "init", None)
            if not callable(restored_init):
                raise RuntimeError(
                    "restored twikit client transaction does not support init()"
                ) from init_err
            await restored_init(session, headers)
            return

    def generate_transaction_id(
        self,
        method: str,
        path: str,
        response: Any = None,
        key: str | None = None,
        animation_key: str | None = None,
        time_now: int | None = None,
    ) -> str:
        if self._transaction is None:
            raise RuntimeError("x_client_transaction backend is not initialized")
        return self._transaction.generate_transaction_id(
            method=method,
            path=path,
            home_page_response=response or self.home_page_response,
            key=key,
            animation_key=animation_key,
            time_now=time_now,
        )


def configure_client_transaction_backend(
    client: Any,
    *,
    transaction_cls: Callable[..., Any] | None = None,
    get_ondemand_file_url: Callable[[Any], str] | None = None,
    load_home_page: Callable[[Any, dict[str, str]], Any] | None = None,
) -> str:
    if (
        transaction_cls is None
        or get_ondemand_file_url is None
        or load_home_page is None
    ):
        try:
            from x_client_transaction import ClientTransaction as xct_transaction_cls
            from x_client_transaction.utils import (
                get_ondemand_file_url as xct_get_ondemand_file_url,
                handle_x_migration_async,
            )
        except Exception as setup_err:
            logger.warning(
                "x_client_transaction setup failed (%s), falling back to twikit_compat",
                setup_err,
            )
            patch_twikit_transaction()
            return "twikit_compat"

        transaction_cls = transaction_cls or xct_transaction_cls
        get_ondemand_file_url = get_ondemand_file_url or xct_get_ondemand_file_url
        if load_home_page is None:
            async def default_load_home_page(session: Any, headers: dict[str, str]) -> Any:
                return await _load_x_client_transaction_home_page(
                    session,
                    headers,
                    handle_x_migration_async=handle_x_migration_async,
                )

            load_home_page = default_load_home_page

    original_client_transaction = getattr(client, "client_transaction", None)
    client.client_transaction = _XClientTransactionAdapter(
        transaction_cls=transaction_cls,
        get_ondemand_file_url=get_ondemand_file_url,
        load_home_page=load_home_page,
        client=client,
        original_client_transaction=original_client_transaction,
    )
    return "x_client_transaction"


def _default_client_factory() -> Any:
    try:
        from twikit import Client
    except ImportError as error:
        raise RuntimeError("twikit is required for video posting. Install twikit==2.3.3.") from error
    client = Client("en-US")
    configure_client_transaction_backend(client)
    return client


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
