from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

from account_score import current_jst_datetime
from auto_follow import (
    DEFAULT_TWITTER_BIN,
    configure_logging,
    run_twitter_json,
    run_twitter_write,
    write_summary,
)
from summary_common import ensure_state_file, extract_tweet_id

LOGGER = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")
DEFAULT_STATE_PATH = Path("tmp/state/liked_ids.txt")
DEFAULT_SUMMARY_OUTPUT = Path("tmp/auto_like_summary.json")
DEFAULT_FEED_MAX = 50
DEFAULT_TARGET_POST_MAX = 5
STATE_RETENTION_DAYS = 7
PRIMARY_WINDOW_MINUTES = 30
EXPANDED_WINDOW_MINUTES = 60
MIN_PRIMARY_WINDOW_TWEETS = 5
DAILY_LIKE_LIMIT = 100
MIN_LIKE_SLEEP_SECONDS = 2
MAX_LIKE_SLEEP_SECONDS = 8
MAX_EXCLUDED_FEED_CANDIDATE_LIKES = 300
RECENCY_BUCKET_MINUTES = 10


@dataclass(frozen=True)
class LikedStateEntry:
    liked_at: datetime
    tweet_id: str


@dataclass(frozen=True)
class TweetCandidate:
    tweet_id: str
    text: str
    created_at: datetime
    username: str = ""
    like_count: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automatically like recent tweets from the for-you timeline.")
    parser.add_argument("--twitter-bin", type=Path, default=DEFAULT_TWITTER_BIN)
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--feed-max", type=int, default=DEFAULT_FEED_MAX)
    parser.add_argument("--target-post-max", type=int, default=DEFAULT_TARGET_POST_MAX)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target-accounts", nargs="+", default=[])
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _safe_int(value: object) -> int:
    try:
        return max(int(str(value).strip()), 0)
    except (TypeError, ValueError):
        return 0


def parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(normalized).astimezone(JST)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text).astimezone(JST)
    except (TypeError, ValueError):
        return None


def _extract_username(node: object) -> str:
    if not isinstance(node, dict):
        return ""
    for key in ("username", "screenName", "screen_name", "handle"):
        value = _normalize_text(node.get(key)).lstrip("@")
        if value:
            return value
    for child_key in ("user", "author", "creator", "core", "legacy"):
        child = node.get(child_key)
        username = _extract_username(child)
        if username:
            return username
    return ""


def _collect_tweet_objects(node: object, collected: list[dict[str, object]]) -> None:
    if isinstance(node, list):
        for item in node:
            _collect_tweet_objects(item, collected)
        return
    if not isinstance(node, dict):
        return

    tweet_id = extract_tweet_id(node)
    has_time = any(node.get(key) for key in ("createdAtISO", "createdAt", "time"))
    has_text = "text" in node
    if tweet_id and (has_time or has_text):
        collected.append(node)
        return

    for value in node.values():
        _collect_tweet_objects(value, collected)


def _extract_first_int(node: dict[str, object], paths: Sequence[tuple[str, ...]]) -> int:
    for path in paths:
        current: object = node
        for segment in path:
            if not isinstance(current, dict) or segment not in current:
                break
            current = current[segment]
        else:
            return _safe_int(current)
    return 0


def extract_like_count(node: dict[str, object]) -> int:
    return _extract_first_int(
        node,
        (
            ("metrics", "likes"),
            ("metrics", "like_count"),
            ("public_metrics", "like_count"),
            ("likes",),
            ("like_count",),
            ("legacy", "favorite_count"),
            ("legacy", "favourite_count"),
            ("favorite_count",),
            ("favourite_count",),
        ),
    )


def extract_tweet_candidates(payload: dict[str, object]) -> list[TweetCandidate]:
    raw_candidates: list[dict[str, object]] = []
    _collect_tweet_objects(payload.get("data") or payload, raw_candidates)

    candidates: list[TweetCandidate] = []
    seen_ids: set[str] = set()
    for item in raw_candidates:
        tweet_id = extract_tweet_id(item)
        if not tweet_id or tweet_id in seen_ids:
            continue
        created_at = parse_datetime(item.get("createdAtISO") or item.get("createdAt") or item.get("time"))
        if created_at is None:
            continue
        candidates.append(
            TweetCandidate(
                tweet_id=tweet_id,
                text=_normalize_text(item.get("text")),
                created_at=created_at,
                username=_extract_username(item),
                like_count=extract_like_count(item),
            )
        )
        seen_ids.add(tweet_id)
    return candidates


