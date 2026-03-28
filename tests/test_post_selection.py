from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from post_selection import deduplicate_source_order, normalize_rotation_source, preferred_media_mode_from_previous, select_candidates


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
            {"id": "a-1", "source_key": "markminervini", "score": 80, "views": 100, "replies": 1, "retweets": 5, "likes": 10, "created_at": "2026-03-22T08:00:00+00:00"},
            {"id": "b-1", "source_key": "hypertechinvest", "score": 60, "views": 90, "replies": 1, "retweets": 4, "likes": 8, "created_at": "2026-03-22T08:30:00+00:00"},
            {"id": "b-2", "source_key": "hypertechinvest", "score": 50, "views": 80, "replies": 1, "retweets": 3, "likes": 7, "created_at": "2026-03-22T08:15:00+00:00"},
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
            {"id": "b-1", "source_key": "hypertechinvest", "score": 60, "views": 90, "replies": 1, "retweets": 4, "likes": 8, "created_at": "2026-03-22T08:30:00+00:00"},
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

    def test_round_robin_account_groups_sources_by_rotation_key(self) -> None:
        candidates = [
            {"id": "alpha-big", "source_key": "alpha-big", "rotation_key": "alpha", "score": 90, "views": 100, "replies": 2, "retweets": 5, "likes": 10, "created_at": "2026-03-22T08:00:00+00:00"},
            {"id": "alpha-small", "source_key": "alpha-small", "rotation_key": "alpha", "score": 80, "views": 90, "replies": 1, "retweets": 4, "likes": 8, "created_at": "2026-03-22T08:10:00+00:00"},
            {"id": "beta-big", "source_key": "beta-big", "rotation_key": "beta", "score": 70, "views": 80, "replies": 1, "retweets": 3, "likes": 7, "created_at": "2026-03-22T08:20:00+00:00"},
        ]

        selected, rotation = select_candidates(
            candidates,
            source_order=["alpha", "beta"],
            max_candidates=2,
            selection_mode="round_robin_account",
            previous_source="alpha",
        )

        self.assertEqual([item["id"] for item in selected], ["beta-big"])
        self.assertEqual(rotation["selection_mode"], "round_robin_account")
        self.assertEqual(rotation["selected_source"], "beta")
        self.assertEqual(rotation["next_source"], "alpha")

    def test_preferred_media_mode_alternates_from_previous(self) -> None:
        self.assertEqual(preferred_media_mode_from_previous("image"), "text")
        self.assertEqual(preferred_media_mode_from_previous("text"), "image")
        self.assertEqual(preferred_media_mode_from_previous(""), "image")

    def test_score_mode_prefers_target_media_bucket(self) -> None:
        candidates = [
            {"id": "text-1", "source_key": "alpha", "score": 90, "views": 100, "replies": 1, "retweets": 5, "likes": 10, "media_mode": "text", "created_at": "2026-03-22T08:00:00+00:00"},
            {"id": "image-1", "source_key": "beta", "score": 80, "views": 90, "replies": 1, "retweets": 4, "likes": 8, "media_mode": "image", "created_at": "2026-03-22T08:30:00+00:00"},
        ]

        selected, rotation = select_candidates(
            candidates,
            source_order=[],
            max_candidates=1,
            selection_mode="score",
            preferred_media_mode="image",
        )

        self.assertEqual(selected[0]["id"], "image-1")
        self.assertEqual(rotation["target_media_mode"], "image")
        self.assertTrue(rotation["media_preference_satisfied"])


    def test_deduplicate_source_order_removes_consecutive_duplicates(self) -> None:
        """source_order に同一 rotation_key が複数あっても、出現順を保ちつつ重複を除く。"""
        raw = ["alpha", "alpha", "beta", "beta", "gamma"]
        result = deduplicate_source_order(raw)
        self.assertEqual(result, ["alpha", "beta", "gamma"])

    def test_deduplicate_source_order_preserves_first_occurrence(self) -> None:
        """先頭出現の位置を維持し、2 回目以降を取り除く。"""
        raw = ["beta", "alpha", "beta", "alpha", "gamma"]
        result = deduplicate_source_order(raw)
        self.assertEqual(result, ["beta", "alpha", "gamma"])

    def test_deduplicate_source_order_drops_empty_strings(self) -> None:
        result = deduplicate_source_order(["", "alpha", "", "beta", ""])
        self.assertEqual(result, ["alpha", "beta"])

    def test_round_robin_account_with_duplicate_source_order_rotates_correctly(self) -> None:
        """source_order に重複がある場合でも、前回 alpha → 次は beta に進む。"""
        candidates = [
            {"id": "a-big", "source_key": "alpha-big", "rotation_key": "alpha", "score": 90, "views": 100, "replies": 2, "retweets": 5, "likes": 10, "created_at": "2026-03-22T08:00:00+00:00"},
            {"id": "a-small", "source_key": "alpha-small", "rotation_key": "alpha", "score": 80, "views": 90, "replies": 1, "retweets": 4, "likes": 8, "created_at": "2026-03-22T08:10:00+00:00"},
            {"id": "b-big", "source_key": "beta-big", "rotation_key": "beta", "score": 70, "views": 80, "replies": 1, "retweets": 3, "likes": 7, "created_at": "2026-03-22T08:20:00+00:00"},
        ]
        raw_source_order = ["alpha", "alpha", "beta", "beta"]
        deduped = deduplicate_source_order(raw_source_order)

        selected, rotation = select_candidates(
            candidates,
            source_order=deduped,
            max_candidates=2,
            selection_mode="round_robin_account",
            previous_source="alpha",
        )

        self.assertEqual([item["id"] for item in selected], ["b-big"])
        self.assertEqual(rotation["selected_source"], "beta")
        self.assertEqual(rotation["next_source"], "alpha")

    def test_round_robin_account_state_persists_across_runs(self) -> None:
        """rotation state ファイルに保存された前回ソースから次ソースへ進む。"""
        candidates_run1 = [
            {"id": "a1", "source_key": "alpha-big", "rotation_key": "alpha", "score": 90, "views": 100, "replies": 2, "retweets": 5, "likes": 10, "created_at": "2026-03-22T08:00:00+00:00"},
            {"id": "b1", "source_key": "beta-big", "rotation_key": "beta", "score": 80, "views": 90, "replies": 1, "retweets": 4, "likes": 8, "created_at": "2026-03-22T08:10:00+00:00"},
            {"id": "c1", "source_key": "gamma-big", "rotation_key": "gamma", "score": 70, "views": 80, "replies": 1, "retweets": 3, "likes": 7, "created_at": "2026-03-22T08:20:00+00:00"},
        ]
        deduped = ["alpha", "beta", "gamma"]

        _, rot1 = select_candidates(
            candidates_run1,
            source_order=deduped,
            max_candidates=1,
            selection_mode="round_robin_account",
            previous_source="",
        )
        self.assertEqual(rot1["selected_source"], "alpha")

        _, rot2 = select_candidates(
            candidates_run1,
            source_order=deduped,
            max_candidates=1,
            selection_mode="round_robin_account",
            previous_source=rot1["selected_source"],
        )
        self.assertEqual(rot2["selected_source"], "beta")

        _, rot3 = select_candidates(
            candidates_run1,
            source_order=deduped,
            max_candidates=1,
            selection_mode="round_robin_account",
            previous_source=rot2["selected_source"],
        )
        self.assertEqual(rot3["selected_source"], "gamma")


if __name__ == "__main__":
    unittest.main()
