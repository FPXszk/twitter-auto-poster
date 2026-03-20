from __future__ import annotations

import re
from typing import Any, Mapping

DEFAULT_SCORE_WEIGHTS = {
    "likes": 1.0,
    "retweets": 1.0,
    "views": 1.0,
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


def calculate_score(metrics: Mapping[str, int], raw_weights: Mapping[str, Any] | None = None) -> tuple[float, dict[str, float]]:
    weights = normalize_score_weights(raw_weights)
    breakdown = {
        "likes": metrics.get("likes", 0) * weights["likes"],
        "retweets": metrics.get("retweets", 0) * weights["retweets"],
        "views": metrics.get("views", 0) * weights["views"],
    }
    score = breakdown["likes"] + breakdown["retweets"] + breakdown["views"]
    return score, breakdown
