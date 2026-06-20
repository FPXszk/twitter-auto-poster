from __future__ import annotations

import argparse
import json
import logging
import random
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from tool_paths import default_twitter_bin

LOGGER = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")
DEFAULT_TWITTER_BIN = default_twitter_bin()
DEFAULT_STATE_PATH = Path("config/follow_state.json")
DEFAULT_SUMMARY_OUTPUT = Path("tmp/auto_follow_summary.json")
JAPANESE_PATTERN = re.compile(r"[ぁ-んァ-ヶ一-龯々ー]")
STOCK_KEYWORDS = (
    "株",
    "投資",
    "トレード",
    "相場",
    "銘柄",
    "FX",
    "日経",
    "決算",
    "テクニカル",
    "ファンダメンタル",
    "IPO",
    "NISA",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-follow eligible followers from a target account.")
    parser.add_argument("--twitter-bin", type=Path, default=DEFAULT_TWITTER_BIN)
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--target-username", default="suzuka_saga")
    parser.add_argument("--followers-max", type=int, default=1000)
    parser.add_argument("--following-max", type=int, default=500)
    parser.add_argument("--recent-post-max", type=int, default=5)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(levelname)s] %(message)s",
    )


def current_jst_datetime() -> datetime:
    return datetime.now(JST)


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def run_twitter_json(twitter_bin: Path, *args: str) -> dict[str, object]:
    command = [str(twitter_bin), *args, "--json"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"command failed: {' '.join(command)}"
        raise RuntimeError(message)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"twitter-cli returned invalid JSON: {error}") from error
    if payload.get("ok") is not True:
        raise RuntimeError("twitter-cli response did not indicate success")
    return payload


def run_twitter_write(twitter_bin: Path, *args: str) -> None:
    command = [str(twitter_bin), *args]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"command failed: {' '.join(command)}"
        raise RuntimeError(message)


def load_follow_state(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"follow state must be a JSON list: {path}")
    entries: list[dict[str, object]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"follow state entry {index} must be an object")
        entries.append(dict(item))
    return entries


