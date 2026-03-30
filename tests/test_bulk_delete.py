from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, mock_open, patch

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "python").resolve()))

from bulk_delete import (
    classify_tweets,
    execute_deletions,
    fetch_total_count,
    fetch_tweets,
    fetch_whoami_username,
    parse_args,
    validate_before_execute,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tweet(tweet_id: str, tweet_type: str = "normal", **extra: object) -> dict[str, object]:
    """Build a minimal tweet dict for testing."""
    base: dict[str, object] = {"id": tweet_id, "type": tweet_type}
    base.update(extra)
    return base


def _make_user_payload(tweets_count: int, username: str = "testuser") -> dict[str, object]:
    return {
        "ok": True,
        "data": {
            "id": "1",
            "screenName": username,
            "tweets": tweets_count,
        },
    }


def _make_whoami_payload(username: str = "testuser") -> dict[str, object]:
    return {
        "ok": True,
        "data": {
            "user": {"username": username},
        },
    }


def _make_user_posts_payload(tweets: list[dict[str, object]]) -> dict[str, object]:
    return {"ok": True, "data": tweets}


# ===========================================================================
# Phase 2: dry-run / 件数確認 CLI
# ===========================================================================

class TestParseArgs(unittest.TestCase):
    def test_defaults_are_dry_run(self) -> None:
        args = parse_args([])
        self.assertFalse(args.execute)
        self.assertFalse(args.yes)

    def test_execute_flag(self) -> None:
        args = parse_args(["--execute"])
        self.assertTrue(args.execute)

    def test_yes_flag(self) -> None:
        args = parse_args(["--yes"])
        self.assertTrue(args.yes)

    def test_max_default(self) -> None:
        args = parse_args([])
        self.assertEqual(args.max, 200)

    def test_custom_max(self) -> None:
        args = parse_args(["--max", "50"])
        self.assertEqual(args.max, 50)

    def test_twitter_bin_default(self) -> None:
        args = parse_args([])
        self.assertEqual(args.twitter_bin, Path("python/.venv/bin/twitter"))


class TestFetchWhoamiUsername(unittest.TestCase):
    def test_returns_username_from_whoami(self) -> None:
        payload = _make_whoami_payload("myaccount")
        with patch("bulk_delete.run_twitter_json", return_value=payload):
            result = fetch_whoami_username(Path("twitter"))
        self.assertEqual(result, "myaccount")

    def test_raises_on_missing_user(self) -> None:
        payload: dict[str, object] = {"ok": True, "data": {}}
        with patch("bulk_delete.run_twitter_json", return_value=payload):
            with self.assertRaises(RuntimeError):
                fetch_whoami_username(Path("twitter"))


class TestFetchTotalCount(unittest.TestCase):
    def test_extracts_tweets_count_from_current_twitter_cli_shape(self) -> None:
        payload = _make_user_payload(42)
        with patch("bulk_delete.run_twitter_json", return_value=payload):
            count = fetch_total_count(Path("twitter"), "testuser")
        self.assertEqual(count, 42)

    def test_falls_back_to_legacy_nested_shape(self) -> None:
        payload: dict[str, object] = {
            "ok": True,
            "data": {
                "user": {
                    "username": "testuser",
                    "public_metrics": {"tweet_count": 99},
                }
            },
        }
        with patch("bulk_delete.run_twitter_json", return_value=payload):
            count = fetch_total_count(Path("twitter"), "testuser")
        self.assertEqual(count, 99)

    def test_returns_zero_on_missing_count(self) -> None:
        payload: dict[str, object] = {
            "ok": True,
            "data": {"user": {"username": "testuser"}},
        }
        with patch("bulk_delete.run_twitter_json", return_value=payload):
            count = fetch_total_count(Path("twitter"), "testuser")
        self.assertEqual(count, 0)


class TestClassifyTweets(unittest.TestCase):
    def test_classifies_all_known_types(self) -> None:
        tweets = [
            {"id": "1", "text": "hello", "isRetweet": False},
            {"id": "2", "text": "hello", "inReplyToStatusId": "999"},
            {"id": "3", "text": "hello", "quotedTweet": {"id": "888", "text": "source"}},
            {"id": "4", "text": "hello", "isRetweet": True},
        ]
        result = classify_tweets(tweets)
        self.assertEqual(len(result["normal"]), 1)
        self.assertEqual(len(result["reply"]), 1)
        self.assertEqual(len(result["quote"]), 1)
        self.assertEqual(len(result["retweet"]), 1)
        self.assertEqual(len(result["unknown"]), 0)

    def test_empty_or_missing_id_goes_to_unknown(self) -> None:
        tweets: list[dict[str, object]] = [{"text": "no id"}]
        result = classify_tweets(tweets)
        self.assertEqual(len(result["unknown"]), 1)

    def test_unknown_type_detected(self) -> None:
        tweets: list[dict[str, object]] = [{"id": "x", "_unsupported_field": True}]
        result = classify_tweets(tweets)
        self.assertEqual(len(result["unknown"]), 1)

    def test_retweet_detected_by_nested_retweeted_status(self) -> None:
        tweets: list[dict[str, object]] = [
            {"id": "5", "text": "RT @someone: ...", "retweeted_status": {"id": "111"}},
        ]
        result = classify_tweets(tweets)
        self.assertEqual(len(result["retweet"]), 1)

    def test_quote_detected_by_quoted_tweet_payload(self) -> None:
        tweets: list[dict[str, object]] = [
            {"id": "6", "text": "commentary", "quotedTweet": {"id": "222", "text": "source"}},
        ]
        result = classify_tweets(tweets)
        self.assertEqual(len(result["quote"]), 1)

    def test_classification_preserves_original_tweet_data(self) -> None:
        tweet = {"id": "1", "text": "hello", "extra": "data", "isRetweet": False}
        result = classify_tweets([tweet])
        self.assertEqual(result["normal"][0]["extra"], "data")


class TestDryRunCountMismatch(unittest.TestCase):
    def test_mismatch_detected(self) -> None:
        classified = {
            "normal": [_make_tweet("1")],
            "reply": [],
            "quote": [],
            "retweet": [],
            "unknown": [],
        }
        errors = validate_before_execute(classified, total_count=5, fetched_count=1)
        self.assertTrue(any("mismatch" in e.lower() or "count" in e.lower() for e in errors))

    def test_no_mismatch_when_counts_match(self) -> None:
        classified = {
            "normal": [_make_tweet("1")],
            "reply": [],
            "quote": [],
            "retweet": [],
            "unknown": [],
        }
        errors = validate_before_execute(classified, total_count=1, fetched_count=1)
        self.assertEqual(errors, [])

    def test_unknown_items_cause_error(self) -> None:
        classified = {
            "normal": [],
            "reply": [],
            "quote": [],
            "retweet": [],
            "unknown": [_make_tweet("u1")],
        }
        errors = validate_before_execute(classified, total_count=1, fetched_count=1)
        self.assertTrue(any("unknown" in e.lower() for e in errors))


# ===========================================================================
# Phase 3: 実削除
# ===========================================================================

class TestExecuteDeletions(unittest.TestCase):
    def test_backup_written_before_execute(self) -> None:
        classified = {
            "normal": [_make_tweet("1")],
            "reply": [],
            "quote": [],
            "retweet": [],
            "unknown": [],
        }
        call_order: list[str] = []

        def mock_write_backup(path: Path, data: object) -> None:
            call_order.append("backup")

        def mock_run_write(twitter_bin: Path, *args: str) -> None:
            call_order.append("delete")

        with (
            patch("bulk_delete.write_backup", side_effect=mock_write_backup),
            patch("bulk_delete.run_twitter_write", side_effect=mock_run_write),
            patch("bulk_delete.save_state"),
            patch("bulk_delete.load_state", return_value=set()),
        ):
            execute_deletions(
                twitter_bin=Path("twitter"),
                classified=classified,
                backup_dir=Path("tmp/backup"),
                state_path=Path("tmp/state.json"),
            )

        self.assertEqual(call_order[0], "backup")
        self.assertIn("delete", call_order)

    def test_delete_normal_reply_quote_uses_delete(self) -> None:
        classified = {
            "normal": [_make_tweet("1")],
            "reply": [_make_tweet("2")],
            "quote": [_make_tweet("3")],
            "retweet": [],
            "unknown": [],
        }
        commands: list[tuple[str, ...]] = []

        def mock_run_write(twitter_bin: Path, *args: str) -> None:
            commands.append(args)

        with (
            patch("bulk_delete.write_backup"),
            patch("bulk_delete.run_twitter_write", side_effect=mock_run_write),
            patch("bulk_delete.save_state"),
            patch("bulk_delete.load_state", return_value=set()),
        ):
            execute_deletions(
                twitter_bin=Path("twitter"),
                classified=classified,
                backup_dir=Path("tmp/backup"),
                state_path=Path("tmp/state.json"),
            )

        delete_commands = [c for c in commands if c[0] == "delete"]
        self.assertEqual(len(delete_commands), 3)

    def test_retweet_uses_unretweet(self) -> None:
        classified = {
            "normal": [],
            "reply": [],
            "quote": [],
            "retweet": [_make_tweet("rt1")],
            "unknown": [],
        }
        commands: list[tuple[str, ...]] = []

        def mock_run_write(twitter_bin: Path, *args: str) -> None:
            commands.append(args)

        with (
            patch("bulk_delete.write_backup"),
            patch("bulk_delete.run_twitter_write", side_effect=mock_run_write),
            patch("bulk_delete.save_state"),
            patch("bulk_delete.load_state", return_value=set()),
        ):
            execute_deletions(
                twitter_bin=Path("twitter"),
                classified=classified,
                backup_dir=Path("tmp/backup"),
                state_path=Path("tmp/state.json"),
            )

        unretweet_commands = [c for c in commands if c[0] == "unretweet"]
        self.assertEqual(len(unretweet_commands), 1)
        self.assertEqual(unretweet_commands[0], ("unretweet", "rt1"))

    def test_resume_skips_already_deleted_ids(self) -> None:
        classified = {
            "normal": [_make_tweet("1"), _make_tweet("2")],
            "reply": [],
            "quote": [],
            "retweet": [],
            "unknown": [],
        }
        commands: list[tuple[str, ...]] = []

        def mock_run_write(twitter_bin: Path, *args: str) -> None:
            commands.append(args)

        with (
            patch("bulk_delete.write_backup"),
            patch("bulk_delete.run_twitter_write", side_effect=mock_run_write),
            patch("bulk_delete.save_state"),
            patch("bulk_delete.load_state", return_value={"1"}),
        ):
            execute_deletions(
                twitter_bin=Path("twitter"),
                classified=classified,
                backup_dir=Path("tmp/backup"),
                state_path=Path("tmp/state.json"),
            )

        delete_ids = [c[1] for c in commands if c[0] == "delete"]
        self.assertNotIn("1", delete_ids)
        self.assertIn("2", delete_ids)

    def test_execute_aborts_when_count_mismatch_exists(self) -> None:
        classified = {
            "normal": [_make_tweet("1")],
            "reply": [],
            "quote": [],
            "retweet": [],
            "unknown": [],
        }
        errors = validate_before_execute(classified, total_count=10, fetched_count=1)
        self.assertTrue(len(errors) > 0)

    def test_execute_aborts_when_unknown_items_exist(self) -> None:
        classified = {
            "normal": [_make_tweet("1")],
            "reply": [],
            "quote": [],
            "retweet": [],
            "unknown": [_make_tweet("u1")],
        }
        errors = validate_before_execute(classified, total_count=2, fetched_count=2)
        self.assertTrue(len(errors) > 0)


class TestExecuteConfirmation(unittest.TestCase):
    def test_execute_requires_confirmation_without_yes(self) -> None:
        """Simulates user declining confirmation prompt."""
        classified = {
            "normal": [_make_tweet("1")],
            "reply": [],
            "quote": [],
            "retweet": [],
            "unknown": [],
        }
        # confirm_execution should return False when user says 'n'
        with patch("builtins.input", return_value="n"):
            from bulk_delete import confirm_execution
            self.assertFalse(confirm_execution(classified))

    def test_execute_proceeds_with_yes_input(self) -> None:
        classified = {
            "normal": [_make_tweet("1")],
            "reply": [],
            "quote": [],
            "retweet": [],
            "unknown": [],
        }
        with patch("builtins.input", return_value="yes"):
            from bulk_delete import confirm_execution
            self.assertTrue(confirm_execution(classified))


class TestMainExitCode(unittest.TestCase):
    def test_main_returns_nonzero_when_delete_errors_exist(self) -> None:
        from bulk_delete import main

        with (
            patch("bulk_delete.parse_args", return_value=parse_args(["--execute", "--yes"])),
            patch("bulk_delete.configure_logging"),
            patch("bulk_delete.fetch_whoami_username", return_value="me"),
            patch("bulk_delete.fetch_total_count", return_value=1),
            patch("bulk_delete.fetch_tweets", return_value=[{"id": "1"}]),
            patch("bulk_delete.execute_deletions", return_value={"deleted": 0, "unretweeted": 0, "skipped": 0, "errors": 1}),
        ):
            self.assertEqual(main(), 1)


if __name__ == "__main__":
    unittest.main()
