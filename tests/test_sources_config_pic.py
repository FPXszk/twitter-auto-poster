"""Tests for config/sources.yaml and config/accounts.yaml pic configuration."""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml

SOURCES_PATH = Path(__file__).resolve().parents[1] / "config" / "sources.yaml"
ACCOUNTS_PATH = Path(__file__).resolve().parents[1] / "config" / "accounts.yaml"

EXPECTED_PIC_ACCOUNTS = [
    "japanofcontext",
    "kjckikyo",
    "yureiyks",
]


class PicSourcesConfigTest(unittest.TestCase):
    """Validate pic sources in config/sources.yaml."""

    @classmethod
    def setUpClass(cls) -> None:
        raw = yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8"))
        cls.sources = raw.get("sources") or []
        cls.pic_sources = [
            s for s in cls.sources
            if s.get("category") == "pic" and s.get("enabled", True)
        ]

    def test_pic_enabled_count_is_6(self) -> None:
        self.assertEqual(len(self.pic_sources), 6)

    def test_pic_rotation_keys_are_3_accounts(self) -> None:
        rotation_keys = sorted(set(s["rotation_key"] for s in self.pic_sources))
        self.assertEqual(rotation_keys, sorted(EXPECTED_PIC_ACCOUNTS))

    def test_each_pic_account_has_big_and_small(self) -> None:
        for account in EXPECTED_PIC_ACCOUNTS:
            variants = [s for s in self.pic_sources if s["rotation_key"] == account]
            ids = sorted(s["id"] for s in variants)
            self.assertEqual(
                ids,
                sorted([f"pic-{account}-big", f"pic-{account}-small"]),
                f"{account} should have big and small entries",
            )

    def test_pic_queries_contain_filter_images(self) -> None:
        for source in self.pic_sources:
            self.assertIn(
                "filter:images",
                source["query"],
                f"{source['id']} query must include filter:images",
            )

    def test_pic_category_is_pic(self) -> None:
        for source in self.pic_sources:
            self.assertEqual(source["category"], "pic", f"{source['id']} category")

    def test_pic_sources_preserve_thresholds(self) -> None:
        for source in self.pic_sources:
            self.assertEqual(source["max_results"], 20, f"{source['id']} max_results")
            if source["id"].endswith("-big"):
                self.assertEqual(source["score_boost"], 10, f"{source['id']} score_boost")
            else:
                self.assertEqual(source["score_boost"], 6, f"{source['id']} score_boost")

    def test_pic_rotation_key_order_matches_expected(self) -> None:
        seen: list[str] = []
        for s in self.pic_sources:
            key = s["rotation_key"]
            if key not in seen:
                seen.append(key)
        self.assertEqual(seen, EXPECTED_PIC_ACCOUNTS)

    def test_buz_sources_still_3(self) -> None:
        """Pic configuration must not affect the reduced buz source count."""
        buz = [s for s in self.sources if s.get("category") == "buz" and s.get("enabled", True)]
        self.assertEqual(len(buz), 3)

    def test_news_sources_still_2(self) -> None:
        """Adding pic must not affect news source count."""
        news = [s for s in self.sources if s.get("category") == "news"]
        self.assertEqual(len(news), 2)


class PicAccountConfigTest(unittest.TestCase):
    """Validate pic account settings in config/accounts.yaml."""

    @classmethod
    def setUpClass(cls) -> None:
        raw = yaml.safe_load(ACCOUNTS_PATH.read_text(encoding="utf-8"))
        accounts = raw.get("accounts") or {}
        cls.pic = accounts.get("pic")

    def test_pic_account_exists(self) -> None:
        self.assertIsNotNone(self.pic, "accounts.yaml must have a 'pic' section")

    def test_pic_dry_run_true(self) -> None:
        self.assertTrue(self.pic["dry_run"])

    def test_pic_selection_mode_round_robin_account(self) -> None:
        self.assertEqual(self.pic["selection_mode"], "round_robin_account")

    def test_pic_reply_disabled(self) -> None:
        reply = self.pic.get("reply") or {}
        self.assertFalse(reply.get("enabled", True))

    def test_pic_summary_provider_copilot(self) -> None:
        self.assertEqual(self.pic["summary_provider"], "copilot_cli")

    def test_pic_state_files_use_pic_prefix(self) -> None:
        self.assertIn("pic", self.pic["state_file"])
        self.assertIn("pic", self.pic["rotation_state_file"])
        self.assertIn("pic", self.pic["media_state_file"])

    def test_pic_image_bonus_high(self) -> None:
        weights = self.pic.get("score_weights") or {}
        self.assertGreaterEqual(weights.get("image_bonus", 0), 15)

    def test_pic_source_reference_mode_none(self) -> None:
        self.assertEqual(self.pic.get("source_reference_mode"), "none")

    def test_pic_max_age_hours_allows_old_image_posts(self) -> None:
        """pic sources are curated image accounts that post infrequently;
        max_age_hours must be >= 720 (30 days) to avoid rejecting all candidates."""
        filters = self.pic.get("filters") or {}
        max_age = filters.get("max_age_hours")
        self.assertIsNotNone(max_age, "pic must define max_age_hours")
        self.assertGreaterEqual(max_age, 720)

    def test_pic_has_no_follower_thresholds(self) -> None:
        """pic search API payloads do not include followersCount;
        any follower threshold causes 100% candidate rejection."""
        filters = self.pic.get("filters") or {}
        self.assertIsNone(
            filters.get("min_author_followers"),
            "pic filters must not set min_author_followers (search API lacks follower data)",
        )
        self.assertIsNone(
            filters.get("max_author_followers"),
            "pic filters must not set max_author_followers (search API lacks follower data)",
        )


if __name__ == "__main__":
    unittest.main()
