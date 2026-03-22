from __future__ import annotations

from typing import Any, Mapping, Sequence


def candidate_sort_key(item: Mapping[str, Any]) -> tuple[float, int, int, int, str]:
    return (
        float(item.get("score", 0)),
        int(item.get("views", 0)),
        int(item.get("retweets", 0)),
        int(item.get("likes", 0)),
        str(item.get("created_at", "")),
    )


def sort_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in sorted(candidates, key=candidate_sort_key, reverse=True)]


def normalize_rotation_source(raw_value: str | None, source_order: Sequence[str]) -> tuple[str, int]:
    normalized_source_order = [item for item in source_order if item]
    if not normalized_source_order:
        return "", 0

    value = str(raw_value or "").strip()
    if value not in normalized_source_order:
        return "", 0

    index = normalized_source_order.index(value)
    return value, (index + 1) % len(normalized_source_order)


def select_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_order: Sequence[str],
    max_candidates: int,
    selection_mode: str,
    previous_source: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ordered_candidates = sort_candidates(candidates)
    limit = max(max_candidates, 1)

    if selection_mode != "round_robin" or not source_order:
        return ordered_candidates[:limit], {
            "selection_mode": "score",
            "source_order": list(source_order),
            "previous_source": "",
            "start_index": 0,
            "selected_source": None,
            "next_source": None,
        }

    normalized_source_order = [item for item in source_order if item]
    normalized_previous_source, start_index = normalize_rotation_source(previous_source, normalized_source_order)
    candidates_by_source: dict[str, list[dict[str, Any]]] = {}
    for candidate in ordered_candidates:
        source_key = str(candidate.get("source_key") or candidate.get("source_id") or "")
        if not source_key:
            continue
        candidates_by_source.setdefault(source_key, []).append(candidate)

    for offset in range(len(normalized_source_order)):
        source_index = (start_index + offset) % len(normalized_source_order)
        source_key = normalized_source_order[source_index]
        source_candidates = candidates_by_source.get(source_key) or []
        if source_candidates:
            return source_candidates[:limit], {
                "selection_mode": "round_robin",
                "source_order": normalized_source_order,
                "previous_source": normalized_previous_source,
                "start_index": start_index,
                "selected_source": source_key,
                "next_source": normalized_source_order[(source_index + 1) % len(normalized_source_order)],
            }

    return [], {
        "selection_mode": "round_robin",
        "source_order": normalized_source_order,
        "previous_source": normalized_previous_source,
        "start_index": start_index,
        "selected_source": None,
        "next_source": normalized_source_order[start_index] if normalized_source_order else None,
    }
