from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from post_feedback import load_feedback_history
from post_filters import parse_created_at

CommandRunner = Callable[[list[str]], Any]


def normalize_post_text(text: object) -> str:
    return " ".join(str(text or "").split())


def _default_command_runner(cmd: list[str]) -> Any:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _extract_username_from_whoami(payload: Mapping[str, Any]) -> str:
    data = payload.get("data") or {}
    user = data.get("user") or {}
    return str(
        user.get("screenName")
        or user.get("screen_name")
        or user.get("username")
        or data.get("screenName")
        or data.get("username")
        or ""
    ).strip()


def _load_recent_history_entries(
    feedback_history_path: str,
    *,
    lookback_days: int,
    now: datetime,
) -> list[dict[str, Any]]:
    entries = load_feedback_history(Path(feedback_history_path))
    cutoff = now - timedelta(days=max(lookback_days, 1))
    recent: list[dict[str, Any]] = []
    for entry in entries:
        posted_at = parse_created_at(str(entry.get("posted_at") or ""))
        if posted_at is None or posted_at < cutoff:
            continue
        normalized_text = normalize_post_text(
            entry.get("posted_text")
            or entry.get("normalized_post_text")
            or ""
        )
        if not normalized_text:
            continue
        recent.append(
            {
                "normalized_text": normalized_text,
                "source": "feedback_history",
                "tweet_id": str(entry.get("posted_tweet_id") or "").strip(),
                "created_at": posted_at.isoformat(),
            }
        )
    return recent


def _load_recent_self_post_entries(
    twitter_bin: str,
    *,
    lookback_days: int,
    max_posts: int,
    now: datetime,
    command_runner: CommandRunner | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    runner = command_runner or _default_command_runner
    whoami = runner([twitter_bin, "whoami", "--json"])
    if getattr(whoami, "returncode", 1) != 0:
        stderr = str(getattr(whoami, "stderr", "") or "").strip()
        return [], stderr or "twitter whoami failed"

    whoami_payload = json.loads(str(getattr(whoami, "stdout", "") or ""))
    if whoami_payload.get("ok") is not True:
        return [], "twitter whoami response was not ok"

    username = _extract_username_from_whoami(whoami_payload)
    if not username:
        return [], "twitter whoami did not return username"

    posts = runner([twitter_bin, "user-posts", username, "--max", str(max_posts), "--json"])
    if getattr(posts, "returncode", 1) != 0:
        stderr = str(getattr(posts, "stderr", "") or "").strip()
        return [], stderr or "twitter user-posts failed"

    posts_payload = json.loads(str(getattr(posts, "stdout", "") or ""))
    if posts_payload.get("ok") is not True:
        return [], "twitter user-posts response was not ok"

    cutoff = now - timedelta(days=max(lookback_days, 1))
    recent: list[dict[str, Any]] = []
    for item in posts_payload.get("data") or []:
        if not isinstance(item, Mapping):
            continue
        created_at = parse_created_at(str(item.get("createdAtISO") or item.get("createdAt") or ""))
        if created_at is None or created_at < cutoff:
            continue
        normalized_text = normalize_post_text(item.get("text") or "")
        if not normalized_text:
            continue
        recent.append(
            {
                "normalized_text": normalized_text,
                "source": "self_recent_posts",
                "tweet_id": str(item.get("id") or "").strip(),
                "created_at": created_at.isoformat(),
            }
        )
    return recent, None


def build_recent_duplicate_index(
    feedback_history_path: str,
    twitter_bin: str,
    *,
    lookback_days: int = 7,
    max_posts: int = 40,
    now: datetime | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    recent_entries = _load_recent_history_entries(
        feedback_history_path,
        lookback_days=lookback_days,
        now=current,
    )
    live_entries, live_error = _load_recent_self_post_entries(
        twitter_bin,
        lookback_days=lookback_days,
        max_posts=max_posts,
        now=current,
        command_runner=command_runner,
    )
    recent_entries.extend(live_entries)

    deduped: dict[str, dict[str, Any]] = {}
    for entry in recent_entries:
        key = str(entry.get("normalized_text") or "")
        if key and key not in deduped:
            deduped[key] = dict(entry)

    return {
        "lookback_days": lookback_days,
        "max_posts": max_posts,
        "entries": list(deduped.values()),
        "history_entry_count": sum(1 for entry in deduped.values() if entry.get("source") == "feedback_history"),
        "live_entry_count": sum(1 for entry in deduped.values() if entry.get("source") == "self_recent_posts"),
        "live_error": live_error,
    }


def find_duplicate_in_index(
    post_text: str,
    index: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_text = normalize_post_text(post_text)
    for entry in index.get("entries") or []:
        if not isinstance(entry, Mapping):
            continue
        if normalized_text and normalized_text == str(entry.get("normalized_text") or ""):
            return {
                "duplicate": True,
                "normalized_text": normalized_text,
                "source": str(entry.get("source") or ""),
                "tweet_id": str(entry.get("tweet_id") or ""),
                "created_at": str(entry.get("created_at") or ""),
            }
    return {"duplicate": False, "normalized_text": normalized_text}
