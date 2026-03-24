from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "python").resolve()))

from auto_follow import (
    build_recorded_username_set,
    contains_stock_keywords,
    evaluate_candidate,
    has_japanese_signal,
    has_japanese_text,
    matches_stock_keyword,
    record_follow,
    record_skip,
)


def build_user(
    *,
    username: str = "sample",
    verified: bool = True,
    followers: int = 100,
    following: int = 100,
    description: str = "日本株と投資が好きです",
) -> dict[str, object]:
    return {
        "username": username,
        "verified": verified,
        "followers": followers,
        "following": following,
        "description": description,
    }


class AutoFollowTests(unittest.TestCase):
    def test_has_japanese_text_detects_profile_language(self) -> None:
        self.assertTrue(has_japanese_text("日本株と投資"))
        self.assertFalse(has_japanese_text("US equities only"))

    def test_contains_stock_keywords_checks_expected_terms(self) -> None:
        self.assertTrue(contains_stock_keywords("日経とNISAを見ています"))
        self.assertFalse(contains_stock_keywords("travel and food"))

    def test_evaluate_candidate_accepts_verified_japanese_stock_account(self) -> None:
        reason = evaluate_candidate(
            build_user(),
            following_usernames=set(),
            recorded_usernames=set(),
        )

        self.assertIsNone(reason)

    def test_matches_stock_keyword_uses_recent_posts_for_stock_match(self) -> None:
        self.assertTrue(
            matches_stock_keyword(
                build_user(description="日本語プロフィールです"),
                ["今日は決算と相場を見ています"],
            )
        )

    def test_has_japanese_signal_uses_recent_posts_when_profile_is_not_japanese(self) -> None:
        self.assertTrue(has_japanese_signal("US stocks and macro", ["今日は相場を見ています"]))
        self.assertFalse(has_japanese_signal("US stocks and macro", ["market review only"]))

    def test_evaluate_candidate_rejects_not_verified_account(self) -> None:
        self.assertEqual(
            evaluate_candidate(
                build_user(verified=False),
                following_usernames=set(),
                recorded_usernames=set(),
            ),
            "not_verified",
        )

    def test_evaluate_candidate_rejects_already_following_and_recorded(self) -> None:
        self.assertEqual(
            evaluate_candidate(
                build_user(username="alice"),
                following_usernames={"alice"},
                recorded_usernames=set(),
            ),
            "already_following",
        )
        self.assertEqual(
            evaluate_candidate(
                build_user(username="bob"),
                following_usernames=set(),
                recorded_usernames={"bob"},
            ),
            "already_recorded",
        )

    def test_record_follow_and_skip_update_state_entries(self) -> None:
        state: list[dict[str, object]] = []

        record_skip(state, "alice", "2026-03-24", "not_verified")
        record_follow(state, "bob", "2026-03-24")

        self.assertEqual(build_recorded_username_set(state), {"alice", "bob"})
        self.assertEqual(state[0]["skip_reason"], "not_verified")
        self.assertEqual(state[1]["followed_at"], "2026-03-24")
        self.assertEqual(state[1]["unfollowed"], False)


if __name__ == "__main__":
    unittest.main()
