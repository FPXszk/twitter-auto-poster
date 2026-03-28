from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from post_reply import (
    extract_replies_from_tweet_detail,
    extract_reply_targets,
    load_reply_check_cursor,
    filter_unreplied,
    generate_reply_text,
    load_replied_state,
    save_reply_check_cursor,
    save_replied_state,
    select_reply_targets,
    send_reply,
    fetch_bot_username,
    run_auto_reply,
)


SAMPLE_TWEET_DETAIL_PAYLOAD = {
    "ok": True,
    "data": [
        {
            "id": "original-100",
            "text": "元の自動投稿です",
            "author": {"id": "bot-user-id", "screenName": "mybotaccount"},
        },
        {
            "id": "reply-201",
            "text": "@mybotaccount いいですね！参考になります",
            "author": {"id": "user-abc", "screenName": "someone_else"},
        },
        {
            "id": "reply-202",
            "text": "@someone_else ありがとうございます",
            "author": {"id": "bot-user-id", "screenName": "mybotaccount"},
        },
        {
            "id": "reply-203",
            "text": "@someone_else すごく面白い投稿ですね",
            "author": {"id": "user-xyz", "screenName": "another_user"},
        },
    ],
}

SAMPLE_WHOAMI_PAYLOAD = {
    "ok": True,
    "data": {
        "user": {
            "id": "bot-user-id",
            "screenName": "mybotaccount",
            "name": "My Bot",
        }
    },
}


class ExtractReplyTargetsTest(TestCase):
    def test_returns_recent_posted_tweet_ids(self) -> None:
        now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
        history = [
            {
                "posted_tweet_id": "tweet-1",
                "posted_at": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "posted_tweet_id": "tweet-2",
                "posted_at": (now - timedelta(hours=5)).isoformat(),
            },
            {
                "posted_tweet_id": "tweet-3",
                "posted_at": (now - timedelta(days=20)).isoformat(),
            },
        ]

        targets = extract_reply_targets(history, max_checks=10, now=now)
        tweet_ids = [t["posted_tweet_id"] for t in targets]
        self.assertIn("tweet-1", tweet_ids)
        self.assertIn("tweet-2", tweet_ids)
        self.assertNotIn("tweet-3", tweet_ids)

    def test_respects_max_checks_cap(self) -> None:
        now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
        history = [
            {
                "posted_tweet_id": f"tweet-{i}",
                "posted_at": (now - timedelta(hours=i)).isoformat(),
            }
            for i in range(10)
        ]

        targets = extract_reply_targets(history, max_checks=3, now=now)
        self.assertEqual(len(targets), 3)

    def test_skips_entries_without_posted_tweet_id(self) -> None:
        now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
        history = [
            {"posted_at": now.isoformat()},
            {"posted_tweet_id": "", "posted_at": now.isoformat()},
            {"posted_tweet_id": "valid-1", "posted_at": now.isoformat()},
        ]
        targets = extract_reply_targets(history, max_checks=10, now=now)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["posted_tweet_id"], "valid-1")

    def test_select_reply_targets_rotates_across_recent_posts(self) -> None:
        now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
        history = [
            {
                "posted_tweet_id": f"tweet-{i}",
                "posted_at": (now - timedelta(hours=i)).isoformat(),
            }
            for i in range(6)
        ]

        first_targets, first_cursor = select_reply_targets(history, max_checks=2, now=now)
        second_targets, second_cursor = select_reply_targets(
            history,
            max_checks=2,
            previous_tweet_id=first_cursor,
            now=now,
        )

        self.assertEqual([item["posted_tweet_id"] for item in first_targets], ["tweet-0", "tweet-1"])
        self.assertEqual([item["posted_tweet_id"] for item in second_targets], ["tweet-2", "tweet-3"])
        self.assertEqual(second_cursor, "tweet-3")


