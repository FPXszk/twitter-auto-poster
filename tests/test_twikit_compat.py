"""Tests for twikit_compat — ClientTransaction fallback logic."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from twikit_compat import (
    ALT_INDICES_PATTERNS,
    ALT_ONDEMAND_HASH_PATTERNS,
    _extract_indices_from_js,
    _extract_ondemand_hash,
    patch_twikit_transaction,
)

# ---------------------------------------------------------------------------
# Realistic test data
# ---------------------------------------------------------------------------

# Old-style ondemand reference (twikit 2.3.3 original regex matches this)
OLD_STYLE_HTML = """<script>{"ondemand.s":"a1b2c3d4e5f6"}</script>"""

# Alternative HTML format (different quoting/spacing)
ALT_STYLE_HTML = """<script>{'ondemand.s': 'fa9e8d7c6b5a'}</script>"""

# Script-src style reference (with trailing "a" suffix)
SCRIPT_SRC_HTML = (
    '<script src="https://abs.twimg.com/responsive-web/client-web/'
    'ondemand.s.deadbeef1234a.js"></script>'
)

# Script-src style reference (without trailing "a" suffix)
SCRIPT_SRC_PLAIN_HTML = (
    '<script src="https://abs.twimg.com/responsive-web/client-web/'
    'ondemand.s.cafe9876.js"></script>'
)

HTML_NO_ONDEMAND = """<html><head><title>X</title></head><body></body></html>"""

# Old-style JS pattern: (e[2], 16)
OLD_STYLE_JS = (
    "var x=function(){return "
    "(e[2], 16)+(e[42], 16)*(e[45], 16);}"
)

# New-style JS pattern: parseInt(e[2], 16)
NEW_STYLE_JS = (
    "var x=function(){return "
    "parseInt(e[2],16)+parseInt(e[42],16)*parseInt(e[45],16);}"
)

# Mixed whitespace parseInt
SPACED_JS = (
    "parseInt( e[ 7 ] , 16 )+parseInt( e[ 19 ] , 16 )"
)

JS_NO_INDICES = "var x = function() { return 42; }"


class ExtractOndemandHashTest(unittest.TestCase):
    """Tests for _extract_ondemand_hash fallback extraction."""

    def test_extracts_hash_from_standard_double_quoted_html(self) -> None:
        result = _extract_ondemand_hash(OLD_STYLE_HTML)
        self.assertEqual(result, "a1b2c3d4e5f6")

    def test_extracts_hash_from_single_quoted_html(self) -> None:
        result = _extract_ondemand_hash(ALT_STYLE_HTML)
        self.assertEqual(result, "fa9e8d7c6b5a")

    def test_extracts_hash_from_script_src(self) -> None:
        result = _extract_ondemand_hash(SCRIPT_SRC_HTML)
        self.assertEqual(result, "deadbeef1234")

    def test_extracts_hash_from_plain_script_src(self) -> None:
        result = _extract_ondemand_hash(SCRIPT_SRC_PLAIN_HTML)
        self.assertEqual(result, "cafe9876")

    def test_returns_none_when_no_ondemand_reference(self) -> None:
        result = _extract_ondemand_hash(HTML_NO_ONDEMAND)
        self.assertIsNone(result)


class ExtractIndicesFromJsTest(unittest.TestCase):
    """Tests for _extract_indices_from_js fallback extraction."""

    def test_matches_parseint_format(self) -> None:
        indices = _extract_indices_from_js(NEW_STYLE_JS)
        self.assertEqual(indices, [2, 42, 45])

    def test_matches_old_paren_format(self) -> None:
        indices = _extract_indices_from_js(OLD_STYLE_JS)
        self.assertEqual(indices, [2, 42, 45])

    def test_matches_spaced_parseint_format(self) -> None:
        indices = _extract_indices_from_js(SPACED_JS)
        self.assertEqual(indices, [7, 19])

    def test_returns_empty_list_when_no_match(self) -> None:
        indices = _extract_indices_from_js(JS_NO_INDICES)
        self.assertEqual(indices, [])


class PatchTwikitTransactionTest(unittest.TestCase):
    """Tests for the monkey-patch mechanism."""

    def test_patch_replaces_get_indices(self) -> None:
        import twikit.x_client_transaction.transaction as txmod

        original = txmod.ClientTransaction.get_indices
        try:
            import twikit_compat
            twikit_compat._original_get_indices = None
            patch_twikit_transaction()
            self.assertIsNot(txmod.ClientTransaction.get_indices, original)
            self.assertTrue(
                hasattr(txmod.ClientTransaction.get_indices, "_twikit_compat_patched")
            )
        finally:
            txmod.ClientTransaction.get_indices = original
            twikit_compat._original_get_indices = None

    def test_patch_is_idempotent_when_called_twice(self) -> None:
        import twikit.x_client_transaction.transaction as txmod

        original = txmod.ClientTransaction.get_indices
        try:
            import twikit_compat
            twikit_compat._original_get_indices = None
            patch_twikit_transaction()
            first_patched = txmod.ClientTransaction.get_indices
            patch_twikit_transaction()
            second_patched = txmod.ClientTransaction.get_indices
            self.assertIs(first_patched, second_patched)
        finally:
            txmod.ClientTransaction.get_indices = original
            twikit_compat._original_get_indices = None


class RobustGetIndicesTest(unittest.TestCase):
    """Tests for the robust fallback get_indices wrapper."""

    def test_passthrough_on_success(self) -> None:
        """Original get_indices succeeds → no fallback triggered."""
        import twikit.x_client_transaction.transaction as txmod

        original = txmod.ClientTransaction.get_indices

        async def fake_original(self_, response, session, headers):
            return 2, [42, 45]

        try:
            import twikit_compat
            twikit_compat._original_get_indices = None
            txmod.ClientTransaction.get_indices = fake_original
            patch_twikit_transaction()

            ct = txmod.ClientTransaction()
            result = asyncio.run(
                txmod.ClientTransaction.get_indices(ct, MagicMock(), MagicMock(), {})
            )
            self.assertEqual(result, (2, [42, 45]))
        finally:
            txmod.ClientTransaction.get_indices = original
            twikit_compat._original_get_indices = None

    def test_fallback_on_key_byte_error(self) -> None:
        """Original raises KEY_BYTE error → fallback uses alternative regex."""
        import twikit.x_client_transaction.transaction as txmod

        original = txmod.ClientTransaction.get_indices

        async def failing_original(self_, response, session, headers):
            raise Exception("Couldn't get KEY_BYTE indices")

        mock_response = MagicMock()
        mock_response.text = NEW_STYLE_JS

        mock_session = MagicMock()
        mock_session.request = AsyncMock(return_value=mock_response)

        import bs4
        home_html = (
            '<html><head>'
            '<script>{"ondemand.s":"abc123"}</script>'
            '</head><body></body></html>'
        )
        home_soup = bs4.BeautifulSoup(home_html, "html.parser")

        try:
            import twikit_compat
            twikit_compat._original_get_indices = None
            txmod.ClientTransaction.get_indices = failing_original
            patch_twikit_transaction()

            ct = txmod.ClientTransaction()
            result = asyncio.run(
                txmod.ClientTransaction.get_indices(ct, home_soup, mock_session, {})
            )
            self.assertEqual(result, (2, [42, 45]))
        finally:
            txmod.ClientTransaction.get_indices = original
            twikit_compat._original_get_indices = None

    def test_fallback_raises_when_no_patterns_match(self) -> None:
        """Fallback also fails → re-raises with compat context."""
        import twikit.x_client_transaction.transaction as txmod

        original = txmod.ClientTransaction.get_indices

        async def failing_original(self_, response, session, headers):
            raise Exception("Couldn't get KEY_BYTE indices")

        mock_response = MagicMock()
        mock_response.text = JS_NO_INDICES

        mock_session = MagicMock()
        mock_session.request = AsyncMock(return_value=mock_response)

        import bs4
        home_soup = bs4.BeautifulSoup(HTML_NO_ONDEMAND, "html.parser")

        try:
            import twikit_compat
            twikit_compat._original_get_indices = None
            txmod.ClientTransaction.get_indices = failing_original
            patch_twikit_transaction()

            ct = txmod.ClientTransaction()
            with self.assertRaisesRegex(Exception, "compat.*ondemand hash not found"):
                asyncio.run(
                    txmod.ClientTransaction.get_indices(
                        ct, home_soup, mock_session, {}
                    )
                )
        finally:
            txmod.ClientTransaction.get_indices = original
            twikit_compat._original_get_indices = None

    def test_non_key_byte_errors_propagate(self) -> None:
        """Non-KEY_BYTE exceptions are not caught by fallback."""
        import twikit.x_client_transaction.transaction as txmod

        original = txmod.ClientTransaction.get_indices

        async def unrelated_error(self_, response, session, headers):
            raise RuntimeError("network timeout")

        try:
            import twikit_compat
            twikit_compat._original_get_indices = None
            txmod.ClientTransaction.get_indices = unrelated_error
            patch_twikit_transaction()

            ct = txmod.ClientTransaction()
            with self.assertRaisesRegex(RuntimeError, "network timeout"):
                asyncio.run(
                    txmod.ClientTransaction.get_indices(
                        ct, MagicMock(), MagicMock(), {}
                    )
                )
        finally:
            txmod.ClientTransaction.get_indices = original
            twikit_compat._original_get_indices = None


if __name__ == "__main__":
    unittest.main()
