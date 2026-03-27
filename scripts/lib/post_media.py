from __future__ import annotations

from typing import Any, Mapping, Sequence

IMAGE_MEDIA_TYPES = {"photo", "image"}
MEDIA_MODES = {"any", "image", "text"}


def nested_get(mapping: Any, *path: str) -> Any:
    current = mapping
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def normalize_media_mode(raw_value: str | None) -> str:
    value = str(raw_value or "").strip().lower()
    if value in MEDIA_MODES:
        return value
    return "any"


def _coerce_media_entries(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        nested = value.get("media")
        if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes)):
            return [item for item in nested if isinstance(item, Mapping)]
    return []


def extract_media_entries(item: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    entries: list[Mapping[str, Any]] = []
    seen_keys: set[str] = set()
    for candidate in (
        item.get("media"),
        nested_get(item, "entities", "media"),
        nested_get(item, "extendedEntities", "media"),
        nested_get(item, "legacy", "entities", "media"),
        nested_get(item, "legacy", "extended_entities", "media"),
        nested_get(item, "attachments", "media"),
        nested_get(item, "attachments", "media_entities"),
    ):
        for media in _coerce_media_entries(candidate):
            key = str(
                media.get("id")
                or media.get("media_key")
                or media.get("expanded_url")
                or media.get("url")
                or media
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            entries.append(media)
    return entries


def media_type(media: Mapping[str, Any]) -> str:
    raw_value = str(
        media.get("type")
        or media.get("mediaType")
        or media.get("media_type")
        or ""
    ).strip().lower()
    if "photo" in raw_value or "image" in raw_value:
        return "photo"
    return raw_value


def extract_candidate_media(
    item: Mapping[str, Any],
    *,
    fallback_mode: str = "any",
) -> dict[str, Any]:
    entries = extract_media_entries(item)
    media_types = [media_type(media) for media in entries if media_type(media)]
    has_image = any(media_type_name in IMAGE_MEDIA_TYPES for media_type_name in media_types)
    normalized_fallback = normalize_media_mode(fallback_mode)

    if has_image:
        selected_mode = "image"
        classification_source = "payload"
    elif entries:
        selected_mode = "text"
        classification_source = "payload"
    elif normalized_fallback in {"image", "text"}:
        selected_mode = normalized_fallback
        classification_source = "query_hint"
    else:
        selected_mode = "text"
        classification_source = "default"

    return {
        "media_mode": selected_mode,
        "has_image": selected_mode == "image",
        "has_media": bool(entries),
        "media_types": sorted(set(media_types)),
        "classification_source": classification_source,
    }
