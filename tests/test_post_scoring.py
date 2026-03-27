from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from post_scoring import calculate_score, normalize_score_weights


class PostScoringTest(unittest.TestCase):
    def test_normalize_score_weights_includes_freshness(self) -> None:
        weights = normalize_score_weights({"retweets": 3, "velocity": 2, "freshness": 5})

        self.assertEqual(weights["likes"], 1.0)
        self.assertEqual(weights["retweets"], 3.0)
        self.assertEqual(weights["replies"], 1.0)
        self.assertEqual(weights["velocity"], 2.0)
        self.assertEqual(weights["freshness"], 5.0)

    def test_calculate_score_adds_velocity_freshness_and_source_boost(self) -> None:
        metrics = {"likes": 10, "retweets": 4, "replies": 2, "views": 500}
        now = datetime(2026, 3, 22, 9, 0, tzinfo=timezone.utc)
        created_at = "2026-03-22T07:00:00+00:00"

        score, breakdown = calculate_score(
            metrics,
            {"likes": 1, "retweets": 4, "replies": 5, "views": 0.02, "velocity": 2, "freshness": 6, "image_bonus": 12},
            created_at=created_at,
            max_age_hours=18,
            source_boost=24,
            now=now,
            has_image=True,
        )

        self.assertEqual(breakdown["likes"], 10.0)
        self.assertEqual(breakdown["retweets"], 16.0)
        self.assertEqual(breakdown["replies"], 10.0)
        self.assertEqual(breakdown["views"], 10.0)
        self.assertEqual(breakdown["velocity"], 29.0)
        self.assertEqual(breakdown["freshness"], 96.0)
        self.assertEqual(breakdown["image_bonus"], 12.0)
        self.assertEqual(breakdown["source_boost"], 24.0)
        self.assertEqual(score, 207.0)

    def test_calculate_score_skips_freshness_without_valid_timestamp(self) -> None:
        score, breakdown = calculate_score(
            {"likes": 1, "retweets": 0, "replies": 0, "views": 10},
            {"likes": 1, "retweets": 1, "replies": 4, "views": 0.1, "velocity": 2, "freshness": 6},
            created_at="not-a-date",
            max_age_hours=18,
        )

        self.assertEqual(breakdown["freshness"], 0.0)
        self.assertEqual(breakdown["velocity"], 0.0)
        self.assertEqual(score, 2.0)


if __name__ == "__main__":
    unittest.main()
