from __future__ import annotations

from typing import Any, Mapping, Sequence

from post_media import normalize_media_mode


def candidate_sort_key(item: Mapping[str, Any]) -> tuple[float, int, int, int, int, str]:
    return (
        float(item.get("score", 0)),
        int(item.get("views", 0)),
        int(item.get("replies", 0)),
        int(item.get("retweets", 0)),
        int(item.get("likes", 0)),
        str(item.get("created_at", "")),
    )


def sort_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in sorted(candidates, key=candidate_sort_key, reverse=True)]


def candidate_rotation_key(item: Mapping[str, Any], *, selection_mode: str) -> str:
    if selection_mode == "round_robin_account":
        return str(item.get("rotation_key") or item.get("screen_name") or item.get("source_username") or item.get("source_key") or item.get("source_id") or "")
    return str(item.get("source_key") or item.get("source_id") or "")


def deduplicate_source_order(source_order: Sequence[str]) -> list[str]:
    """出現順を保ちつつ空文字と重複を除去する。"""
    seen: set[str] = set()
    result: list[str] = []
    for item in source_order:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def normalize_rotation_source(raw_value: str | None, source_order: Sequence[str]) -> tuple[str, int]:
    normalized_source_order = [item for item in source_order if item]
    if not normalized_source_order:
        return "", 0

    value = str(raw_value or "").strip()
    if value not in normalized_source_order:
        return "", 0

    index = normalized_source_order.index(value)
    return value, (index + 1) % len(normalized_source_order)


def preferred_media_mode_from_previous(raw_value: str | None) -> str:
    previous_mode = normalize_media_mode(raw_value)
    if previous_mode == "image":
        return "text"
    return "image"


def apply_media_preference(
    candidates: Sequence[Mapping[str, Any]],
    *,
    preferred_media_mode: str,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    target_mode = normalize_media_mode(preferred_media_mode)
    ordered_candidates = [dict(item) for item in candidates]
    if target_mode == "any":
        selected = ordered_candidates[:limit]
        return selected, {
            "target_media_mode": "any",
            "selected_media_mode": selected[0].get("media_mode") if selected else None,
            "media_preference_satisfied": False,
        }

    preferred = [
        dict(item)
        for item in ordered_candidates
        if normalize_media_mode(str(item.get("media_mode") or "")) == target_mode
    ]
    fallback = [
        dict(item)
        for item in ordered_candidates
        if normalize_media_mode(str(item.get("media_mode") or "")) != target_mode
    ]
    selected = (preferred or fallback)[:limit]
    selected_media_mode = selected[0].get("media_mode") if selected else None
    return selected, {
        "target_media_mode": target_mode,
        "selected_media_mode": selected_media_mode,
        "media_preference_satisfied": bool(preferred),
    }


def select_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_order: Sequence[str],
    max_candidates: int,
    selection_mode: str,
    previous_source: str = "",
    preferred_media_mode: str = "any",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ordered_candidates = sort_candidates(candidates)
    limit = max(max_candidates, 1)

    if selection_mode not in {"round_robin", "round_robin_account"} or not source_order:
        selected, media = apply_media_preference(
            ordered_candidates,
            preferred_media_mode=preferred_media_mode,
            limit=limit,
        )
        return selected, {
            "selection_mode": "score",
            "source_order": list(source_order),
            "previous_source": "",
            "start_index": 0,
            "selected_source": None,
            "next_source": None,
            **media,
        }

    normalized_source_order = [item for item in source_order if item]
    normalized_previous_source, start_index = normalize_rotation_source(previous_source, normalized_source_order)
    candidates_by_source: dict[str, list[dict[str, Any]]] = {}
    for candidate in ordered_candidates:
        source_key = str(candidate.get("source_key") or candidate.get("source_id") or "")
        if not source_key:
            continue
        rotation_key = candidate_rotation_key(candidate, selection_mode=selection_mode)
        if not rotation_key:
            continue
        candidates_by_source.setdefault(rotation_key, []).append(candidate)

    for offset in range(len(normalized_source_order)):
        source_index = (start_index + offset) % len(normalized_source_order)
        source_key = normalized_source_order[source_index]
        source_candidates = candidates_by_source.get(source_key) or []
        if source_candidates:
            selected, media = apply_media_preference(
                source_candidates,
                preferred_media_mode=preferred_media_mode,
                limit=limit,
            )
            return selected, {
                "selection_mode": selection_mode,
                "source_order": normalized_source_order,
                "previous_source": normalized_previous_source,
                "start_index": start_index,
                "selected_source": source_key,
                "next_source": normalized_source_order[(source_index + 1) % len(normalized_source_order)],
                **media,
            }

    return [], {
        "selection_mode": selection_mode,
        "source_order": normalized_source_order,
        "previous_source": normalized_previous_source,
        "start_index": start_index,
        "selected_source": None,
        "next_source": normalized_source_order[start_index] if normalized_source_order else None,
        "target_media_mode": normalize_media_mode(preferred_media_mode),
        "selected_media_mode": None,
        "media_preference_satisfied": False,
    }