def save_follow_state(path: Path, entries: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_recorded_username_set(entries: Iterable[dict[str, object]]) -> set[str]:
    usernames: set[str] = set()
    for entry in entries:
        username = _normalize_text(entry.get("username")).lstrip("@").lower()
        if username:
            usernames.add(username)
    return usernames



def upsert_state_entry(entries: list[dict[str, object]], username: str, values: dict[str, object]) -> None:
    normalized_username = username.lstrip("@")
    for entry in entries:
        if _normalize_text(entry.get("username")).lstrip("@").lower() == normalized_username.lower():
            entry.update(values)
            entry["username"] = normalized_username
            return
    payload = {"username": normalized_username}
    payload.update(values)
    entries.append(payload)


def record_follow(
    entries: list[dict[str, object]],
    username: str,
    current_date: str,
    follow_type: str = "new_follow",
) -> None:
    upsert_state_entry(
        entries,
        username,
        {
            "followed_at": current_date,
            "unfollowed": False,
            "follow_type": follow_type,
        },
    )


def record_skip(entries: list[dict[str, object]], username: str, current_date: str, reason: str) -> None:
    upsert_state_entry(
        entries,
        username,
        {
            "skipped_at": current_date,
            "skip_reason": reason,
        },
    )


def extract_data_list(payload: dict[str, object]) -> list[dict[str, object]]:
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        users = data.get("users")
        if isinstance(users, list):
            return [item for item in users if isinstance(item, dict)]
        return [data]
    raise RuntimeError("twitter-cli response data was missing or not a list")


def extract_username(user: dict[str, object]) -> str:
    for key in ("username", "screenName", "screen_name", "handle"):
        username = _normalize_text(user.get(key)).lstrip("@")
        if username:
            return username
    return ""


def extract_profile_text(user: dict[str, object]) -> str:
    for key in ("description", "bio"):
        text = _normalize_text(user.get(key))
        if text:
            return text
    return ""


def extract_metric(user: dict[str, object], key: str) -> int:
    direct_value = user.get(key)
    if direct_value not in (None, ""):
        return _safe_int(direct_value)
    metrics = user.get("metrics")
    if isinstance(metrics, dict):
        return _safe_int(metrics.get(key))
    legacy_metrics = user.get("public_metrics")
    if isinstance(legacy_metrics, dict):
        return _safe_int(legacy_metrics.get(key))
    return 0


def is_verified_account(user: dict[str, object]) -> bool:
    return bool(user.get("verified") is True)


def has_japanese_text(text: str) -> bool:
    return bool(JAPANESE_PATTERN.search(text))


def contains_stock_keywords(text: str) -> bool:
    normalized = _normalize_text(text).lower()
    if not normalized:
        return False
    return any(keyword.lower() in normalized for keyword in STOCK_KEYWORDS)


def evaluate_candidate(
    user: dict[str, object],
    *,
    following_usernames: set[str],
    recorded_usernames: set[str],
) -> str | None:
    username = extract_username(user)
    if not username:
        return "missing_username"

    normalized_username = username.lower()
    if normalized_username in recorded_usernames:
        return "already_recorded"
    if normalized_username in following_usernames:
        return "already_following"
    if not is_verified_account(user):
        return "not_verified"
    return None



def has_japanese_signal(profile_text: str, recent_post_texts: list[str]) -> bool:
    if has_japanese_text(profile_text):
        return True
    return any(has_japanese_text(text) for text in recent_post_texts)


def matches_stock_keyword(user: dict[str, object], recent_post_texts: list[str]) -> bool:
    profile_text = extract_profile_text(user)
    if contains_stock_keywords(profile_text):
        return True
    return any(contains_stock_keywords(text) for text in recent_post_texts)


def fetch_authenticated_username(twitter_bin: Path) -> str:
    payload = run_twitter_json(twitter_bin, "whoami")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("twitter whoami returned unexpected data")
    user = data.get("user")
    if not isinstance(user, dict):
        raise RuntimeError("twitter whoami did not return a user object")
    username = extract_username(user)
    if not username:
        raise RuntimeError("twitter whoami did not return username")
    return username


def fetch_usernames(twitter_bin: Path, command: str, username: str, limit: int) -> set[str]:
    payload = run_twitter_json(twitter_bin, command, username, "--max", str(limit))
    usernames: set[str] = set()
    for item in extract_data_list(payload):
        handle = extract_username(item)
        if handle:
            usernames.add(handle.lower())
    return usernames


def fetch_recent_post_texts(twitter_bin: Path, username: str, max_posts: int) -> list[str]:
    payload = run_twitter_json(twitter_bin, "user-posts", username, "--max", str(max_posts))
    posts = extract_data_list(payload)
    return [_normalize_text(post.get("text")) for post in posts if _normalize_text(post.get("text"))]


def write_summary(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    now = current_jst_datetime()
    current_date = now.date().isoformat()
    target_follow_count = random.randint(10, 15)

    try:
        state_entries = load_follow_state(args.state_path)
        recorded_usernames = build_recorded_username_set(state_entries)
        auth_username = fetch_authenticated_username(args.twitter_bin)
        following_usernames = fetch_usernames(
            args.twitter_bin, "following", auth_username, args.following_max,
        )
        follower_payload = run_twitter_json(
            args.twitter_bin,
            "followers",
            args.target_username,
            "--max",
            str(args.followers_max),
        )
        follower_candidates = extract_data_list(follower_payload)
    except Exception as error:
        write_summary(
            args.summary_output,
            {
                "status": "failed",
                "run_at_jst": now.isoformat(),
                "error": str(error),
            },
        )
        LOGGER.error("%s", error)
        return 1

    skipped: list[dict[str, object]] = []
    scanned_followers = 0
    recent_post_lookups = 0
    followed_new: list[str] = []

    def _sleep_between_follows() -> None:
        if len(followed_new) < target_follow_count:
            sleep_seconds = random.randint(3, 8)
            LOGGER.info("sleeping %s seconds before next follow", sleep_seconds)
            time.sleep(sleep_seconds)

    # Phase 1: gather new follow candidates from target account's followers.
    new_follow_candidates: list[dict[str, object]] = []

    for candidate in follower_candidates:
        if len(new_follow_candidates) >= target_follow_count:
            break
        username = extract_username(candidate)
        if not username:
            continue
        scanned_followers += 1

        recent_post_texts: list[str] = []
        profile_text = extract_profile_text(candidate)
        reason = evaluate_candidate(
            candidate,
            following_usernames=following_usernames,
            recorded_usernames=recorded_usernames,
        )
        if reason is not None:
            if reason not in {"already_recorded", "already_following"}:
                record_skip(state_entries, username, current_date, reason)
                recorded_usernames.add(username.lower())
                skipped.append({"username": username, "reason": reason})
            continue

        if not has_japanese_text(profile_text) or not contains_stock_keywords(profile_text):
            try:
                recent_post_texts = fetch_recent_post_texts(
                    args.twitter_bin, username, args.recent_post_max,
                )
                recent_post_lookups += 1
            except Exception as error:
                reason = "recent_posts_error"
                LOGGER.warning("failed to inspect recent posts for @%s: %s", username, error)
                skipped.append({"username": username, "reason": reason})
                continue

        if not has_japanese_signal(profile_text, recent_post_texts):
            record_skip(state_entries, username, current_date, "no_japanese_signal")
            recorded_usernames.add(username.lower())
            skipped.append({"username": username, "reason": "no_japanese_signal"})
            continue

        if not matches_stock_keyword(candidate, recent_post_texts):
            record_skip(state_entries, username, current_date, "no_stock_keyword")
            recorded_usernames.add(username.lower())
            skipped.append({"username": username, "reason": "no_stock_keyword"})
            continue

        new_follow_candidates.append(
            {
                "username": username,
                "description": profile_text,
                "recent_post_texts": recent_post_texts,
            }
        )

    # Phase 2: execute new follows.
    for candidate in new_follow_candidates:
        if len(followed_new) >= target_follow_count:
            break
        username = str(candidate["username"])
        try:
            run_twitter_write(args.twitter_bin, "follow", username)
        except Exception as error:
            LOGGER.warning("failed to follow @%s: %s", username, error)
            skipped.append({"username": username, "reason": "follow_failed"})
            continue

        LOGGER.info("followed @%s", username)
        record_follow(state_entries, username, current_date, follow_type="new_follow")
        recorded_usernames.add(username.lower())
        followed_new.append(username)
        save_follow_state(args.state_path, state_entries)
        _sleep_between_follows()

    save_follow_state(args.state_path, state_entries)
    write_summary(
        args.summary_output,
        {
            "status": "ok",
            "run_at_jst": now.isoformat(),
            "auth_username": auth_username,
            "target_username": args.target_username,
            "requested_follow_count": target_follow_count,
            "follower_candidates": len(follower_candidates),
            "scanned_followers": scanned_followers,
            "scan_limit": args.followers_max,
            "recent_post_lookups": recent_post_lookups,
            "new_follow_candidates": len(new_follow_candidates),
            "followed_new_count": len(followed_new),
            "followed_new_usernames": followed_new,
            "followed_count": len(followed_new),
            "followed_usernames": list(followed_new),
            "skipped": skipped,
            "state_path": str(args.state_path),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
