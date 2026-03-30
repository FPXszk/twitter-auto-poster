from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")
DEFAULT_TWITTER_BIN = Path("python/.venv/bin/twitter")
DEFAULT_BACKUP_DIR = Path("tmp/bulk_delete_backup")
DEFAULT_STATE_PATH = Path("tmp/bulk_delete_state.json")
TWEET_CATEGORIES = ("normal", "reply", "quote", "retweet", "unknown")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk-delete tweets from the authenticated account.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually delete tweets. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        default=False,
        help="Skip the interactive confirmation prompt (use with --execute).",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=200,
        help="Maximum number of tweets to fetch (default: 200).",
    )
    parser.add_argument(
        "--twitter-bin",
        type=Path,
        default=DEFAULT_TWITTER_BIN,
        help="Path to twitter-cli binary.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help="Directory for backup JSON files.",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help="Path to state file for resume support.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level.",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# twitter-cli wrappers (matches auto_follow.py pattern)
# ---------------------------------------------------------------------------

def run_twitter_json(twitter_bin: Path, *args: str) -> dict[str, Any]:
    command = [str(twitter_bin), *args, "--json"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"command failed: {' '.join(command)}"
        )
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
        message = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"command failed: {' '.join(command)}"
        )
        raise RuntimeError(message)


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

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


def fetch_whoami_username(twitter_bin: Path) -> str:
    payload = run_twitter_json(twitter_bin, "whoami")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("twitter whoami returned unexpected data")
    user = data.get("user")
    if not isinstance(user, dict):
        raise RuntimeError("twitter whoami did not return a user object")
    username = str(user.get("username", "")).strip()
    if not username:
        raise RuntimeError("twitter whoami did not return a username")
    return username


def fetch_total_count(twitter_bin: Path, username: str) -> int:
    payload = run_twitter_json(twitter_bin, "user", username)
    data = payload.get("data")
    if not isinstance(data, dict):
        return 0
    direct = data.get("tweets")
    if direct not in (None, ""):
        return _safe_int(direct)
    user = data.get("user")
    if not isinstance(user, dict):
        return 0
    direct = user.get("tweets_count")
    if direct not in (None, ""):
        return _safe_int(direct)
    public_metrics = user.get("public_metrics")
    if isinstance(public_metrics, dict):
        return _safe_int(public_metrics.get("tweet_count"))
    return 0


