from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from post_filters import candidate_rejection_reasons, merge_filters, normalize_filters


class PostFiltersTest(unittest.TestCase):
    def test_merge_filters_prefers_source_override_per_key(self) -> None:
        merged = merge_filters(
            {
                "max_age_hours": 48,
                "required_terms": ["AI"],
                "exclude_keywords": ["promo"],
            },
            {
                "max_age_hours": 12,
                "required_terms": ["Micron"],
            },
        )

        self.assertEqual(merged["max_age_hours"], 12)
        self.assertEqual(merged["required_terms"], ["Micron"])
        self.assertEqual(merged["exclude_keywords"], ["promo"])

    def test_merge_filters_respects_explicit_empty_list_override(self) -> None:
        merged = merge_filters(
            {"required_terms": ["AI"], "exclude_keywords": ["promo"]},
            {"required_terms": [], "exclude_keywords": []},
        )

        self.assertEqual(merged["required_terms"], [])
        self.assertEqual(merged["exclude_keywords"], [])

    def test_normalize_filters_keeps_default_noise_keywords(self) -> None:
        normalized = normalize_filters({"exclude_keywords": ["custom spam"]})

        self.assertIn("custom spam", normalized["exclude_keywords"])
        self.assertIn("giveaway", normalized["exclude_keywords"])

    def test_candidate_rejection_uses_merged_required_terms(self) -> None:
        merged = merge_filters(
            {"required_terms": ["AI"], "max_age_hours": 48},
            {"required_terms": ["Micron"]},
        )
        created_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        reasons = candidate_rejection_reasons(
            text="Micron demand is improving this quarter.",
            created_at=created_at,
            raw_filters=merged,
        )

        self.assertNotIn("tweet does not include any required_terms", reasons)

    def test_candidate_rejection_ignores_old_tweet_when_age_limit_tightens(self) -> None:
        created_at = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()

        reasons = candidate_rejection_reasons(
            text="Micron demand is improving this quarter.",
            created_at=created_at,
            raw_filters={"max_age_hours": 18},
        )

        self.assertIn("tweet is older than max_age_hours", reasons)

    def test_candidate_rejection_rejects_author_with_too_many_followers(self) -> None:
        created_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        reasons = candidate_rejection_reasons(
            text="急に伸びた投資メモです。",
            created_at=created_at,
            raw_filters={"max_author_followers": 50000},
            author_metrics={"followers": 120000},
        )

        self.assertIn("author exceeds max_author_followers", reasons)

    def test_candidate_rejection_rejects_author_with_too_few_followers(self) -> None:
        created_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        reasons = candidate_rejection_reasons(
            text="急に伸びた投資メモです。",
            created_at=created_at,
            raw_filters={"min_author_followers": 500},
            author_metrics={"followers": 120},
        )

        self.assertIn("author is below min_author_followers", reasons)

    def test_candidate_rejection_rejects_author_when_follower_count_is_unavailable(self) -> None:
        created_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        reasons = candidate_rejection_reasons(
            text="急に伸びた投資メモです。",
            created_at=created_at,
            raw_filters={"max_author_followers": 50000},
            author_metrics={"followers": 0},
        )

        self.assertIn("author follower count unavailable", reasons)

    def test_pic_candidate_not_rejected_when_no_follower_filters(self) -> None:
        """When neither min_ nor max_author_followers is set, missing
        follower data must not cause rejection — this is the pic scenario."""
        created_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        reasons = candidate_rejection_reasons(
            text="https://t.co/example",
            created_at=created_at,
            raw_filters={"max_age_hours": 720},
            author_metrics={"followers": 0},
        )

        self.assertNotIn("author follower count unavailable", reasons)
        self.assertNotIn("author is below min_author_followers", reasons)

    def test_pic_old_candidate_passes_relaxed_age_limit(self) -> None:
        """A 10-day-old image post must pass when max_age_hours=720."""
        created_at = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

        reasons = candidate_rejection_reasons(
            text="https://t.co/example",
            created_at=created_at,
            raw_filters={"max_age_hours": 720},
        )

        self.assertNotIn("tweet is older than max_age_hours", reasons)

    def test_pic_very_old_candidate_rejected_beyond_relaxed_limit(self) -> None:
        """A 31-day-old post should still be rejected at max_age_hours=720."""
        created_at = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()

        reasons = candidate_rejection_reasons(
            text="https://t.co/example",
            created_at=created_at,
            raw_filters={"max_age_hours": 720},
        )

        self.assertIn("tweet is older than max_age_hours", reasons)


if __name__ == "__main__":
    unittest.main()
