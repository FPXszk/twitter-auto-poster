from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase, main

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from post_feedback import (
    append_feedback_history,
    build_feedback_boost_map,
    build_feedback_entry,
    extract_posted_tweet_id,
    load_feedback_history,
    refresh_feedback_entries,
)


class PostFeedbackTest(TestCase):
    def test_extract_posted_tweet_id_reads_result_payload(self) -> None:
        payload = {"ok": True, "data": {"id": "posted-123"}}

        self.assertEqual(extract_posted_tweet_id(payload), "posted-123")

    def test_append_feedback_history_trims_old_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "feedback.jsonl"
            append_feedback_history(history_path, {"posted_tweet_id": "1"}, max_entries=2)
            append_feedback_history(history_path, {"posted_tweet_id": "2"}, max_entries=2)
            append_feedback_history(history_path, {"posted_tweet_id": "3"}, max_entries=2)

            entries = load_feedback_history(history_path)

        self.assertEqual([entry["posted_tweet_id"] for entry in entries], ["2", "3"])

    def test_refresh_feedback_entries_updates_recent_metrics(self) -> None:
        now = datetime(2026, 3, 28, 9, 0, tzinfo=timezone.utc)
        entries = [
            build_feedback_entry(
                {
                    "id": "source-1",
                    "source_id": "alpha",
                    "source_key": "alpha",
                    "source_username": "alpha_user",
                    "source_type": "search",
                    "score": 42.0,
                },
                "posted-1",
                posted_at="2026-03-28T07:00:00+00:00",
            )
        ]

        updated_entries, summary = refresh_feedback_entries(
            entries,
            fetch_tweet_payload=lambda tweet_id: {
                "id": tweet_id,
                "metrics": {"likes": 120, "retweets": 10, "replies": 3, "views": 5000},
            },
            now=now,
            min_refresh_interval_hours=0,
        )

        self.assertEqual(summary["refreshed_entries"], 1)
        self.assertEqual(updated_entries[0]["post_metrics"]["likes"], 120)

    def test_build_feedback_boost_map_uses_recent_entries_only(self) -> None:
        now = datetime(2026, 3, 28, 9, 0, tzinfo=timezone.utc)
        recent_entry = build_feedback_entry(
            {
                "id": "source-1",
                "source_id": "alpha",
                "source_key": "alpha",
                "source_username": "alpha_user",
                "source_type": "search",
                "score": 42.0,
            },
            "posted-1",
            posted_at=(now - timedelta(days=1)).isoformat(),
        )
        recent_entry["post_metrics"] = {"likes": 120, "retweets": 10, "replies": 3, "views": 5000}

        stale_entry = build_feedback_entry(
            {
                "id": "source-2",
                "source_id": "beta",
                "source_key": "beta",
                "source_username": "beta_user",
                "source_type": "search",
                "score": 12.0,
            },
            "posted-2",
            posted_at=(now - timedelta(days=30)).isoformat(),
        )
        stale_entry["post_metrics"] = {"likes": 999, "retweets": 99, "replies": 20, "views": 10000}

        boosts = build_feedback_boost_map([recent_entry, stale_entry], now=now)

        self.assertIn("alpha", boosts)
        self.assertNotIn("beta", boosts)
        self.assertGreater(boosts["alpha"]["feedback_boost"], 0.0)


if __name__ == "__main__":
    main()