def fetch_tweets(twitter_bin: Path, username: str, max_count: int) -> list[dict[str, Any]]:
    payload = run_twitter_json(
        twitter_bin, "user-posts", username, "--max", str(max_count),
    )
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        tweets = data.get("tweets")
        if isinstance(tweets, list):
            return [item for item in tweets if isinstance(item, dict)]
    return []


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_tweets(tweets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    classified: dict[str, list[dict[str, Any]]] = {
        cat: [] for cat in TWEET_CATEGORIES
    }
    for tweet in tweets:
        tweet_id = str(tweet.get("id", "")).strip()
        if not tweet_id or not _has_known_tweet_shape(tweet):
            classified["unknown"].append(tweet)
            continue
        if _is_retweet(tweet):
            classified["retweet"].append(tweet)
        elif _is_reply(tweet):
            classified["reply"].append(tweet)
        elif _is_quote(tweet):
            classified["quote"].append(tweet)
        else:
            classified["normal"].append(tweet)
    return classified


def _has_known_tweet_shape(tweet: dict[str, Any]) -> bool:
    if "isRetweet" in tweet:
        return True
    legacy_shape_markers = (
        "retweeted_status_id",
        "retweeted_status",
        "quoted_status_id",
        "quotedTweet",
        "in_reply_to_status_id",
        "inReplyToStatusId",
        "inReplyToTweetId",
    )
    return any(marker in tweet for marker in legacy_shape_markers)


def _is_retweet(tweet: dict[str, Any]) -> bool:
    if bool(tweet.get("isRetweet", False)):
        return True
    if tweet.get("retweetedBy"):
        return True
    if tweet.get("retweeted_status_id"):
        return True
    if isinstance(tweet.get("retweeted_status"), dict):
        return True
    return False


def _is_reply(tweet: dict[str, Any]) -> bool:
    return bool(
        tweet.get("in_reply_to_status_id")
        or tweet.get("inReplyToStatusId")
        or tweet.get("inReplyToTweetId")
    )


def _is_quote(tweet: dict[str, Any]) -> bool:
    return bool(tweet.get("quotedTweet") or tweet.get("quoted_status_id"))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_before_execute(
    classified: dict[str, list[dict[str, Any]]],
    *,
    total_count: int,
    fetched_count: int,
) -> list[str]:
    errors: list[str] = []
    if total_count != fetched_count:
        errors.append(
            f"Count mismatch: API reports {total_count} tweets but fetched {fetched_count}. "
            "Some tweets may be missing. Aborting for safety."
        )
    unknown_items = classified.get("unknown", [])
    if unknown_items:
        errors.append(
            f"Found {len(unknown_items)} unknown/unclassifiable tweet(s). "
            "Aborting for safety."
        )
    return errors


# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------

def confirm_execution(classified: dict[str, list[dict[str, Any]]]) -> bool:
    total = sum(len(v) for v in classified.values())
    LOGGER.info("About to delete/unretweet %d tweets.", total)
    for cat in TWEET_CATEGORIES:
        count = len(classified[cat])
        if count:
            LOGGER.info("  %s: %d", cat, count)
    answer = input("Type 'yes' to proceed, anything else to abort: ").strip().lower()
    return answer == "yes"


# ---------------------------------------------------------------------------
# Backup / State
# ---------------------------------------------------------------------------

def write_backup(path: Path, data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("Backup written to %s (%d tweets)", path, len(data))


def load_state(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return {str(item) for item in raw}
    except (json.JSONDecodeError, OSError) as error:
        LOGGER.warning("Failed to load state from %s: %s", path, error)
    return set()


def save_state(path: Path, deleted_ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sorted(deleted_ids), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def execute_deletions(
    *,
    twitter_bin: Path,
    classified: dict[str, list[dict[str, Any]]],
    backup_dir: Path,
    state_path: Path,
) -> dict[str, int]:
    all_tweets: list[dict[str, Any]] = []
    for cat in TWEET_CATEGORIES:
        all_tweets.extend(classified.get(cat, []))

    timestamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"bulk_delete_backup_{timestamp}.json"
    write_backup(backup_path, all_tweets)

    deleted_ids = load_state(state_path)
    stats: dict[str, int] = {"deleted": 0, "unretweeted": 0, "skipped": 0, "errors": 0}

    for cat in ("normal", "reply", "quote"):
        for tweet in classified.get(cat, []):
            tweet_id = str(tweet.get("id", "")).strip()
            if not tweet_id or tweet_id in deleted_ids:
                stats["skipped"] += 1
                continue
            try:
                run_twitter_write(twitter_bin, "delete", tweet_id)
                deleted_ids.add(tweet_id)
                stats["deleted"] += 1
                LOGGER.info("Deleted tweet %s (%s)", tweet_id, cat)
            except RuntimeError as error:
                stats["errors"] += 1
                LOGGER.error("Failed to delete tweet %s: %s", tweet_id, error)
            save_state(state_path, deleted_ids)

    for tweet in classified.get("retweet", []):
        tweet_id = str(tweet.get("id", "")).strip()
        if not tweet_id or tweet_id in deleted_ids:
            stats["skipped"] += 1
            continue
        try:
            run_twitter_write(twitter_bin, "unretweet", tweet_id)
            deleted_ids.add(tweet_id)
            stats["unretweeted"] += 1
            LOGGER.info("Unretweeted tweet %s", tweet_id)
        except RuntimeError as error:
            stats["errors"] += 1
            LOGGER.error("Failed to unretweet tweet %s: %s", tweet_id, error)
        save_state(state_path, deleted_ids)

    return stats


# ---------------------------------------------------------------------------
# Dry-run summary
# ---------------------------------------------------------------------------

def log_dry_run_summary(
    *,
    username: str,
    total_count: int,
    fetched_count: int,
    classified: dict[str, list[dict[str, Any]]],
) -> None:
    LOGGER.info("=== Bulk Delete Dry-Run Summary ===")
    LOGGER.info("Account: @%s", username)
    LOGGER.info("Total tweets (API): %d", total_count)
    LOGGER.info("Fetched tweets:     %d", fetched_count)
    if total_count != fetched_count:
        LOGGER.warning(
            "COUNT MISMATCH: API=%d, fetched=%d (diff=%d)",
            total_count, fetched_count, total_count - fetched_count,
        )
    for cat in TWEET_CATEGORIES:
        items = classified.get(cat, [])
        LOGGER.info("  %-10s %d", cat, len(items))
    LOGGER.info("=== End Summary ===")
    LOGGER.info("Run with --execute to delete. This is irreversible.")


# ---------------------------------------------------------------------------
# Configure logging
# ---------------------------------------------------------------------------

def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(levelname)s] %(message)s",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    try:
        username = fetch_whoami_username(args.twitter_bin)
        LOGGER.info("Authenticated as @%s", username)
    except RuntimeError as error:
        LOGGER.error("Failed to determine account: %s", error)
        return 1

    try:
        total_count = fetch_total_count(args.twitter_bin, username)
        LOGGER.info("API reports %d total tweets for @%s", total_count, username)
    except RuntimeError as error:
        LOGGER.error("Failed to fetch total tweet count: %s", error)
        return 1

    try:
        tweets = fetch_tweets(args.twitter_bin, username, args.max)
        LOGGER.info("Fetched %d tweets", len(tweets))
    except RuntimeError as error:
        LOGGER.error("Failed to fetch tweets: %s", error)
        return 1

    classified = classify_tweets(tweets)
    fetched_count = len(tweets)

    if not args.execute:
        log_dry_run_summary(
            username=username,
            total_count=total_count,
            fetched_count=fetched_count,
            classified=classified,
        )
        return 0

    # Execute mode: validate before proceeding
    errors = validate_before_execute(
        classified, total_count=total_count, fetched_count=fetched_count,
    )
    if errors:
        for error_msg in errors:
            LOGGER.error("ABORT: %s", error_msg)
        return 1

    if not args.yes:
        if not confirm_execution(classified):
            LOGGER.info("Aborted by user.")
            return 0

    try:
        stats = execute_deletions(
            twitter_bin=args.twitter_bin,
            classified=classified,
            backup_dir=args.backup_dir,
            state_path=args.state_path,
        )
    except RuntimeError as error:
        LOGGER.error("Execution failed: %s", error)
        return 1

    LOGGER.info(
        "Done: deleted=%d, unretweeted=%d, skipped=%d, errors=%d",
        stats["deleted"], stats["unretweeted"], stats["skipped"], stats["errors"],
    )
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
