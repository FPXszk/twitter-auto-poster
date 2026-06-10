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

    def test_buz_enabled_count_is_3(self) -> None:
        self.assertEqual(len(self.buz_sources), 3)

    def test_buz_rotation_keys_are_only_requested_3_accounts(self) -> None:
        rotation_keys = sorted(set(s["rotation_key"] for s in self.buz_sources))
        self.assertEqual(rotation_keys, sorted(EXPECTED_NEW_ACCOUNTS))

    def test_each_account_has_single_enabled_source(self) -> None:
        for account in EXPECTED_NEW_ACCOUNTS:
            variants = [s for s in self.buz_sources if s["rotation_key"] == account]
            ids = sorted(s["id"] for s in variants)
            self.assertEqual(
                ids,
                [f"buz-{account}"],
                f"{account} should have exactly one enabled source",
            )

    def test_old_accounts_not_in_enabled_buz(self) -> None:
        enabled_keys = set(s["rotation_key"] for s in self.buz_sources)
        for old in OLD_ACCOUNTS:
            self.assertNotIn(old, enabled_keys, f"Old account {old} should not be enabled")

    def test_buz_sources_preserve_requested_fetch_shapes(self) -> None:
        expected = {
            "buz-ql_7mxa": {"type": "search", "max_results": 120},
            "buz-yaruki_nash2": {"type": "user", "max_results": 200},
            "buz-rmiqx_": {"type": "search", "max_results": 100},
        }
        for source in self.buz_sources:
            with self.subTest(source=source["id"]):
                self.assertEqual(source["type"], expected[source["id"]]["type"])
                self.assertEqual(source["max_results"], expected[source["id"]]["max_results"])

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

    def test_buz_max_age_hours_is_disabled(self) -> None:
        filters = self.buz.get("filters") or {}
        self.assertIsNone(filters.get("max_age_hours"))


if __name__ == "__main__":
    unittest.main()