def select_timeline_candidates(
    candidates: Sequence[TweetCandidate],
    *,
    now: datetime,
) -> tuple[list[TweetCandidate], int]:
    sorted_candidates = sorted(candidates, key=lambda item: item.created_at, reverse=True)

    def within_window(window_minutes: int) -> list[TweetCandidate]:
        window = timedelta(minutes=window_minutes)
        return [
            candidate
            for candidate in sorted_candidates
            if timedelta(0) <= now - candidate.created_at <= window
        ]

    primary_candidates = within_window(PRIMARY_WINDOW_MINUTES)
    if len(primary_candidates) >= MIN_PRIMARY_WINDOW_TWEETS:
        return primary_candidates, PRIMARY_WINDOW_MINUTES
    return within_window(EXPANDED_WINDOW_MINUTES), EXPANDED_WINDOW_MINUTES


def pick_latest_account_candidates(
    account_candidates: dict[str, Sequence[TweetCandidate]],
) -> list[TweetCandidate]:
    latest_candidates: list[TweetCandidate] = []
    for username, candidates in account_candidates.items():
        sorted_candidates = sorted(candidates, key=lambda item: item.created_at, reverse=True)
        if not sorted_candidates:
            LOGGER.warning("no posts found for @%s", username)
            continue
        latest_candidates.append(sorted_candidates[0])
    return latest_candidates


