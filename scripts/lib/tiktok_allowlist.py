from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

logger = logging.getLogger(__name__)

ALLOWED_TOP_LEVEL_KEYS = {"creators"}
ALLOWED_CREATOR_KEYS = {
    "platform_user_id",
    "tiktok_username",
    "enabled",
    "consent_type",
    "consent_reference",
    "consent_checked_at",
    "expires_at",
    "max_results",
    "score_boost",
}
VALID_CONSENT_TYPES = {"owner", "explicit"}


def _parse_datetime(raw_value: str | None) -> datetime | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_username(raw_value: str | None) -> str:
    return str(raw_value or "").strip().lstrip("@").casefold()


def validate_creator(creator: Mapping[str, Any]) -> list[str]:
    """Return a list of validation errors for a single creator entry."""
    errors: list[str] = []

    if not str(creator.get("platform_user_id") or "").strip():
        errors.append("missing required field: platform_user_id")

    if not str(creator.get("tiktok_username") or "").strip():
        errors.append("missing required field: tiktok_username")

    consent_type = str(creator.get("consent_type") or "").strip().lower()
    if consent_type not in VALID_CONSENT_TYPES:
        errors.append(f"invalid consent_type: must be one of {sorted(VALID_CONSENT_TYPES)}")

    if not str(creator.get("consent_reference") or "").strip():
        errors.append("missing required field: consent_reference")

    return errors


def load_allowlist(path: str | Path) -> dict[str, Any]:
    """Load and validate a TikTok allowlist YAML file."""
    allowlist_path = Path(path)
    if not allowlist_path.exists():
        raise FileNotFoundError(f"allowlist file not found: {allowlist_path}")

    payload = yaml.safe_load(allowlist_path.read_text(encoding="utf-8")) or {}

    unexpected_top_level = sorted(set(payload) - ALLOWED_TOP_LEVEL_KEYS)
    if unexpected_top_level:
        raise ValueError(
            f"{allowlist_path} contains unsupported keys: {', '.join(unexpected_top_level)}"
        )

    creators = payload.get("creators") or []
    if not isinstance(creators, list):
        raise ValueError(f"{allowlist_path} creators must be a list")

    normalized_creators: list[dict[str, Any]] = []
    for index, creator in enumerate(creators, start=1):
        if not isinstance(creator, Mapping):
            raise ValueError(f"{allowlist_path} creator #{index} must be a mapping")

        unexpected_creator_keys = sorted(set(creator) - ALLOWED_CREATOR_KEYS)
        if unexpected_creator_keys:
            raise ValueError(
                f"{allowlist_path} creator #{index} contains unsupported keys: {', '.join(unexpected_creator_keys)}"
            )

        errors = validate_creator(creator)
        if errors:
            raise ValueError(f"{allowlist_path} creator #{index} invalid: {'; '.join(errors)}")

        normalized_creators.append(
            {
                "platform_user_id": str(creator.get("platform_user_id") or "").strip(),
                "tiktok_username": normalize_username(creator.get("tiktok_username")),
                "enabled": bool(creator.get("enabled", True)),
                "consent_type": str(creator.get("consent_type") or "").strip().lower(),
                "consent_reference": str(creator.get("consent_reference") or "").strip(),
                "consent_checked_at": str(creator.get("consent_checked_at") or "").strip(),
                "expires_at": str(creator.get("expires_at") or "").strip(),
                "max_results": int(creator.get("max_results") or 10),
                "score_boost": float(creator.get("score_boost") or 0.0),
            }
        )

    return {"creators": normalized_creators}


def creator_is_active(
    creator: Mapping[str, Any],
    *,
    platform_user_id: str,
    live_run: bool,
    now: datetime | None = None,
) -> bool:
    if not creator.get("enabled", True):
        return False
    if live_run and str(creator.get("consent_type") or "") != "owner":
        return False
    if str(creator.get("platform_user_id") or "").strip() != str(platform_user_id or "").strip():
        return False
    if not str(creator.get("consent_reference") or "").strip():
        return False
    expires_at = _parse_datetime(str(creator.get("expires_at") or "").strip())
    if expires_at is not None and expires_at < (now or datetime.now(timezone.utc)):
        return False
    return True


def get_allowed_creator(
    username: str,
    platform_user_id: str,
    allowlist: Mapping[str, Any],
    *,
    live_run: bool = True,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Return the creator dict if allowed, None otherwise."""
    normalized_username = normalize_username(username)
    for creator in allowlist.get("creators") or []:
        if normalize_username(creator.get("tiktok_username")) != normalized_username:
            continue
        if creator_is_active(creator, platform_user_id=platform_user_id, live_run=live_run, now=now):
            return dict(creator)
        return None
    return None


def get_enabled_creators(allowlist: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(creator)
        for creator in allowlist.get("creators") or []
        if bool(creator.get("enabled", True))
    ]
