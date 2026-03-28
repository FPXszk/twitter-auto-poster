from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TWITTER_BIN = PROJECT_ROOT / "python" / ".venv" / "bin" / "twitter"


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
    return 0


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return False


def nested_get(mapping: Any, *path: str) -> Any:
    current = mapping
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def resolve_twitter_bin(
    *,
    env: Mapping[str, str] | None = None,
    default_bin: Path = DEFAULT_TWITTER_BIN,
    which: Callable[[str], str | None] | None = None,
) -> str:
    env_map = os.environ if env is None else env
    which_fn = shutil.which if which is None else which

    configured_bin = str(env_map.get("TWITTER_BIN") or "").strip()
    if configured_bin:
        if "/" in configured_bin:
            candidate = Path(configured_bin).expanduser()
            if is_executable_file(candidate):
                return str(candidate)
            raise RuntimeError(f"twitter-cli executable not found: {configured_bin}")

        resolved = which_fn(configured_bin)
        if resolved:
            return resolved
        raise RuntimeError(f"required command not found: {configured_bin}")

    if is_executable_file(default_bin):
        return str(default_bin)

    fallback = which_fn("twitter")
    if fallback:
        return fallback

    raise RuntimeError(f"twitter-cli not found. expected {default_bin} or a TWITTER_BIN override")


def extract_author_metrics(item: Mapping[str, Any]) -> dict[str, Any]:
    author = item.get("author") if isinstance(item.get("author"), Mapping) else {}
    return {
        "screen_name": str(author.get("screenName") or author.get("screen_name") or "").strip().lstrip("@"),
        "verified": coerce_bool(author.get("verified") or author.get("isBlueVerified") or author.get("is_blue_verified")),
        "followers": max(
            coerce_int(author.get("followers")),
            coerce_int(author.get("followersCount")),
            coerce_int(author.get("followers_count")),
        ),
        "following": max(
            coerce_int(author.get("following")),
            coerce_int(author.get("friendsCount")),
            coerce_int(author.get("followingCount")),
            coerce_int(author.get("following_count")),
        ),
    }


def fetch_author_metrics(
    screen_name: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    twitter_bin = resolve_twitter_bin()
    try:
        result = command_runner(
            [twitter_bin, "user", screen_name, "--json"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(f"twitter user lookup failed for @{screen_name}: {exc}") from exc

    if result.returncode != 0:
        stderr = " ".join(result.stderr.split())
        stdout = " ".join(result.stdout.split())
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(f"twitter user lookup failed for @{screen_name}: {detail}")

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"twitter user lookup returned invalid JSON for @{screen_name}") from exc

    data = payload.get("data") if isinstance(payload, Mapping) and isinstance(payload.get("data"), Mapping) else payload
    if not isinstance(data, Mapping):
        raise RuntimeError(f"twitter user lookup returned unexpected payload for @{screen_name}")

    return {
        "screen_name": str(data.get("screenName") or data.get("screen_name") or screen_name).strip().lstrip("@"),
        "verified": coerce_bool(
            data.get("verified")
            or data.get("isBlueVerified")
            or data.get("is_blue_verified")
            or nested_get(data, "legacy", "verified")
        ),
        "followers": max(
            coerce_int(data.get("followers")),
            coerce_int(data.get("followersCount")),
            coerce_int(data.get("followers_count")),
            coerce_int(nested_get(data, "legacy", "followers_count")),
        ),
        "following": max(
            coerce_int(data.get("following")),
            coerce_int(data.get("friendsCount")),
            coerce_int(data.get("followingCount")),
            coerce_int(data.get("following_count")),
            coerce_int(nested_get(data, "legacy", "friends_count")),
        ),
    }


def enrich_author_metrics(
    item: Mapping[str, Any],
    *,
    cache: dict[str, dict[str, Any]] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str | None]:
    if diagnostics is not None:
        diagnostics.setdefault("payload_metrics", 0)
        diagnostics.setdefault("cache_hits", 0)
        diagnostics.setdefault("lookup_success", 0)
        diagnostics.setdefault("lookup_failed", 0)
        diagnostics.setdefault("missing_screen_name", 0)

    metrics = extract_author_metrics(item)
    screen_name = str(metrics.get("screen_name") or "").strip()
    if not screen_name:
        if diagnostics is not None:
            diagnostics["missing_screen_name"] += 1
        return metrics, None

    cache_key = screen_name.casefold()
    if metrics.get("followers", 0) > 0 or metrics.get("following", 0) > 0:
        if diagnostics is not None:
            diagnostics["payload_metrics"] += 1
        if cache is not None:
            cache[cache_key] = dict(metrics)
        return metrics, None

    if cache is not None and cache_key in cache:
        if diagnostics is not None:
            diagnostics["cache_hits"] += 1
        cached = dict(cache[cache_key])
        cached.setdefault("screen_name", screen_name)
        cached["verified"] = bool(cached.get("verified") or metrics.get("verified"))
        return cached, None

    try:
        fetched = fetch_author_metrics(screen_name)
    except RuntimeError as exc:
        if diagnostics is not None:
            diagnostics["lookup_failed"] += 1
        return metrics, str(exc)

    if diagnostics is not None:
        diagnostics["lookup_success"] += 1
    if cache is not None:
        cache[cache_key] = dict(fetched)

    merged = dict(metrics)
    merged["screen_name"] = str(fetched.get("screen_name") or screen_name)
    merged["verified"] = bool(merged.get("verified") or fetched.get("verified"))
    merged["followers"] = max(coerce_int(merged.get("followers")), coerce_int(fetched.get("followers")))
    merged["following"] = max(coerce_int(merged.get("following")), coerce_int(fetched.get("following")))
    return merged, None
