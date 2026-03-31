from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from post_filters import parse_created_at
from tiktok_allowlist import get_allowed_creator

logger = logging.getLogger(__name__)

DEFAULT_TIKTOK_FILTERS = {
    "max_age_hours": None,
    "required_terms": [],
    "exclude_keywords": [],
    "min_engagement": 0,
    "min_likes": 0,
    "min_views": 0,
    "min_replies": 0,
    "min_retweets": 0,
}


def normalize_tiktok_filters(raw_filters: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize TikTok-specific filter configuration with defaults."""
    payload = dict(DEFAULT_TIKTOK_FILTERS)
    if not raw_filters:
        return payload

    if raw_filters.get("max_age_hours") is not None:
        payload["max_age_hours"] = float(raw_filters["max_age_hours"])

    payload["required_terms"] = [
        str(item).strip()
        for item in raw_filters.get("required_terms", [])
        if str(item).strip()
    ]
    payload["exclude_keywords"] = [
        str(item).strip()
        for item in raw_filters.get("exclude_keywords", [])
        if str(item).strip()
    ]
    payload["min_engagement"] = int(raw_filters.get("min_engagement") or 0)
    for key in ("min_likes", "min_views", "min_replies", "min_retweets"):
        payload[key] = int(raw_filters.get(key) or 0)

    return payload


def candidate_rejection_reasons(
    *,
    video: Mapping[str, Any] | None = None,
    item: Mapping[str, Any] | None = None,
    raw_filters: Mapping[str, Any] | None,
    allowlist: Mapping[str, Any] | None = None,
    allowed_creator: Mapping[str, Any] | None = None,
    live_run: bool = True,
    now: datetime | None = None,
) -> list[str]:
    """Return a list of rejection reasons for a TikTok video candidate.

    Supports both the new API (video=, allowlist=) and the legacy API
    (item=, allowed_creator=) for backward compatibility with tiktok_pipeline.
    """
    candidate = video or item or {}
    reasons: list[str] = []

    # Allowlist check: new API uses allowlist mapping, legacy uses pre-resolved allowed_creator
    if allowlist is not None:
        author = candidate.get("author") or {}
        username = str(author.get("username") or "").strip()
        platform_user_id = str(author.get("platform_user_id") or "").strip()
        resolved_creator = get_allowed_creator(
            username, platform_user_id, allowlist, live_run=live_run, now=now,
        )
        if resolved_creator is None:
            reasons.append("creator is not in allowlist")
    elif allowed_creator is not None:
        if live_run and str(allowed_creator.get("consent_type") or "") != "owner":
            reasons.append("creator is not owner-consented for live posting")
    else:
        reasons.append("creator is not in allowlist")

    filters = normalize_tiktok_filters(raw_filters)

    # Build combined text from title + description
    title = str(candidate.get("title") or "").strip()
    description = str(candidate.get("description") or "").strip()
    text = str(candidate.get("text") or "").strip()
    combined_text = " ".join([title, description, text]).strip()
    lowered_text = combined_text.casefold()

    # Required terms check
    required_terms = filters.get("required_terms") or []
    if required_terms and not any(term.casefold() in lowered_text for term in required_terms):
        reasons.append("video does not include any required_terms")

    # Age check
    created_at_value = str(candidate.get("created_at") or "")
    parsed = parse_created_at(created_at_value)
    max_age_hours = filters.get("max_age_hours")
    if max_age_hours is not None and parsed is not None:
        if parsed < (now or datetime.now(timezone.utc)) - timedelta(hours=max_age_hours):
            reasons.append("video is older than max_age_hours")

    # Keyword exclusion check
    exclude_keywords = filters.get("exclude_keywords") or []
    matched = [term for term in exclude_keywords if term.casefold() in lowered_text]
    if matched:
        reasons.append(f"video matched exclude_keywords: {', '.join(matched[:3])}")

    # Engagement check (combined metric)
    metrics = candidate.get("metrics") or {}
    total_engagement = (
        int(metrics.get("likes") or 0)
        + int(metrics.get("views") or 0)
        + int(metrics.get("retweets") or 0)
        + int(metrics.get("replies") or 0)
    )
    min_engagement = int(filters.get("min_engagement") or 0)
    if total_engagement < min_engagement:
        reasons.append(f"video is below min_engagement ({total_engagement} < {min_engagement})")

    # Per-metric minimum checks (legacy support)
    checks = {
        "min_likes": int(metrics.get("likes") or 0),
        "min_views": int(metrics.get("views") or 0),
        "min_replies": int(metrics.get("replies") or 0),
        "min_retweets": int(metrics.get("retweets") or 0),
    }
    for key, actual in checks.items():
        minimum = int(filters.get(key) or 0)
        if actual < minimum:
            reasons.append(f"video is below {key}")

    return reasons
