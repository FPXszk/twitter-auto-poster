from __future__ import annotations

import argparse
import logging
import random
import time
from datetime import date
from pathlib import Path

from auto_follow import (
    DEFAULT_STATE_PATH,
    DEFAULT_TWITTER_BIN,
    configure_logging,
    current_jst_datetime,
    extract_username,
    fetch_authenticated_username,
    fetch_usernames,
    load_follow_state,
    run_twitter_write,
    save_follow_state,
    write_summary,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_SUMMARY_OUTPUT = Path("tmp/auto_unfollow_summary.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-unfollow users who did not follow back after a waiting period.")
    parser.add_argument("--twitter-bin", type=Path, default=DEFAULT_TWITTER_BIN)
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--followers-max", type=int, default=500)
    parser.add_argument("--min-age-days", type=int, default=7)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def parse_followed_at(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def build_unfollow_candidates(
    state_entries: list[dict[str, object]],
    *,
    today: date,
    min_age_days: int,
    follower_usernames: set[str],
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for entry in state_entries:
        username = extract_username(entry)
        if not username:
            continue
        if bool(entry.get("unfollowed")):
            continue
        followed_at = parse_followed_at(entry.get("followed_at"))
        if followed_at is None:
            continue
        if (today - followed_at).days < min_age_days:
            continue
        if username.lower() in follower_usernames:
            continue
        candidates.append(entry)
    return candidates


def mark_unfollowed(state_entries: list[dict[str, object]], username: str) -> None:
    normalized = username.lower()
    for entry in state_entries:
        if extract_username(entry).lower() == normalized:
            entry["unfollowed"] = True
            return


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    now = current_jst_datetime()

    try:
        state_entries = load_follow_state(args.state_path)
        auth_username = fetch_authenticated_username(args.twitter_bin)
        follower_usernames = fetch_usernames(args.twitter_bin, "followers", auth_username, args.followers_max)
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

    target_unfollow_count = random.randint(1, 3)
    candidates = build_unfollow_candidates(
        state_entries,
        today=now.date(),
        min_age_days=args.min_age_days,
        follower_usernames=follower_usernames,
    )
    random.shuffle(candidates)

    unfollowed: list[str] = []
    skipped: list[dict[str, object]] = []
    for entry in candidates:
        if len(unfollowed) >= target_unfollow_count:
            break
        username = extract_username(entry)
        if not username:
            continue
        try:
            run_twitter_write(args.twitter_bin, "unfollow", username)
        except Exception as error:
            LOGGER.warning("failed to unfollow @%s: %s", username, error)
            skipped.append({"username": username, "reason": "unfollow_failed"})
            continue

        LOGGER.info("unfollowed @%s", username)
        mark_unfollowed(state_entries, username)
        save_follow_state(args.state_path, state_entries)
        unfollowed.append(username)

        if len(unfollowed) < target_unfollow_count:
            sleep_seconds = random.randint(3, 8)
            LOGGER.info("sleeping %s seconds before next unfollow", sleep_seconds)
            time.sleep(sleep_seconds)

    save_follow_state(args.state_path, state_entries)
    write_summary(
        args.summary_output,
        {
            "status": "ok",
            "run_at_jst": now.isoformat(),
            "auth_username": auth_username,
            "requested_unfollow_count": target_unfollow_count,
            "eligible_candidates": len(candidates),
            "unfollowed_count": len(unfollowed),
            "unfollowed_usernames": unfollowed,
            "skipped": skipped,
            "state_path": str(args.state_path),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
