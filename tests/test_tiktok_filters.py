from __future__ import annotations

import sys
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_filters import candidate_rejection_reasons, normalize_tiktok_filters


def _make_video(
    *,
    video_id: str = "v001",
    title: str = "Fun Video",
    description: str = "Great content here",
    created_at: str | None = None,
    likes: int = 500,
    views: int = 10000,
    retweets: int = 50,
    replies: int = 30,
    username: str = "testuser",
    platform_user_id: str = "111222333",
) -> dict:
    if created_at is None:
        created_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    return {
        "video_id": video_id,
        "title": title,
        "description": description,
        "created_at": created_at,
        "create_time": 1711879200,
        "share_url": f"https://www.tiktok.com/@{username}/video/{video_id}",
        "metrics": {
            "likes": likes,
            "views": views,
            "retweets": retweets,
            "replies": replies,
        },
        "author": {
            "username": username,
            "platform_user_id": platform_user_id,
        },
    }


def _make_allowlist(
    *,
    username: str = "testuser",
    platform_user_id: str = "111222333",
    enabled: bool = True,
    consent_type: str = "owner",
) -> dict:
    return {
        "creators": [
            {
                "platform_user_id": platform_user_id,
                "tiktok_username": username,
                "enabled": enabled,
                "consent_type": consent_type,
                "consent_reference": "self-owned account",
                "consent_checked_at": "2026-03-31",
                "expires_at": None,
                "max_results": 10,
                "score_boost": 0,
            }
        ]
    }


class NormalizeTikTokFiltersTest(unittest.TestCase):
    def test_defaults_applied(self) -> None:
        filters = normalize_tiktok_filters(None)
        self.assertIsNone(filters["max_age_hours"])
        self.assertEqual(filters["min_engagement"], 0)
        self.assertIsInstance(filters["exclude_keywords"], list)

    def test_values_override_defaults(self) -> None:
        filters = normalize_tiktok_filters({"max_age_hours": 48, "min_engagement": 100})
        self.assertEqual(filters["max_age_hours"], 48.0)
        self.assertEqual(filters["min_engagement"], 100)


class CandidateRejectionReasonsTest(unittest.TestCase):
    def test_video_older_than_max_age_hours_rejected(self) -> None:
        video = _make_video(created_at="2020-01-01T00:00:00+00:00")
        reasons = candidate_rejection_reasons(
            video=video,
            raw_filters={"max_age_hours": 24},
            allowlist=_make_allowlist(),
            live_run=True,
        )
        self.assertTrue(any("older" in r for r in reasons))

    def test_video_with_exclude_keyword_rejected(self) -> None:
        video = _make_video(description="Join our giveaway now!")
        reasons = candidate_rejection_reasons(
            video=video,
            raw_filters={"exclude_keywords": ["giveaway"]},
            allowlist=_make_allowlist(),
            live_run=True,
        )
        self.assertTrue(any("exclude_keyword" in r for r in reasons))

    def test_video_below_min_engagement_rejected(self) -> None:
        video = _make_video(likes=0, views=0, retweets=0, replies=0)
        reasons = candidate_rejection_reasons(
            video=video,
            raw_filters={"min_engagement": 1000},
            allowlist=_make_allowlist(),
            live_run=True,
        )
        self.assertTrue(any("engagement" in r for r in reasons))

    def test_video_not_in_allowlist_rejected(self) -> None:
        video = _make_video(username="unknown_user")
        reasons = candidate_rejection_reasons(
            video=video,
            raw_filters=None,
            allowlist=_make_allowlist(username="different_user"),
            live_run=True,
        )
        self.assertTrue(any("allowlist" in r for r in reasons))

    def test_video_passes_all_filters(self) -> None:
        video = _make_video()
        reasons = candidate_rejection_reasons(
            video=video,
            raw_filters={"max_age_hours": 720, "min_engagement": 0},
            allowlist=_make_allowlist(),
            live_run=True,
        )
        self.assertEqual(reasons, [])

    def test_missing_description_treated_as_empty_string(self) -> None:
        video = _make_video(description="")
        del video["description"]
        reasons = candidate_rejection_reasons(
            video=video,
            raw_filters={"exclude_keywords": ["giveaway"]},
            allowlist=_make_allowlist(),
            live_run=True,
        )
        keyword_reasons = [r for r in reasons if "exclude_keyword" in r]
        self.assertEqual(keyword_reasons, [])

    def test_exclude_keyword_matches_title_too(self) -> None:
        video = _make_video(title="Big giveaway!", description="Normal text")
        reasons = candidate_rejection_reasons(
            video=video,
            raw_filters={"exclude_keywords": ["giveaway"]},
            allowlist=_make_allowlist(),
            live_run=True,
        )
        self.assertTrue(any("exclude_keyword" in r for r in reasons))

    def test_no_allowlist_rejects_video(self) -> None:
        video = _make_video()
        reasons = candidate_rejection_reasons(
            video=video,
            raw_filters=None,
            allowlist=None,
            live_run=True,
        )
        self.assertTrue(any("allowlist" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
