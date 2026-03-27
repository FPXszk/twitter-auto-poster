from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Mapping

from post_filters import parse_created_at

DEFAULT_SCORE_WEIGHTS = {
    "likes": 1.0,
    "retweets": 1.0,
    "replies": 1.0,
    "views": 1.0,
    "velocity": 0.0,
    "freshness": 0.0,
    "image_bonus": 0.0,
    "author_virality": 0.0,
}


def coerce_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        compact = value.replace(",", "").strip()
        if compact.isdigit():
            return int(compact)
        match = re.search(r"\d[\d,]*", value)
        if match:
            return int(match.group(0).replace(",", ""))
    return 0


def nested_get(mapping: Any, *path: str) -> Any:
    current = mapping
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def extract_metric(item: Mapping[str, Any], paths: list[tuple[str, ...]]) -> int:
    values = [nested_get(item, *path) for path in paths]
    return max((coerce_int(value) for value in values), default=0)


def extract_candidate_metrics(item: Mapping[str, Any]) -> dict[str, int]:
    return {
        "likes": extract_metric(item, [("metrics", "likes"), ("likes",), ("legacy", "favorite_count")]),
        "retweets": extract_metric(item, [("metrics", "retweets"), ("retweets",), ("legacy", "retweet_count")]),
        "replies": extract_metric(item, [("metrics", "replies"), ("replies",), ("legacy", "reply_count")]),
        "views": extract_metric(
            item,
            [
                ("metrics", "views"),
                ("metrics", "viewCount"),
                ("views",),
                ("viewCount",),
                ("view_count",),
                ("views", "count"),
                ("legacy", "views"),
                ("legacy", "view_count"),
            ],
        ),
    }


def normalize_score_weights(raw_weights: Mapping[str, Any] | None) -> dict[str, float]:
    weights = dict(DEFAULT_SCORE_WEIGHTS)
    if not raw_weights:
        return weights

    for key in DEFAULT_SCORE_WEIGHTS:
        try:
            weights[key] = float(raw_weights.get(key, weights[key]))
        except (TypeError, ValueError):
            continue
    return weights


def calculate_freshness_bonus(
    *,
    created_at: str,
    freshness_weight: float,
    max_age_hours: float | None,
    now: datetime | None = None,
) -> float:
    if freshness_weight <= 0 or max_age_hours is None or max_age_hours <= 0:
        return 0.0

    parsed = parse_created_at(created_at)
    if parsed is None:
        return 0.0

    current = now or datetime.now(timezone.utc)
    age_hours = max((current - parsed).total_seconds() / 3600, 0.0)
    remaining_hours = max(max_age_hours - age_hours, 0.0)
    return remaining_hours * freshness_weight


def calculate_velocity_bonus(
    metrics: Mapping[str, int],
    *,
    created_at: str,
    velocity_weight: float,
    now: datetime | None = None,
) -> float:
    if velocity_weight <= 0:
        return 0.0

    parsed = parse_created_at(created_at)
    if parsed is None:
        return 0.0

    current = now or datetime.now(timezone.utc)
    age_hours = max((current - parsed).total_seconds() / 3600, 1.0)
    weighted_interactions = (
        metrics.get("likes", 0)
        + (metrics.get("retweets", 0) * 2.0)
        + (metrics.get("replies", 0) * 3.0)
        + (metrics.get("views", 0) * 0.01)
    )
    return (weighted_interactions / age_hours) * velocity_weight


def calculate_score(
    metrics: Mapping[str, int],
    raw_weights: Mapping[str, Any] | None = None,
    *,
    created_at: str = "",
    max_age_hours: float | None = None,
    source_boost: float = 0.0,
    now: datetime | None = None,
    has_image: bool = False,
    author_metrics: Mapping[str, Any] | None = None,
) -> tuple[float, dict[str, float]]:
    weights = normalize_score_weights(raw_weights)
    freshness = calculate_freshness_bonus(
        created_at=created_at,
        freshness_weight=weights["freshness"],
        max_age_hours=max_age_hours,
        now=now,
    )
    velocity = calculate_velocity_bonus(
        metrics,
        created_at=created_at,
        velocity_weight=weights["velocity"],
        now=now,
    )
    followers = max(coerce_int((author_metrics or {}).get("followers")), 1)
    weighted_author_engagement = (
        metrics.get("likes", 0)
        + (metrics.get("retweets", 0) * 3.0)
        + (metrics.get("replies", 0) * 4.0)
        + (metrics.get("views", 0) * 0.02)
    )
    author_virality = (weighted_author_engagement / followers) * weights["author_virality"]
    breakdown = {
        "likes": metrics.get("likes", 0) * weights["likes"],
        "retweets": metrics.get("retweets", 0) * weights["retweets"],
        "replies": metrics.get("replies", 0) * weights["replies"],
        "views": metrics.get("views", 0) * weights["views"],
        "velocity": velocity,
        "freshness": freshness,
        "image_bonus": weights["image_bonus"] if has_image else 0.0,
        "author_virality": author_virality,
        "source_boost": float(source_boost),
    }
    score = sum(breakdown.values())
    return score, breakdown
