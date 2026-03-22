from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from post_selection import normalize_rotation_source, select_candidates


class PostSelectionTest(unittest.TestCase):
    def test_normalize_rotation_source_returns_next_start(self) -> None:
        previous_source, start_index = normalize_rotation_source(
            "hypertechinvest",
            ["markminervini", "hypertechinvest", "stocksavvyshay"],
        )

        self.assertEqual(previous_source, "hypertechinvest")
        self.assertEqual(start_index, 2)

    def test_round_robin_prefers_next_source_with_candidates(self) -> None:
        candidates = [
            {"id": "a-1", "source_key": "markminervini", "score": 80, "views": 100, "retweets": 5, "likes": 10, "created_at": "2026-03-22T08:00:00+00:00"},
            {"id": "b-1", "source_key": "hypertechinvest", "score": 60, "views": 90, "retweets": 4, "likes": 8, "created_at": "2026-03-22T08:30:00+00:00"},
            {"id": "b-2", "source_key": "hypertechinvest", "score": 50, "views": 80, "retweets": 3, "likes": 7, "created_at": "2026-03-22T08:15:00+00:00"},
        ]

        selected, rotation = select_candidates(
            candidates,
            source_order=["markminervini", "hypertechinvest", "stocksavvyshay"],
            max_candidates=2,
            selection_mode="round_robin",
            previous_source="markminervini",
        )

        self.assertEqual([item["id"] for item in selected], ["b-1", "b-2"])
        self.assertEqual(rotation["selected_source"], "hypertechinvest")
        self.assertEqual(rotation["next_source"], "stocksavvyshay")

    def test_round_robin_skips_source_without_candidates(self) -> None:
        candidates = [
            {"id": "b-1", "source_key": "hypertechinvest", "score": 60, "views": 90, "retweets": 4, "likes": 8, "created_at": "2026-03-22T08:30:00+00:00"},
        ]

        selected, rotation = select_candidates(
            candidates,
            source_order=["markminervini", "hypertechinvest"],
            max_candidates=1,
            selection_mode="round_robin",
            previous_source="markminervini",
        )

        self.assertEqual(selected[0]["id"], "b-1")
        self.assertEqual(rotation["selected_source"], "hypertechinvest")
        self.assertEqual(rotation["next_source"], "markminervini")


if __name__ == "__main__":
    unittest.main()
