from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "python").resolve()))

from auto_unfollow import build_unfollow_candidates, mark_unfollowed


class AutoUnfollowTests(unittest.TestCase):
    def test_build_unfollow_candidates_filters_by_age_followback_and_status(self) -> None:
        state = [
            {"username": "keep", "followed_at": "2026-03-20", "unfollowed": False},
            {"username": "follower", "followed_at": "2026-03-10", "unfollowed": False},
            {"username": "done", "followed_at": "2026-03-10", "unfollowed": True},
            {"username": "target", "followed_at": "2026-03-10", "unfollowed": False},
            {"username": "skipped", "skipped_at": "2026-03-10", "skip_reason": "ratio_out_of_range"},
        ]

        candidates = build_unfollow_candidates(
            state,
            today=date(2026, 3, 24),
            min_age_days=7,
            follower_usernames={"follower"},
        )

        self.assertEqual([entry["username"] for entry in candidates], ["target"])

    def test_mark_unfollowed_updates_matching_state_entry(self) -> None:
        state = [{"username": "target", "followed_at": "2026-03-10", "unfollowed": False}]

        mark_unfollowed(state, "target")

        self.assertTrue(state[0]["unfollowed"])


if __name__ == "__main__":
    unittest.main()
