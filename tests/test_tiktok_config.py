from __future__ import annotations

from pathlib import Path
import unittest

import yaml

ACCOUNTS_PATH = Path(__file__).resolve().parents[1] / 'config' / 'accounts.yaml'
ALLOWLIST_PATH = Path(__file__).resolve().parents[1] / 'config' / 'tiktok_allowlist.yaml'


class TikTokConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = yaml.safe_load(ACCOUNTS_PATH.read_text(encoding='utf-8')) or {}
        cls.tiktok = (raw.get('accounts') or {}).get('tiktok') or {}
        cls.allowlist = yaml.safe_load(ALLOWLIST_PATH.read_text(encoding='utf-8')) or {}

    def test_tiktok_account_exists(self) -> None:
        self.assertTrue(self.tiktok)

    def test_tiktok_defaults_to_dry_run(self) -> None:
        self.assertTrue(self.tiktok.get('dry_run'))

    def test_tiktok_uses_tiktok_state_file(self) -> None:
        self.assertIn('tiktok', self.tiktok.get('state_file', ''))

    def test_tiktok_allowlist_path_points_to_config(self) -> None:
        self.assertEqual(self.tiktok.get('allowlist_path'), 'config/tiktok_allowlist.yaml')

    def test_tiktok_allowlist_has_creators_key(self) -> None:
        self.assertIn('creators', self.allowlist)


if __name__ == '__main__':
    unittest.main()
