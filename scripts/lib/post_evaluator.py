from __future__ import annotations

import re
from typing import Any

from post_summary import estimate_x_post_length

URL_PATTERN = re.compile(r"https?://\S+")
MEANINGFUL_CHAR_PATTERN = re.compile(r"[0-9A-Za-zぁ-んァ-ヶ一-龯]")
REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{7,}")


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

    return {
        "ok": not reasons,
        "reasons": reasons,
        "estimated_length": estimated_length,
        "source_length": estimate_x_post_length(normalized_source) if normalized_source else 0,
    }