def _candidate_recency_bucket(candidate: TweetCandidate, *, now: datetime) -> int:
    age_seconds = max((now - candidate.created_at).total_seconds(), 0)
    return int(age_seconds // (RECENCY_BUCKET_MINUTES * 60))


def prioritize_feed_candidates(
    candidates: Sequence[TweetCandidate],
    *,
    now: datetime,
) -> list[TweetCandidate]:
    eligible_candidates = [candidate for candidate in candidates if candidate.like_count < MAX_EXCLUDED_FEED_CANDIDATE_LIKES]
    return sorted(
        eligible_candidates,
        key=lambda item: (
            _candidate_recency_bucket(item, now=now),
            item.like_count,
            -item.created_at.timestamp(),
            item.tweet_id,
        ),
    )


def parse_state_line(line: str) -> LikedStateEntry:
    parts = line.rstrip("\n").split("\t", 1)
    if len(parts) != 2:
        raise ValueError("expected <timestamp>\\t<tweet_id> format")
    liked_at = parse_datetime(parts[0])
    if liked_at is None:
        raise ValueError("timestamp could not be parsed")
    tweet_id = parts[1].strip()
    if not tweet_id:
        raise ValueError("tweet_id is empty")
    return LikedStateEntry(liked_at=liked_at, tweet_id=tweet_id)


def load_liked_state(path: Path) -> list[LikedStateEntry]:
    entries: list[LikedStateEntry] = []
    for line_number, line in enumerate(ensure_state_file(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entries.append(parse_state_line(line))
        except ValueError as error:
            LOGGER.warning("skipping malformed like state line %s in %s: %s", line_number, path, error)
    return entries


def prune_liked_state(entries: Iterable[LikedStateEntry], *, now: datetime) -> list[LikedStateEntry]:
    cutoff = now - timedelta(days=STATE_RETENTION_DAYS)
    return sorted(
        [entry for entry in entries if entry.liked_at >= cutoff],
        key=lambda item: item.liked_at,
    )


def save_liked_state(path: Path, entries: Sequence[LikedStateEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{entry.liked_at.isoformat()}\t{entry.tweet_id}" for entry in sorted(entries, key=lambda item: item.liked_at)]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def build_liked_id_set(entries: Iterable[LikedStateEntry]) -> set[str]:
    return {entry.tweet_id for entry in entries}


def count_daily_likes(entries: Iterable[LikedStateEntry], target_date: date) -> int:
    return sum(1 for entry in entries if entry.liked_at.astimezone(JST).date() == target_date)


def determine_like_count(requested_count: int, remaining_daily_capacity: int, candidate_count: int) -> int:
    return max(min(requested_count, remaining_daily_capacity, candidate_count), 0)


def candidate_preview(candidate: TweetCandidate) -> dict[str, object]:
    return {
        "tweet_id": candidate.tweet_id,
        "username": candidate.username,
        "created_at": candidate.created_at.isoformat(),
        "like_count": candidate.like_count,
        "text_snippet": candidate.text[:140] + ("…" if len(candidate.text) > 140 else ""),
    }


def fetch_feed_candidates(twitter_bin: Path, max_results: int) -> list[TweetCandidate]:
    payload = run_twitter_json(twitter_bin, "feed", "--max", str(max_results))
    return extract_tweet_candidates(payload)


def fetch_target_account_candidates(
    twitter_bin: Path,
    target_accounts: Sequence[str],
    *,
    max_results: int,
) -> tuple[list[TweetCandidate], list[dict[str, object]]]:
    account_candidates: dict[str, Sequence[TweetCandidate]] = {}
    skipped_accounts: list[dict[str, object]] = []
    for raw_username in target_accounts:
        username = raw_username.strip().lstrip("@")
        if not username:
            continue
        try:
            payload = run_twitter_json(twitter_bin, "user-posts", username, "--max", str(max_results))
            account_candidates[username] = extract_tweet_candidates(payload)
        except Exception as error:
            LOGGER.warning("failed to fetch posts for @%s: %s", username, error)
            skipped_accounts.append({"username": username, "reason": "fetch_failed", "error": str(error)})
    return pick_latest_account_candidates(account_candidates), skipped_accounts


def log_dry_run_candidates(selected_candidates: Sequence[TweetCandidate]) -> None:
    if not selected_candidates:
        LOGGER.info("[dry-run] no tweets selected for liking")
        return
    for index, candidate in enumerate(selected_candidates, start=1):
        LOGGER.info(
            "[dry-run] %s. tweet_id=%s user=@%s created_at=%s text=%s",
            index,
            candidate.tweet_id,
            candidate.username or "unknown",
            candidate.created_at.isoformat(),
            candidate.text[:200],
        )


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    now = current_jst_datetime()
    requested_like_count = random.randint(5, 15)
    normalized_target_accounts = [item.strip().lstrip("@") for item in args.target_accounts if item.strip()]

    try:
        state_entries = prune_liked_state(load_liked_state(args.state_path), now=now)
        liked_ids = build_liked_id_set(state_entries)
        current_daily_like_count = count_daily_likes(state_entries, now.date())
        remaining_daily_capacity = max(DAILY_LIKE_LIMIT - current_daily_like_count, 0)

        candidate_window_minutes: int | None = None
        fetch_skipped: list[dict[str, object]] = []
        if normalized_target_accounts:
            source_mode = "target_accounts"
            candidates, fetch_skipped = fetch_target_account_candidates(
                args.twitter_bin,
                normalized_target_accounts,
                max_results=args.target_post_max,
            )
        else:
            source_mode = "feed"
            feed_candidates = fetch_feed_candidates(args.twitter_bin, args.feed_max)
            candidates, candidate_window_minutes = select_timeline_candidates(feed_candidates, now=now)
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

    eligible_candidates = [candidate for candidate in candidates if candidate.tweet_id not in liked_ids]
    if source_mode == "feed":
        eligible_candidates = prioritize_feed_candidates(eligible_candidates, now=now)
    else:
        random.shuffle(eligible_candidates)
    selected_count = determine_like_count(requested_like_count, remaining_daily_capacity, len(eligible_candidates))
    selected_candidates = eligible_candidates[:selected_count]

    if args.dry_run:
        log_dry_run_candidates(selected_candidates)
    else:
        save_liked_state(args.state_path, state_entries)

    liked_tweet_ids: list[str] = []
    skipped: list[dict[str, object]] = []
    if not args.dry_run:
        for index, candidate in enumerate(selected_candidates, start=1):
            try:
                run_twitter_write(args.twitter_bin, "like", candidate.tweet_id)
            except Exception as error:
                LOGGER.warning("failed to like %s: %s", candidate.tweet_id, error)
                skipped.append({"tweet_id": candidate.tweet_id, "reason": "like_failed", "error": str(error)})
            else:
                liked_at = current_jst_datetime()
                LOGGER.info("liked tweet_id=%s user=@%s", candidate.tweet_id, candidate.username or "unknown")
                state_entries.append(LikedStateEntry(liked_at=liked_at, tweet_id=candidate.tweet_id))
                state_entries = prune_liked_state(state_entries, now=liked_at)
                save_liked_state(args.state_path, state_entries)
                liked_tweet_ids.append(candidate.tweet_id)

            if index < len(selected_candidates):
                sleep_seconds = random.randint(MIN_LIKE_SLEEP_SECONDS, MAX_LIKE_SLEEP_SECONDS)
                LOGGER.info("sleeping %s seconds before next like", sleep_seconds)
                time.sleep(sleep_seconds)

    write_summary(
        args.summary_output,
        {
            "status": "ok",
            "run_at_jst": now.isoformat(),
            "dry_run": args.dry_run,
            "source_mode": source_mode,
            "target_accounts": normalized_target_accounts,
            "requested_like_count": requested_like_count,
            "daily_like_limit": DAILY_LIKE_LIMIT,
            "current_daily_like_count": current_daily_like_count,
            "remaining_daily_capacity": remaining_daily_capacity,
            "candidate_window_minutes": candidate_window_minutes,
            "candidate_count": len(candidates),
            "eligible_candidates": len(eligible_candidates),
            "selected_count": len(selected_candidates),
            "selected_candidates": [candidate_preview(candidate) for candidate in selected_candidates],
            "liked_count": len(liked_tweet_ids),
            "liked_tweet_ids": liked_tweet_ids,
            "skipped": skipped,
            "fetch_skipped": fetch_skipped,
            "state_path": str(args.state_path),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
