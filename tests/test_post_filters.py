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


if __name__ == "__main__":
    unittest.main()
