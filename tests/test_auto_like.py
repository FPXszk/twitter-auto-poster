from __future__ import annotations

import sys
import unittest
from argparse import Namespace
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "python").resolve()))

from auto_like import (
    LikedStateEntry,
    TweetCandidate,
    count_daily_likes,
    determine_like_count,
    main,
    pick_latest_account_candidates,
    prune_liked_state,
    select_timeline_candidates,
)

JST = ZoneInfo("Asia/Tokyo")


def build_candidate(tweet_id: str, created_at: datetime, username: str = "sample") -> TweetCandidate:
    return TweetCandidate(
        tweet_id=tweet_id,
        text=f"tweet {tweet_id}",
        created_at=created_at,
        username=username,
    )


class AutoLikeTests(unittest.TestCase):
    def test_select_timeline_candidates_prefers_primary_window_when_enough_items(self) -> None:
        now = datetime(2026, 3, 24, 12, 0, tzinfo=JST)
        candidates = [
            build_candidate("1", datetime(2026, 3, 24, 11, 55, tzinfo=JST)),
            build_candidate("2", datetime(2026, 3, 24, 11, 50, tzinfo=JST)),
            build_candidate("3", datetime(2026, 3, 24, 11, 45, tzinfo=JST)),
            build_candidate("4", datetime(2026, 3, 24, 11, 40, tzinfo=JST)),
            build_candidate("5", datetime(2026, 3, 24, 11, 35, tzinfo=JST)),
            build_candidate("6", datetime(2026, 3, 24, 11, 20, tzinfo=JST)),
        ]

        selected, window_minutes = select_timeline_candidates(candidates, now=now)

        self.assertEqual(window_minutes, 30)
        self.assertEqual([item.tweet_id for item in selected], ["1", "2", "3", "4", "5"])

    def test_select_timeline_candidates_expands_window_when_needed(self) -> None:
        now = datetime(2026, 3, 24, 12, 0, tzinfo=JST)
        candidates = [
            build_candidate("1", datetime(2026, 3, 24, 11, 55, tzinfo=JST)),
            build_candidate("2", datetime(2026, 3, 24, 11, 45, tzinfo=JST)),
            build_candidate("3", datetime(2026, 3, 24, 11, 35, tzinfo=JST)),
            build_candidate("4", datetime(2026, 3, 24, 11, 20, tzinfo=JST)),
            build_candidate("5", datetime(2026, 3, 24, 11, 10, tzinfo=JST)),
            build_candidate("6", datetime(2026, 3, 24, 10, 50, tzinfo=JST)),
        ]

        selected, window_minutes = select_timeline_candidates(candidates, now=now)

        self.assertEqual(window_minutes, 60)
        self.assertEqual([item.tweet_id for item in selected], ["1", "2", "3", "4", "5"])

    def test_pick_latest_account_candidates_returns_latest_post_per_account(self) -> None:
        selected = pick_latest_account_candidates(
            {
                "alice": [
                    build_candidate("11", datetime(2026, 3, 24, 8, 0, tzinfo=JST), "alice"),
                    build_candidate("10", datetime(2026, 3, 24, 7, 0, tzinfo=JST), "alice"),
                ],
                "bob": [
                    build_candidate("20", datetime(2026, 3, 24, 6, 0, tzinfo=JST), "bob"),
                ],
            }
        )

        self.assertEqual([item.tweet_id for item in selected], ["11", "20"])

    def test_prune_liked_state_keeps_last_seven_days(self) -> None:
        now = datetime(2026, 3, 24, 12, 0, tzinfo=JST)
        entries = [
            LikedStateEntry(liked_at=datetime(2026, 3, 17, 12, 0, tzinfo=JST), tweet_id="keep"),
            LikedStateEntry(liked_at=datetime(2026, 3, 16, 11, 59, tzinfo=JST), tweet_id="drop"),
        ]

        pruned = prune_liked_state(entries, now=now)

        self.assertEqual([item.tweet_id for item in pruned], ["keep"])

    def test_count_daily_likes_counts_only_target_day(self) -> None:
        entries = [
            LikedStateEntry(liked_at=datetime(2026, 3, 24, 9, 0, tzinfo=JST), tweet_id="1"),
            LikedStateEntry(liked_at=datetime(2026, 3, 24, 18, 0, tzinfo=JST), tweet_id="2"),
            LikedStateEntry(liked_at=datetime(2026, 3, 23, 23, 59, tzinfo=JST), tweet_id="3"),
        ]

        self.assertEqual(count_daily_likes(entries, date(2026, 3, 24)), 2)

    def test_determine_like_count_applies_all_caps(self) -> None:
        self.assertEqual(determine_like_count(12, 4, 10), 4)
        self.assertEqual(determine_like_count(12, 10, 3), 3)
        self.assertEqual(determine_like_count(12, 0, 10), 0)

    def test_main_sleeps_between_attempts_even_when_a_like_fails(self) -> None:
        now = datetime(2026, 3, 24, 12, 0, tzinfo=JST)
        candidates = [
            build_candidate("1", datetime(2026, 3, 24, 11, 55, tzinfo=JST)),
            build_candidate("2", datetime(2026, 3, 24, 11, 50, tzinfo=JST)),
        ]

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            args = Namespace(
                twitter_bin=tmp_path / "twitter",
                state_path=tmp_path / "liked_ids.txt",
                summary_output=tmp_path / "summary.json",
                feed_max=50,
                target_post_max=5,
                dry_run=False,
                target_accounts=[],
                log_level="INFO",
            )

            with (
                patch("auto_like.parse_args", return_value=args),
                patch("auto_like.configure_logging"),
                patch("auto_like.current_jst_datetime", return_value=now),
                patch("auto_like.load_liked_state", return_value=[]),
                patch("auto_like.fetch_feed_candidates", return_value=candidates),
                patch("auto_like.select_timeline_candidates", return_value=(candidates, 30)),
                patch("auto_like.random.randint", side_effect=[2, 20]),
                patch("auto_like.random.shuffle", side_effect=lambda items: None),
                patch("auto_like.run_twitter_write", side_effect=[RuntimeError("boom"), None]) as like_mock,
                patch("auto_like.time.sleep") as sleep_mock,
                patch("auto_like.save_liked_state"),
                patch("auto_like.write_summary"),
            ):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(like_mock.call_count, 2)
        sleep_mock.assert_called_once_with(20)


if __name__ == "__main__":
    unittest.main()
