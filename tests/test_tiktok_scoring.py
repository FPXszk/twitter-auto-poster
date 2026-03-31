from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_scoring import (
    DEFAULT_TIKTOK_SCORE_WEIGHTS,
    calculate_tiktok_score,
    normalize_tiktok_score_weights,
)


class NormalizeTikTokScoreWeightsTest(unittest.TestCase):
    def test_defaults_filled(self) -> None:
        weights = normalize_tiktok_score_weights(None)
        for key in DEFAULT_TIKTOK_SCORE_WEIGHTS:
            self.assertIn(key, weights)

    def test_overrides_applied(self) -> None:
        weights = normalize_tiktok_score_weights({"likes": 5.0, "views": 2.0})
        self.assertEqual(weights["likes"], 5.0)
        self.assertEqual(weights["views"], 2.0)


class CalculateTikTokScoreTest(unittest.TestCase):
    def test_score_with_tiktok_metrics(self) -> None:
        metrics = {"likes": 100, "views": 5000, "retweets": 20, "replies": 10}
        now = datetime(2026, 3, 31, 14, 0, tzinfo=timezone.utc)
        created_at = "2026-03-31T12:00:00+00:00"

        score, breakdown = calculate_tiktok_score(
            metrics,
            {"likes": 1.0, "views": 0.01, "retweets": 2.0, "replies": 3.0},
            created_at=created_at,
            max_age_hours=72,
            source_boost=5.0,
            now=now,
        )
        self.assertGreater(score, 0)
        self.assertIn("likes", breakdown)
        self.assertIn("views", breakdown)
        self.assertIn("retweets", breakdown)
        self.assertIn("replies", breakdown)
        self.assertIn("source_boost", breakdown)

    def test_freshness_bonus_calculation(self) -> None:
        metrics = {"likes": 10, "views": 100, "retweets": 1, "replies": 1}
        now = datetime(2026, 3, 31, 14, 0, tzinfo=timezone.utc)
        created_at = "2026-03-31T12:00:00+00:00"

        _, breakdown = calculate_tiktok_score(
            metrics,
            {"freshness": 2.0},
            created_at=created_at,
            max_age_hours=24,
            source_boost=0,
            now=now,
        )
        self.assertGreater(breakdown.get("freshness", 0), 0)

    def test_zero_metrics_returns_zero_base_score(self) -> None:
        metrics = {"likes": 0, "views": 0, "retweets": 0, "replies": 0}
        now = datetime(2026, 3, 31, 14, 0, tzinfo=timezone.utc)

        score, breakdown = calculate_tiktok_score(
            metrics,
            None,
            created_at="2026-03-31T12:00:00+00:00",
            max_age_hours=24,
            source_boost=0,
            now=now,
        )
        metric_sum = (
            breakdown.get("likes", 0)
            + breakdown.get("views", 0)
            + breakdown.get("retweets", 0)
            + breakdown.get("replies", 0)
        )
        self.assertEqual(metric_sum, 0)

    def test_score_breakdown_includes_all_expected_keys(self) -> None:
        metrics = {"likes": 10, "views": 500, "retweets": 2, "replies": 1}
        now = datetime(2026, 3, 31, 14, 0, tzinfo=timezone.utc)

        _, breakdown = calculate_tiktok_score(
            metrics,
            None,
            created_at="2026-03-31T12:00:00+00:00",
            max_age_hours=24,
            source_boost=0,
            now=now,
        )
        expected_keys = {"likes", "retweets", "replies", "views", "velocity", "freshness", "source_boost"}
        for key in expected_keys:
            self.assertIn(key, breakdown, f"missing key: {key}")


if __name__ == "__main__":
    unittest.main()
