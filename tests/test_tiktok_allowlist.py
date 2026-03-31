from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_allowlist import get_allowed_creator, get_enabled_creators, load_allowlist, validate_creator


def _make_creator(
    *,
    platform_user_id: str = "111222333",
    tiktok_username: str = "testuser",
    enabled: bool = True,
    consent_type: str = "owner",
    consent_reference: str = "self-owned account",
    expires_at: str | None = None,
    max_results: int = 10,
    score_boost: float = 0.0,
) -> dict:
    return {
        "platform_user_id": platform_user_id,
        "tiktok_username": tiktok_username,
        "enabled": enabled,
        "consent_type": consent_type,
        "consent_reference": consent_reference,
        "consent_checked_at": "2026-03-31",
        "expires_at": expires_at,
        "max_results": max_results,
        "score_boost": score_boost,
    }


def _make_allowlist(*creators: dict) -> dict:
    return {"creators": list(creators)}


class ValidateCreatorTest(unittest.TestCase):
    def test_valid_owner_creator_has_no_errors(self) -> None:
        errors = validate_creator(_make_creator())
        self.assertEqual(errors, [])

    def test_missing_platform_user_id_is_error(self) -> None:
        creator = _make_creator()
        del creator["platform_user_id"]
        errors = validate_creator(creator)
        self.assertTrue(any("platform_user_id" in e for e in errors))

    def test_missing_consent_reference_is_error(self) -> None:
        creator = _make_creator(consent_reference="")
        errors = validate_creator(creator)
        self.assertTrue(any("consent_reference" in e for e in errors))

    def test_missing_tiktok_username_is_error(self) -> None:
        creator = _make_creator()
        del creator["tiktok_username"]
        errors = validate_creator(creator)
        self.assertTrue(any("tiktok_username" in e for e in errors))

    def test_invalid_consent_type_is_error(self) -> None:
        creator = _make_creator(consent_type="unknown")
        errors = validate_creator(creator)
        self.assertTrue(any("consent_type" in e for e in errors))


class GetAllowedCreatorTest(unittest.TestCase):
    def test_owner_consent_type_passes_live_run(self) -> None:
        creator = _make_creator(consent_type="owner")
        allowlist = _make_allowlist(creator)
        result = get_allowed_creator("testuser", "111222333", allowlist, live_run=True)
        self.assertIsNotNone(result)
        self.assertEqual(result["tiktok_username"], "testuser")

    def test_explicit_consent_type_rejected_for_live_run(self) -> None:
        creator = _make_creator(consent_type="explicit")
        allowlist = _make_allowlist(creator)
        result = get_allowed_creator("testuser", "111222333", allowlist, live_run=True)
        self.assertIsNone(result)

    def test_explicit_consent_type_allowed_for_dry_run(self) -> None:
        creator = _make_creator(consent_type="explicit")
        allowlist = _make_allowlist(creator)
        result = get_allowed_creator("testuser", "111222333", allowlist, live_run=False)
        self.assertIsNotNone(result)

    def test_disabled_creator_rejected(self) -> None:
        creator = _make_creator(enabled=False)
        allowlist = _make_allowlist(creator)
        result = get_allowed_creator("testuser", "111222333", allowlist, live_run=True)
        self.assertIsNone(result)

    def test_expired_creator_rejected(self) -> None:
        creator = _make_creator(expires_at="2020-01-01")
        allowlist = _make_allowlist(creator)
        result = get_allowed_creator("testuser", "111222333", allowlist, live_run=True)
        self.assertIsNone(result)

    def test_null_expires_at_treated_as_no_expiry(self) -> None:
        creator = _make_creator(expires_at=None)
        allowlist = _make_allowlist(creator)
        result = get_allowed_creator("testuser", "111222333", allowlist, live_run=True)
        self.assertIsNotNone(result)

    def test_platform_user_id_mismatch_rejected(self) -> None:
        creator = _make_creator(platform_user_id="999999999")
        allowlist = _make_allowlist(creator)
        result = get_allowed_creator("testuser", "111222333", allowlist, live_run=True)
        self.assertIsNone(result)

    def test_missing_consent_reference_rejected(self) -> None:
        creator = _make_creator(consent_reference="")
        allowlist = _make_allowlist(creator)
        result = get_allowed_creator("testuser", "111222333", allowlist, live_run=True)
        self.assertIsNone(result)

    def test_unknown_username_returns_none(self) -> None:
        creator = _make_creator()
        allowlist = _make_allowlist(creator)
        result = get_allowed_creator("unknown", "111222333", allowlist, live_run=True)
        self.assertIsNone(result)

    def test_username_matching_is_case_insensitive(self) -> None:
        creator = _make_creator(tiktok_username="TestUser")
        allowlist = _make_allowlist(creator)
        result = get_allowed_creator("testuser", "111222333", allowlist, live_run=True)
        self.assertIsNotNone(result)


class LoadAllowlistTest(unittest.TestCase):
    def test_load_valid_yaml(self) -> None:
        yaml_path = Path(__file__).resolve().parents[1] / "config" / "tiktok_allowlist.yaml"
        allowlist = load_allowlist(yaml_path)
        self.assertIn("creators", allowlist)
        self.assertIsInstance(allowlist["creators"], list)

    def test_load_nonexistent_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_allowlist("/nonexistent/path.yaml")

    def test_load_normalizes_username(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "allowlist.yaml"
            path.write_text(
                "creators:\n"
                '  - platform_user_id: "1"\n'
                '    tiktok_username: "@ExampleOwner"\n'
                "    consent_type: owner\n"
                '    consent_reference: "owned"\n'
                "    expires_at: null\n",
                encoding="utf-8",
            )
            allowlist = load_allowlist(path)
            self.assertEqual(allowlist["creators"][0]["tiktok_username"], "exampleowner")

    def test_load_invalid_creator_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "allowlist.yaml"
            path.write_text(
                "creators:\n"
                "  - consent_type: owner\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "invalid"):
                load_allowlist(path)

    def test_get_enabled_creators_filters_disabled_entries(self) -> None:
        creators = get_enabled_creators(
            _make_allowlist(
                _make_creator(tiktok_username="enabled", enabled=True),
                _make_creator(tiktok_username="disabled", enabled=False),
            )
        )
        self.assertEqual([creator["tiktok_username"] for creator in creators], ["enabled"])


if __name__ == "__main__":
    unittest.main()