class ExtractRepliesTest(TestCase):
    def test_excludes_bot_own_replies_and_original(self) -> None:
        replies = extract_replies_from_tweet_detail(
            SAMPLE_TWEET_DETAIL_PAYLOAD["data"],
            original_tweet_id="original-100",
            bot_username="mybotaccount",
        )
        reply_ids = [r["id"] for r in replies]
        self.assertNotIn("original-100", reply_ids)
        self.assertNotIn("reply-202", reply_ids)
        self.assertIn("reply-201", reply_ids)
        self.assertNotIn("reply-203", reply_ids)

    def test_returns_empty_for_no_replies(self) -> None:
        data = [
            {
                "id": "original-100",
                "text": "投稿",
                "author": {"id": "bot-user-id", "screenName": "mybotaccount"},
            },
        ]
        replies = extract_replies_from_tweet_detail(
            data, original_tweet_id="original-100", bot_username="mybotaccount"
        )
        self.assertEqual(replies, [])


class RepliedStateTest(TestCase):
    def test_load_save_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "replied.jsonl"
            save_replied_state(state_path, {"reply-201": "original-100"})
            loaded = load_replied_state(state_path)
            self.assertIn("reply-201", loaded)

    def test_load_missing_file_returns_empty(self) -> None:
        loaded = load_replied_state(Path("/nonexistent/path/replied.jsonl"))
        self.assertEqual(loaded, {})

    def test_filter_unreplied_removes_known_ids(self) -> None:
        replies = [
            {"id": "reply-201", "text": "hello"},
            {"id": "reply-203", "text": "world"},
        ]
        already_replied = {"reply-201": "original-100"}
        unreplied = filter_unreplied(replies, already_replied)
        self.assertEqual(len(unreplied), 1)
        self.assertEqual(unreplied[0]["id"], "reply-203")

    def test_reply_check_cursor_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "reply-check.txt"
            save_reply_check_cursor(cursor_path, "tweet-123")
            self.assertEqual(load_reply_check_cursor(cursor_path), "tweet-123")


class FetchBotUsernameTest(TestCase):
    def test_extracts_username_from_whoami_payload(self) -> None:
        def mock_runner(cmd, **kwargs):
            class Result:
                returncode = 0
                stdout = json.dumps(SAMPLE_WHOAMI_PAYLOAD)
                stderr = ""
            return Result()

        username = fetch_bot_username("twitter", command_runner=mock_runner)
        self.assertEqual(username, "mybotaccount")

    def test_raises_on_failure(self) -> None:
        def mock_runner(cmd, **kwargs):
            class Result:
                returncode = 1
                stdout = ""
                stderr = "auth failed"
            return Result()

        with self.assertRaises(RuntimeError):
            fetch_bot_username("twitter", command_runner=mock_runner)

    def test_accepts_username_alias(self) -> None:
        payload = {"ok": True, "data": {"user": {"username": "mybotaccount"}}}

        def mock_runner(cmd, **kwargs):
            class Result:
                returncode = 0
                stdout = json.dumps(payload)
                stderr = ""
            return Result()

        self.assertEqual(fetch_bot_username("twitter", command_runner=mock_runner), "mybotaccount")


class GenerateReplyTextTest(TestCase):
    def test_returns_copilot_output(self) -> None:
        def mock_runner(cmd, **kwargs):
            class Result:
                returncode = 0
                stdout = "ありがとうございます！参考になれば嬉しいです。"
                stderr = ""
            return Result()

        text = generate_reply_text(
            model="gpt-5-mini",
            original_text="元の投稿テキスト",
            reply_text="いいですね",
            prompt_path="",
            command_runner=mock_runner,
        )
        self.assertIn("ありがとう", text)

    def test_raises_on_empty_output(self) -> None:
        def mock_runner(cmd, **kwargs):
            class Result:
                returncode = 0
                stdout = ""
                stderr = ""
            return Result()

        with self.assertRaises(RuntimeError):
            generate_reply_text(
                model="gpt-5-mini",
                original_text="test",
                reply_text="test",
                prompt_path="",
                command_runner=mock_runner,
            )

    def test_raises_on_nonzero_returncode(self) -> None:
        def mock_runner(cmd, **kwargs):
            class Result:
                returncode = 1
                stdout = "Copilot authentication failed"
                stderr = "auth error"
            return Result()

        with self.assertRaises(RuntimeError):
            generate_reply_text(
                model="gpt-5-mini",
                original_text="test",
                reply_text="test",
                prompt_path="",
                command_runner=mock_runner,
            )

    def test_rejects_overly_long_reply(self) -> None:
        long_text = "あ" * 300

        def mock_runner(cmd, **kwargs):
            class Result:
                returncode = 0
                stdout = long_text
                stderr = ""
            return Result()

        with self.assertRaises(RuntimeError):
            generate_reply_text(
                model="gpt-5-mini",
                original_text="test",
                reply_text="test",
                prompt_path="",
                command_runner=mock_runner,
                max_reply_length=280,
            )


