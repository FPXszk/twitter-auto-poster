from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Mapping

DEFAULT_NOISE_KEYWORDS = [
    "giveaway",
    "airdrop",
    "telegram",
    "discord",
    "promo",
    "promote",
    "follow me",
    "dm me",
]


def normalize_filters(raw_filters: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = {
        "max_age_hours": None,
        "required_terms": [],
        "exclude_keywords": list(DEFAULT_NOISE_KEYWORDS),
    }

    if not raw_filters:
        return payload

    if raw_filters.get("max_age_hours") is not None:
        payload["max_age_hours"] = float(raw_filters["max_age_hours"])

    payload["required_terms"] = [str(item).strip() for item in raw_filters.get("required_terms", []) if str(item).strip()]

    configured_keywords = [str(item).strip() for item in raw_filters.get("exclude_keywords", []) if str(item).strip()]
    payload["exclude_keywords"] = list(dict.fromkeys([*payload["exclude_keywords"], *configured_keywords]))
    return payload


def parse_created_at(raw_value: str) -> datetime | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def candidate_rejection_reasons(*, text: str, created_at: str, raw_filters: Mapping[str, Any] | None) -> list[str]:
    filters = normalize_filters(raw_filters)
    lowered_text = text.casefold()
    reasons: list[str] = []

    max_age_hours = filters.get("max_age_hours")
    if max_age_hours is not None:
        parsed = parse_created_at(created_at)
        if parsed is not None and parsed < datetime.now(timezone.utc) - timedelta(hours=max_age_hours):
            reasons.append("tweet is older than max_age_hours")

    required_terms = filters.get("required_terms") or []
    if required_terms and not any(term.casefold() in lowered_text for term in required_terms):
        reasons.append("tweet does not include any required_terms")

    exclude_keywords = filters.get("exclude_keywords") or []
    matched_keywords = [term for term in exclude_keywords if term.casefold() in lowered_text]
    if matched_keywords:
        reasons.append(f"tweet matched exclude_keywords: {', '.join(matched_keywords[:3])}")

    if len(re.findall(r"\$[A-Za-z]{1,6}", text)) >= 5:
        reasons.append("tweet looks noisy due to too many cashtags")

    return reasons
