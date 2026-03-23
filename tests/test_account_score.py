from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "python").resolve()))

from python.account_score import analyze_account_score

JST = ZoneInfo("Asia/Tokyo")


def build_post(
    *,
    text: str,
    created_at_iso: str,
    views: int,
    likes: int = 0,
    replies: int = 0,
    retweets: int = 0,
    quotes: int = 0,
    bookmarks: int = 0,
    urls: list[object] | None = None,
    media: list[object] | None = None,
) -> dict[str, object]:
    return {
        "id": "1",
        "text": text,
        "createdAtISO": created_at_iso,
        "metrics": {
            "views": views,
            "likes": likes,
            "replies": replies,
            "retweets": retweets,
            "quotes": quotes,
            "bookmarks": bookmarks,
        },
        "urls": urls or [],
        "media": media or [],
    }


class AccountScoreTests(unittest.TestCase):
    def test_high_quality_profile_scores_healthy_or_better(self) -> None:
        user = {
            "followers": 420,
            "following": 180,
            "createdAt": "Wed Jan 01 07:03:40 +0000 2025",
        }
        posts = [
            build_post(
                text="【本日の注目銘柄】03/21\n半導体3社の動きと見るポイントを整理しました。+4.2% の背景は？",
                created_at_iso="2026-03-21T02:00:00+09:00",
                views=1200,
                likes=24,
                replies=4,
            ),
            build_post(
                text="日経平均 ¥38,200 +1.1%\n明日のシナリオを3点に絞って整理します。",
                created_at_iso="2026-03-20T18:00:00+09:00",
                views=980,
                likes=18,
                replies=2,
                media=[{"type": "photo"}],
            ),
        ]

        result = analyze_account_score(
            user,
            posts,
            assume_premium=True,
            now=datetime(2026, 3, 21, 4, 0, tzinfo=JST),
        )

        self.assertGreaterEqual(result["score"], 65.0)
        self.assertIn(result["distribution"], ("healthy", "strong"))
        self.assertLessEqual(result["components"]["penalties"], 0.0)

    def test_quote_activity_counts_as_strong_positive_signal(self) -> None:
        user = {
            "followers": 320,
            "following": 150,
            "createdAt": "Wed Jan 01 07:03:40 +0000 2025",
        }
        base_posts = [
            build_post(
                text="半導体3社の見方を整理しました。来週の注目ポイントは？",
                created_at_iso="2026-03-21T03:30:00+09:00",
                views=500,
                likes=8,
                replies=1,
            )
        ]
        quoted_posts = [
            build_post(
                text="半導体3社の見方を整理しました。来週の注目ポイントは？",
                created_at_iso="2026-03-21T03:30:00+09:00",
                views=500,
                likes=8,
                replies=1,
                quotes=1,
            )
        ]

        base_result = analyze_account_score(
            user,
            base_posts,
            assume_premium=True,
            now=datetime(2026, 3, 21, 4, 0, tzinfo=JST),
        )
        quoted_result = analyze_account_score(
            user,
            quoted_posts,
            assume_premium=True,
            now=datetime(2026, 3, 21, 4, 0, tzinfo=JST),
        )

        self.assertGreater(
            quoted_result["metrics"]["average_engagement_signal_rate"],
            base_result["metrics"]["average_engagement_signal_rate"],
        )
        self.assertGreater(quoted_result["score"], base_result["score"])

    def test_link_heavy_profile_is_not_flagged_as_link_penalty(self) -> None:
        user = {
            "followers": 220,
            "following": 140,
            "createdAt": "Wed Jan 01 07:03:40 +0000 2025",
        }
        posts = [
            build_post(
                text="今朝の市場メモです https://example.com",
                created_at_iso="2026-03-21T03:30:00+09:00",
                views=320,
                likes=6,
                urls=[{"expanded_url": "https://example.com"}],
            )
            for _ in range(5)
        ]

        result = analyze_account_score(
            user,
            posts,
            assume_premium=True,
            now=datetime(2026, 3, 21, 4, 0, tzinfo=JST),
        )

        self.assertEqual(result["metrics"]["link_rate"], 1.0)
        self.assertEqual(result["components"]["penalties"], 0.0)
        self.assertFalse(any("リンク比率" in warning for warning in result["warnings"]))
        self.assertFalse(any("返信側に回してください" in suggestion for suggestion in result["suggestions"]))

    def test_negative_spammy_profile_gets_penalties(self) -> None:
        user = {
            "followers": 90,
            "following": 650,
            "createdAt": "Wed Mar 11 07:03:40 +0000 2026",
        }
        posts = [
            build_post(
                text="【悲報】最悪だ https://example.com #a #b #c",
                created_at_iso="2026-03-21T03:30:00+09:00",
                views=50,
                urls=[{"expanded_url": "https://example.com"}],
            )
            for _ in range(10)
        ]

        result = analyze_account_score(
            user,
            posts,
            assume_premium=False,
            now=datetime(2026, 3, 21, 4, 0, tzinfo=JST),
        )

        self.assertLess(result["score"], 45.0)
        self.assertEqual(result["distribution"], "fragile")
        self.assertGreater(result["components"]["penalties"], 0.0)
        self.assertTrue(result["warnings"])
        self.assertFalse(any("リンク比率" in warning for warning in result["warnings"]))
