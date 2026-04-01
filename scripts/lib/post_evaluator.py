from __future__ import annotations

import re
from typing import Any

from post_summary import estimate_x_post_length

URL_PATTERN = re.compile(r"https?://\S+")
MEANINGFUL_CHAR_PATTERN = re.compile(r"[0-9A-Za-zぁ-んァ-ヶ一-龯]")
REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{7,}")

# LLM refusal/safety boilerplate patterns (case-insensitive).
# Each pattern is anchored to avoid false positives on normal text.
_LLM_REFUSAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"i[''']?m sorry,? but i cannot", re.IGNORECASE),
    re.compile(r"i can[''']?t help with that", re.IGNORECASE),
    re.compile(r"i[''']?m unable to assist", re.IGNORECASE),
    re.compile(r"sorry,? i can[''']?t provide", re.IGNORECASE),
    re.compile(r"i[''']?m not able to help", re.IGNORECASE),
    re.compile(r"as an ai(?: language)? model,? i cannot", re.IGNORECASE),
    re.compile(r"i apologize,? but i[''']?m unable to", re.IGNORECASE),
    re.compile(r"i cannot generate content", re.IGNORECASE),
    re.compile(r"i[''']?m sorry,? i can[''']?t do that", re.IGNORECASE),
    re.compile(r"i can[''']?t assist with that", re.IGNORECASE),
    re.compile(r"i[''']?m unable to fulfill", re.IGNORECASE),
)


def _is_llm_refusal(text: str) -> bool:
    """Return True if *text* matches a known LLM refusal/safety pattern."""
    # Normalize smart/curly quotes to ASCII so patterns match both forms.
    normalized = text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    for pattern in _LLM_REFUSAL_PATTERNS:
        if pattern.search(normalized):
            return True
    return False


def evaluate_summary(
    summary_text: str,
    *,
    source_text: str = "",
    max_length: int = 280,
    min_meaningful_chars: int = 4,
) -> dict[str, Any]:
    normalized_summary = str(summary_text or "").strip()
    normalized_source = str(source_text or "").strip()
    reasons: list[str] = []
    estimated_length = estimate_x_post_length(normalized_summary)

    if not normalized_summary:
        reasons.append("empty_summary")
    else:
        if estimated_length > max(max_length, 0):
            reasons.append("summary_too_long")
        if URL_PATTERN.search(normalized_summary):
            reasons.append("contains_url")
        if len(MEANINGFUL_CHAR_PATTERN.findall(normalized_summary)) < max(min_meaningful_chars, 1):
            reasons.append("insufficient_content")
        if REPEATED_CHAR_PATTERN.search(normalized_summary):
            reasons.append("excessive_repetition")
        if _is_llm_refusal(normalized_summary):
            reasons.append("llm_refusal")

    return {
        "ok": not reasons,
        "reasons": reasons,
        "estimated_length": estimated_length,
        "source_length": estimate_x_post_length(normalized_source) if normalized_source else 0,
    }
