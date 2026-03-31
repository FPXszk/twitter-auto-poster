from __future__ import annotations

import argparse
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "python").resolve()))

from auto_follow import (
    build_active_followed_username_set,
    build_recorded_username_set,
    collect_followback_usernames,
    contains_stock_keywords,
    evaluate_candidate,
    evaluate_followback_candidate,
    has_japanese_signal,
    has_japanese_text,
    matches_stock_keyword,
    parse_args,
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
    def test_parse_args_uses_suzuka_saga_as_default_target(self) -> None:
        with patch.object(sys, "argv", ["auto_follow.py"]):
            args = parse_args()

        self.assertEqual(args.target_username, "suzuka_saga")

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


class FollowbackTests(unittest.TestCase):
    """Tests for followback-priority logic."""

    def test_evaluate_followback_candidate_accepts_unverified_user(self) -> None:
        """Followback should NOT require verified status."""
        reason = evaluate_followback_candidate(
            build_user(verified=False),
            following_usernames=set(),
            recorded_usernames=set(),
        )
        self.assertIsNone(reason)

    def test_evaluate_followback_candidate_accepts_without_japanese_or_stock(self) -> None:
        reason = evaluate_followback_candidate(
            build_user(description="English only profile"),
            following_usernames=set(),
            recorded_usernames=set(),
        )
        self.assertIsNone(reason)

    def test_evaluate_followback_candidate_rejects_missing_username(self) -> None:
        reason = evaluate_followback_candidate(
            {"verified": True, "description": "test"},
            following_usernames=set(),
            recorded_usernames=set(),
        )
        self.assertEqual(reason, "missing_username")

    def test_evaluate_followback_candidate_rejects_already_following(self) -> None:
        reason = evaluate_followback_candidate(
            build_user(username="alice"),
            following_usernames={"alice"},
            recorded_usernames=set(),
        )
        self.assertEqual(reason, "already_following")

    def test_evaluate_followback_candidate_rejects_already_recorded(self) -> None:
        reason = evaluate_followback_candidate(
            build_user(username="bob"),
            following_usernames=set(),
            recorded_usernames={"bob"},
        )
        self.assertEqual(reason, "already_recorded")

    def test_collect_followback_usernames_returns_eligible(self) -> None:
        my_followers = {"alice", "bob", "charlie", "dave"}
        result = collect_followback_usernames(
            my_followers,
            following_usernames={"alice"},
            active_followed_usernames={"charlie"},
        )
        self.assertEqual(set(result), {"bob", "dave"})

    def test_collect_followback_usernames_returns_empty_when_all_excluded(self) -> None:
        result = collect_followback_usernames(
            {"alice"},
            following_usernames={"alice"},
            active_followed_usernames=set(),
        )
        self.assertEqual(result, [])

    def test_collect_followback_usernames_returns_sorted_for_determinism(self) -> None:
        result = collect_followback_usernames(
            {"charlie", "alice", "bob"},
            following_usernames=set(),
            active_followed_usernames=set(),
        )
        self.assertEqual(result, ["alice", "bob", "charlie"])

    def test_build_active_followed_username_set_excludes_skipped_and_unfollowed(self) -> None:
        state = [
            {"username": "active", "followed_at": "2026-03-20", "unfollowed": False},
            {"username": "gone", "followed_at": "2026-03-10", "unfollowed": True},
            {"username": "skipped", "skipped_at": "2026-03-24", "skip_reason": "not_verified"},
        ]

        self.assertEqual(build_active_followed_username_set(state), {"active"})

    def test_collect_followback_usernames_allows_previously_skipped_or_unfollowed(self) -> None:
        state = [
            {"username": "skipped", "skipped_at": "2026-03-24", "skip_reason": "not_verified"},
            {"username": "unfollowed", "followed_at": "2026-03-10", "unfollowed": True},
        ]

        result = collect_followback_usernames(
            {"skipped", "unfollowed"},
            following_usernames=set(),
            active_followed_usernames=build_active_followed_username_set(state),
        )

        self.assertEqual(set(result), {"skipped", "unfollowed"})

    def test_record_follow_stores_follow_type_followback(self) -> None:
        state: list[dict[str, object]] = []
        record_follow(state, "alice", "2026-03-28", follow_type="followback")
        self.assertEqual(state[0]["follow_type"], "followback")
        self.assertEqual(state[0]["followed_at"], "2026-03-28")
        self.assertFalse(state[0]["unfollowed"])

    def test_record_follow_defaults_to_new_follow_type(self) -> None:
        state: list[dict[str, object]] = []
        record_follow(state, "bob", "2026-03-28")
        self.assertEqual(state[0]["follow_type"], "new_follow")

    def test_main_fills_with_new_follow_when_followback_fails(self) -> None:
        args = argparse.Namespace(
            twitter_bin=Path("python/.venv/bin/twitter"),
            state_path=Path("config/follow_state.json"),
            summary_output=Path("tmp/auto_follow_summary.json"),
            target_username="suzuka_saga",
            followers_max=1000,
            following_max=500,
            recent_post_max=5,
            log_level="INFO",
        )
        summary_payloads: list[dict[str, object]] = []

        def fake_run_twitter_write(_twitter_bin: Path, command: str, username: str) -> None:
            self.assertEqual(command, "follow")
            if username == "followback1":
                raise RuntimeError("followback failed")

        with (
            patch("auto_follow.parse_args", return_value=args),
            patch("auto_follow.configure_logging"),
            patch("auto_follow.current_jst_datetime", return_value=datetime(2026, 3, 28, 9, 0, 0)),
            patch("auto_follow.random.randint", return_value=1),
            patch("auto_follow.random.shuffle", side_effect=lambda items: None),
            patch("auto_follow.load_follow_state", return_value=[]),
            patch("auto_follow.fetch_authenticated_username", return_value="me"),
            patch("auto_follow.fetch_usernames", side_effect=[set(), {"followback1"}]),
            patch(
                "auto_follow.run_twitter_json",
                return_value={
                    "ok": True,
                    "data": [
                        {
                            "username": "new1",
                            "verified": True,
                            "description": "日本株と投資が好きです",
                        }
                    ],
                },
            ),
            patch("auto_follow.run_twitter_write", side_effect=fake_run_twitter_write) as mock_follow,
            patch("auto_follow.save_follow_state"),
            patch("auto_follow.write_summary", side_effect=lambda _path, payload: summary_payloads.append(payload)),
        ):
            from auto_follow import main

            self.assertEqual(main(), 0)

        self.assertEqual(
            [call.args[2] for call in mock_follow.call_args_list],
            ["followback1", "new1"],
        )
        self.assertEqual(summary_payloads[0]["followed_back_count"], 0)
        self.assertEqual(summary_payloads[0]["followed_new_count"], 1)
        self.assertEqual(summary_payloads[0]["followed_usernames"], ["new1"])


if __name__ == "__main__":
    unittest.main()
