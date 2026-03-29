"""Compatibility shim for twikit ClientTransaction.

Patches ``ClientTransaction.get_indices`` so that when the original regex
patterns fail (``"Couldn't get KEY_BYTE indices"``), a fallback set of
broader patterns is tried.  This addresses the breakage reported in twikit
issue #408 where Twitter changed the ``ondemand.s.*.js`` structure around
2026-03-18.

Usage — call once before creating ``twikit.Client()``:

    from twikit_compat import patch_twikit_transaction
    patch_twikit_transaction()
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── Alternative regex patterns ────────────────────────────────────────────

ALT_ONDEMAND_HASH_PATTERNS: list[re.Pattern[str]] = [
    # Standard JS object: "ondemand.s":"hash" or 'ondemand.s':'hash'
    re.compile(r"""['"]ondemand\.s['"]\s*:\s*['"]([a-f0-9]+)['"]""", re.MULTILINE),
    # Script src: ondemand.s.HASHa.js (twikit appends "a.js" to the hash)
    re.compile(r"""ondemand\.s\.([a-f0-9]+)a\.js""", re.MULTILINE),
    # Script src: ondemand.s.HASH.js (no trailing "a" suffix)
    re.compile(r"""ondemand\.s\.([a-f0-9]+)\.js""", re.MULTILINE),
]

ALT_INDICES_PATTERNS: list[re.Pattern[str]] = [
    # parseInt(e[12], 16) — new format seen after 2026-03-18
    re.compile(
        r"""parseInt\(\s*\w+\[\s*(\d{1,3})\s*\]\s*,\s*16\s*\)""",
        re.MULTILINE,
    ),
    # (e[12], 16) — broader version of the twikit original
    re.compile(
        r"""\(\s*\w+\[\s*(\d{1,3})\s*\]\s*,\s*16\s*\)""",
        re.MULTILINE,
    ),
]


def _extract_ondemand_hash(html_text: str) -> str | None:
    """Try alternative patterns to extract the ondemand file hash."""
    for pattern in ALT_ONDEMAND_HASH_PATTERNS:
        match = pattern.search(html_text)
        if match:
            return match.group(1)
    return None


def _extract_indices_from_js(js_text: str) -> list[int]:
    """Try alternative patterns to extract KEY_BYTE indices from JS."""
    for pattern in ALT_INDICES_PATTERNS:
        matches = list(pattern.finditer(js_text))
        if matches:
            return [int(m.group(1)) for m in matches]
    return []


# ── Monkey-patch machinery ────────────────────────────────────────────────

_original_get_indices: Any = None


async def _robust_get_indices(
    self: Any,
    home_page_response: Any,
    session: Any,
    headers: dict[str, str],
) -> tuple[int, list[int]]:
    """Drop-in async replacement for ``ClientTransaction.get_indices``.

    Tries the original implementation first.  If it raises an exception
    mentioning ``KEY_BYTE``, falls back to broader regex patterns and
    re-fetches the ondemand JS file.
    """
    try:
        return await _original_get_indices(self, home_page_response, session, headers)
    except Exception as original_error:
        if "KEY_BYTE" not in str(original_error):
            raise
        logger.warning(
            "twikit_compat: original get_indices failed (%s), trying fallback",
            original_error,
        )

    # ── Fallback path ─────────────────────────────────────────────────
    response_text = str(home_page_response)

    from twikit.x_client_transaction.transaction import ON_DEMAND_FILE_REGEX

    on_demand_match = ON_DEMAND_FILE_REGEX.search(response_text)
    on_demand_hash = (
        on_demand_match.group(1) if on_demand_match else _extract_ondemand_hash(response_text)
    )

    if not on_demand_hash:
        raise Exception("Couldn't get KEY_BYTE indices (compat: ondemand hash not found)")

    url_variants = [
        f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{on_demand_hash}a.js",
        f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{on_demand_hash}.js",
    ]

    key_byte_indices: list[int] = []
    for url in url_variants:
        try:
            resp = await session.request(method="GET", url=url, headers=headers)
            js_text = resp.text if hasattr(resp, "text") else str(resp)
            key_byte_indices = _extract_indices_from_js(js_text)
            if key_byte_indices:
                break
        except Exception:
            continue

    if not key_byte_indices:
        raise Exception(
            "Couldn't get KEY_BYTE indices (compat: no fallback patterns matched)"
        )

    logger.info(
        "twikit_compat: fallback extracted %d indices", len(key_byte_indices)
    )
    return key_byte_indices[0], key_byte_indices[1:]


_robust_get_indices._twikit_compat_patched = True  # type: ignore[attr-defined]


def patch_twikit_transaction() -> None:
    """Monkey-patch ``ClientTransaction.get_indices`` with fallback logic.

    Safe to call multiple times — the patch is applied only once.
    Uses a sentinel attribute to prevent double-wrapping even under
    concurrent calls.
    """
    global _original_get_indices

    from twikit.x_client_transaction.transaction import ClientTransaction

    if getattr(ClientTransaction.get_indices, "_twikit_compat_patched", False):
        return

    if _original_get_indices is not None:
        return

    _original_get_indices = ClientTransaction.get_indices
    ClientTransaction.get_indices = _robust_get_indices  # type: ignore[assignment]
