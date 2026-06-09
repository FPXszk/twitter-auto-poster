from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from post_duplicate_guard import (
    build_recent_duplicate_index,
    find_duplicate_in_index,
    normalize_post_text,
)


class PostDuplicateGuardTest(unittest.TestCase):
    def test_normalize_post_text_collapses_whitespace(self) -> None:
        self.assertEqual(normalize_post_text("a  b\nc"), "a b c")

    def test_build_recent_duplicate_index_includes_feedback_history(self) -> None:
        now = datetime(2026, 6, 9, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "feedback.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "posted_tweet_id": "posted-1",
                        "posted_at": (now - timedelta(days=2)).isoformat(),
                        "posted_text": "同じ 文面",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            def runner(cmd: list[str]) -> SimpleNamespace:
                return SimpleNamespace(returncode=1, stdout="", stderr="auth failed")

            index = build_recent_duplicate_index(
                str(history_path),
                "twitter",
                lookback_days=7,
                max_posts=40,
                now=now,
                command_runner=runner,
            )

        self.assertEqual(index["history_entry_count"], 1)
        self.assertEqual(index["live_entry_count"], 0)
        self.assertEqual(index["entries"][0]["normalized_text"], "同じ 文面")

    def test_build_recent_duplicate_index_includes_live_self_posts(self) -> None:
        now = datetime(2026, 6, 9, 0, 0, tzinfo=timezone.utc)

        def runner(cmd: list[str]) -> SimpleNamespace:
            if cmd[1] == "whoami":
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps({"ok": True, "data": {"user": {"screenName": "bot"}}}),
                    stderr="",
                )
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "data": [
                            {
                                "id": "live-1",
                                "text": "ライブ 重複 候補",
                                "createdAtISO": (now - timedelta(days=1)).isoformat(),
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "feedback.jsonl"
            history_path.write_text("", encoding="utf-8")
            index = build_recent_duplicate_index(
                str(history_path),
                "twitter",
                lookback_days=7,
                max_posts=40,
                now=now,
                command_runner=runner,
            )

        self.assertEqual(index["live_entry_count"], 1)
        self.assertEqual(index["entries"][0]["tweet_id"], "live-1")

    def test_find_duplicate_in_index_matches_normalized_text(self) -> None:
        result = find_duplicate_in_index(
            "重複  テキスト",
            {
                "entries": [
                    {
                        "normalized_text": "重複 テキスト",
                        "source": "feedback_history",
                        "tweet_id": "posted-1",
                        "created_at": "2026-06-08T00:00:00+00:00",
                    }
                ]
            },
        )

        self.assertTrue(result["duplicate"])
        self.assertEqual(result["tweet_id"], "posted-1")


if __name__ == "__main__":
    unittest.main()
