"""Tests for config/sources.yaml buz source configuration."""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml

SOURCES_PATH = Path(__file__).resolve().parents[1] / "config" / "sources.yaml"
ACCOUNTS_PATH = Path(__file__).resolve().parents[1] / "config" / "accounts.yaml"

EXPECTED_NEW_ACCOUNTS = [
    "ql_7mxa",
    "yaruki_nash2",
    "rmiqx_",
]

OLD_ACCOUNTS = [
    "gorillataxjp",
    "zanengineer",
    "tkzwgrs",
    "sakenmilove",
    "bovccgdlap95845",
    "fuwaraidou_2525",
    "yeskiri",
    "romi_hoshino",
    "aigare01",
]


class SourcesConfigTest(unittest.TestCase):
    """Validate buz sources in config/sources.yaml."""

    @classmethod
    def setUpClass(cls) -> None:
        raw = yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8"))
        cls.sources = raw.get("sources") or []
        cls.buz_sources = [s for s in cls.sources if s.get("category") == "buz" and s.get("enabled", True)]

    def test_buz_enabled_count_is_6(self) -> None:
        self.assertEqual(len(self.buz_sources), 6)

    def test_buz_rotation_keys_are_only_requested_3_accounts(self) -> None:
        rotation_keys = sorted(set(s["rotation_key"] for s in self.buz_sources))
        self.assertEqual(rotation_keys, sorted(EXPECTED_NEW_ACCOUNTS))

    def test_each_account_has_big_and_small(self) -> None:
        for account in EXPECTED_NEW_ACCOUNTS:
            variants = [s for s in self.buz_sources if s["rotation_key"] == account]
            ids = sorted(s["id"] for s in variants)
            self.assertEqual(
                ids,
                sorted([f"buz-{account}-big", f"buz-{account}-small"]),
                f"{account} should have big and small entries",
            )

    def test_old_accounts_not_in_enabled_buz(self) -> None:
        enabled_keys = set(s["rotation_key"] for s in self.buz_sources)
        for old in OLD_ACCOUNTS:
            self.assertNotIn(old, enabled_keys, f"Old account {old} should not be enabled")

    def test_buz_sources_preserve_thresholds(self) -> None:
        for source in self.buz_sources:
            self.assertEqual(source["max_results"], 20, f"{source['id']} max_results")
            if source["id"].endswith("-big"):
                self.assertEqual(source["score_boost"], 10, f"{source['id']} score_boost")
            else:
                self.assertEqual(source["score_boost"], 6, f"{source['id']} score_boost")

    def test_news_sources_unchanged(self) -> None:
        news = [s for s in self.sources if s.get("category") == "news"]
        self.assertEqual(len(news), 2)

    def test_rotation_key_order_matches_expected(self) -> None:
        seen: list[str] = []
        for s in self.buz_sources:
            key = s["rotation_key"]
            if key not in seen:
                seen.append(key)
        self.assertEqual(seen, EXPECTED_NEW_ACCOUNTS)


class BuzAccountConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = yaml.safe_load(ACCOUNTS_PATH.read_text(encoding="utf-8")) or {}
        cls.buz = ((raw.get("accounts") or {}).get("buz") or {})

    def test_buz_summary_language_is_raw(self) -> None:
        self.assertEqual(self.buz.get("summary_language"), "raw")

    def test_buz_summary_provider_is_legacy_for_raw_passthrough(self) -> None:
        self.assertEqual(self.buz.get("summary_provider"), "legacy_google_translate")

    def test_buz_reply_disabled(self) -> None:
        reply = self.buz.get("reply") or {}
        self.assertFalse(reply.get("enabled", True))


if __name__ == "__main__":
    unittest.main()
