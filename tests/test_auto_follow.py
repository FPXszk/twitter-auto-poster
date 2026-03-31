from __future__ import annotations

import argparse
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "python").resolve()))

from auto_follow import (
    build_recorded_username_set,
    contains_stock_keywords,
    evaluate_candidate,
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

    def test_main_does_not_fetch_my_followers(self) -> None:
        """main() must not call fetch_usernames('followers', auth_username, ...)."""
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

        with (
            patch("auto_follow.parse_args", return_value=args),
            patch("auto_follow.configure_logging"),
            patch("auto_follow.current_jst_datetime", return_value=datetime(2026, 3, 28, 9, 0, 0)),
            patch("auto_follow.random.randint", return_value=1),
            patch("auto_follow.random.shuffle", side_effect=lambda items: None),
            patch("auto_follow.load_follow_state", return_value=[]),
            patch("auto_follow.fetch_authenticated_username", return_value="me"),
            patch("auto_follow.fetch_usernames", return_value=set()) as mock_fetch,
            patch(
                "auto_follow.run_twitter_json",
                return_value={"ok": True, "data": []},
            ),
            patch("auto_follow.run_twitter_write"),
            patch("auto_follow.save_follow_state"),
            patch("auto_follow.write_summary"),
        ):
            from auto_follow import main
            main()

        for call in mock_fetch.call_args_list:
            self.assertNotEqual(
                call.args[1],
                "followers",
                "main() must not fetch the auth user's own followers",
            )

    def test_main_summary_has_no_followback_fields(self) -> None:
        """Summary output must not contain followback-specific fields."""
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

        with (
            patch("auto_follow.parse_args", return_value=args),
            patch("auto_follow.configure_logging"),
            patch("auto_follow.current_jst_datetime", return_value=datetime(2026, 3, 28, 9, 0, 0)),
            patch("auto_follow.random.randint", return_value=1),
            patch("auto_follow.random.shuffle", side_effect=lambda items: None),
            patch("auto_follow.load_follow_state", return_value=[]),
            patch("auto_follow.fetch_authenticated_username", return_value="me"),
            patch("auto_follow.fetch_usernames", return_value=set()),
            patch(
                "auto_follow.run_twitter_json",
                return_value={"ok": True, "data": []},
            ),
            patch("auto_follow.run_twitter_write"),
            patch("auto_follow.save_follow_state"),
            patch("auto_follow.write_summary", side_effect=lambda _path, payload: summary_payloads.append(payload)),
        ):
            from auto_follow import main
            main()

        self.assertTrue(len(summary_payloads) > 0)
        payload = summary_payloads[0]
        for forbidden_key in ("followback_candidates", "followed_back_count", "followed_back_usernames"):
            self.assertNotIn(forbidden_key, payload, f"Summary must not contain '{forbidden_key}'")

    def test_main_only_new_follows_flow(self) -> None:
        """All follows recorded by main() must use follow_type='new_follow'."""
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
        recorded_follow_types: list[str] = []
        original_record_follow = record_follow

        def tracking_record_follow(entries, username, current_date, follow_type="new_follow"):
            recorded_follow_types.append(follow_type)
            return original_record_follow(entries, username, current_date, follow_type=follow_type)

        def fake_fetch_usernames(_bin, command, _user, _limit):
            if command == "followers":
                return {"fb_user1", "fb_user2"}
            return set()

        with (
            patch("auto_follow.parse_args", return_value=args),
            patch("auto_follow.configure_logging"),
            patch("auto_follow.current_jst_datetime", return_value=datetime(2026, 3, 28, 9, 0, 0)),
            patch("auto_follow.random.randint", return_value=2),
            patch("auto_follow.random.shuffle", side_effect=lambda items: None),
            patch("auto_follow.load_follow_state", return_value=[]),
            patch("auto_follow.fetch_authenticated_username", return_value="me"),
            patch("auto_follow.fetch_usernames", side_effect=fake_fetch_usernames),
            patch(
                "auto_follow.run_twitter_json",
                return_value={
                    "ok": True,
                    "data": [
                        {"username": "new1", "verified": True, "description": "日本株と投資が好きです"},
                        {"username": "new2", "verified": True, "description": "日本株と投資が好きです"},
                    ],
                },
            ),
            patch("auto_follow.run_twitter_write"),
            patch("auto_follow.save_follow_state"),
            patch("auto_follow.write_summary", side_effect=lambda _path, payload: summary_payloads.append(payload)),
            patch("auto_follow.record_follow", side_effect=tracking_record_follow),
        ):
            from auto_follow import main
            main()

        self.assertTrue(len(recorded_follow_types) > 0, "At least one follow must be recorded")
        for ft in recorded_follow_types:
            self.assertEqual(ft, "new_follow", f"All follows must be new_follow, got '{ft}'")
        payload = summary_payloads[0]
        self.assertEqual(payload["followed_new_count"], len(recorded_follow_types))
        self.assertEqual(payload["followed_count"], len(recorded_follow_types))

    def test_record_follow_defaults_to_new_follow_type(self) -> None:
        state: list[dict[str, object]] = []
        record_follow(state, "bob", "2026-03-28")
        self.assertEqual(state[0]["follow_type"], "new_follow")


if __name__ == "__main__":
    unittest.main()