class SendReplyTest(TestCase):
    def test_sends_and_returns_new_id(self) -> None:
        reply_payload = {
            "ok": True,
            "data": {
                "success": True,
                "action": "reply",
                "id": "new-reply-999",
                "replyTo": "reply-201",
            },
        }

        def mock_runner(cmd, **kwargs):
            class Result:
                returncode = 0
                stdout = json.dumps(reply_payload)
                stderr = ""
            return Result()

        result = send_reply(
            "twitter", reply_to_id="reply-201", text="ありがとう！",
            command_runner=mock_runner,
        )
        self.assertEqual(result["id"], "new-reply-999")


class RunAutoReplyTest(TestCase):
    def test_full_flow_with_mocks(self) -> None:
        """統合テスト: 全体フローをモックで検証。"""
        now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
        history = [
            {
                "posted_tweet_id": "original-100",
                "posted_at": (now - timedelta(hours=2)).isoformat(),
                "source_tweet_id": "src-1",
            },
        ]

        tweet_detail_calls = []

        def mock_fetch_tweet_detail(twitter_bin, tweet_id):
            tweet_detail_calls.append(tweet_id)
            return SAMPLE_TWEET_DETAIL_PAYLOAD["data"]

        copilot_calls = []

        def mock_generate(model, original_text, reply_text, prompt_path, **kwargs):
            copilot_calls.append(reply_text)
            return "ありがとうございます！"

        send_calls = []

        def mock_send(twitter_bin, reply_to_id, text, **kwargs):
            send_calls.append((reply_to_id, text))
            return {"id": f"sent-{reply_to_id}", "replyTo": reply_to_id}

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "replied.jsonl"
            cursor_path = Path(tmpdir) / "reply-check.txt"

            result = run_auto_reply(
                feedback_history=history,
                twitter_bin="twitter",
                bot_username="mybotaccount",
                replied_state_path=state_path,
                reply_check_state_path=cursor_path,
                max_reply_checks=5,
                max_replies=3,
                copilot_model="gpt-5-mini",
                reply_prompt_path="",
                now=now,
                fetch_tweet_detail_fn=mock_fetch_tweet_detail,
                generate_reply_fn=mock_generate,
                send_reply_fn=mock_send,
            )

            self.assertEqual(load_reply_check_cursor(cursor_path), "original-100")

        self.assertEqual(result["checked_tweets"], 1)
        self.assertEqual(result["replies_sent"], 1)
        self.assertEqual(len(send_calls), 1)
        sent_reply_ids = {call[0] for call in send_calls}
        self.assertIn("reply-201", sent_reply_ids)

    def test_respects_max_replies_cap(self) -> None:
        now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
        history = [
            {
                "posted_tweet_id": "original-100",
                "posted_at": (now - timedelta(hours=2)).isoformat(),
            },
        ]

        def mock_fetch(twitter_bin, tweet_id):
            return SAMPLE_TWEET_DETAIL_PAYLOAD["data"]

        def mock_generate(model, original_text, reply_text, prompt_path, **kwargs):
            return "返信です"

        send_calls = []

        def mock_send(twitter_bin, reply_to_id, text, **kwargs):
            send_calls.append(reply_to_id)
            return {"id": f"sent-{reply_to_id}", "replyTo": reply_to_id}

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "replied.jsonl"
            cursor_path = Path(tmpdir) / "reply-check.txt"

            result = run_auto_reply(
                feedback_history=history,
                twitter_bin="twitter",
                bot_username="mybotaccount",
                replied_state_path=state_path,
                reply_check_state_path=cursor_path,
                max_reply_checks=5,
                max_replies=1,
                copilot_model="gpt-5-mini",
                reply_prompt_path="",
                now=now,
                fetch_tweet_detail_fn=mock_fetch,
                generate_reply_fn=mock_generate,
                send_reply_fn=mock_send,
            )

        self.assertEqual(result["replies_sent"], 1)
        self.assertEqual(len(send_calls), 1)

    def test_reply_cursor_only_advances_through_checked_tweets(self) -> None:
        now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
        history = [
            {
                "posted_tweet_id": f"original-{i}",
                "posted_at": (now - timedelta(hours=i)).isoformat(),
            }
            for i in range(3)
        ]

        detail_by_id = {
            "original-0": [
                {"id": "original-0", "text": "元投稿0", "author": {"screenName": "mybotaccount"}},
                {"id": "reply-0", "text": "@mybotaccount 0への返信", "author": {"screenName": "user0"}},
            ],
            "original-1": [
                {"id": "original-1", "text": "元投稿1", "author": {"screenName": "mybotaccount"}},
                {"id": "reply-1", "text": "@mybotaccount 1への返信", "author": {"screenName": "user1"}},
            ],
            "original-2": [
                {"id": "original-2", "text": "元投稿2", "author": {"screenName": "mybotaccount"}},
                {"id": "reply-2", "text": "@mybotaccount 2への返信", "author": {"screenName": "user2"}},
            ],
        }

        checked_ids: list[str] = []

        def mock_fetch(twitter_bin, tweet_id):
            checked_ids.append(tweet_id)
            return detail_by_id[tweet_id]

        def mock_generate(model, original_text, reply_text, prompt_path, **kwargs):
            return "ありがとうございます"

        def mock_send(twitter_bin, reply_to_id, text, **kwargs):
            return {"id": f"sent-{reply_to_id}"}

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "replied.jsonl"
            cursor_path = Path(tmpdir) / "reply-check.txt"

            result = run_auto_reply(
                feedback_history=history,
                twitter_bin="twitter",
                bot_username="mybotaccount",
                replied_state_path=state_path,
                reply_check_state_path=cursor_path,
                max_reply_checks=3,
                max_replies=1,
                now=now,
                fetch_tweet_detail_fn=mock_fetch,
                generate_reply_fn=mock_generate,
                send_reply_fn=mock_send,
            )

            self.assertEqual(checked_ids, ["original-0"])
            self.assertEqual(result["reply_check_cursor_after"], "original-0")
            self.assertEqual(load_reply_check_cursor(cursor_path), "original-0")

    def test_fetch_failure_does_not_advance_reply_cursor(self) -> None:
        now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
        history = [
            {
                "posted_tweet_id": "original-0",
                "posted_at": now.isoformat(),
            }
        ]

        def mock_fetch(twitter_bin, tweet_id):
            raise RuntimeError("tweet detail failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "replied.jsonl"
            cursor_path = Path(tmpdir) / "reply-check.txt"

            result = run_auto_reply(
                feedback_history=history,
                twitter_bin="twitter",
                bot_username="mybotaccount",
                replied_state_path=state_path,
                reply_check_state_path=cursor_path,
                max_reply_checks=1,
                max_replies=1,
                now=now,
                fetch_tweet_detail_fn=mock_fetch,
            )

            self.assertEqual(result["checked_tweets"], 0)
            self.assertEqual(result["reply_check_cursor_after"], "")
            self.assertEqual(load_reply_check_cursor(cursor_path), "")


if __name__ == "__main__":
    main()
