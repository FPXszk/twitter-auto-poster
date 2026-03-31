from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Mapping

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tiktok_allowlist import (
    get_allowed_creator,
    get_enabled_creators,
    load_allowlist,
)
from tiktok_client import TikTokClient
from tiktok_downloader import download_tiktok_video
from tiktok_filters import candidate_rejection_reasons
from tiktok_scoring import calculate_tiktok_score, extract_candidate_metrics
from tiktok_state import is_posted, load_posted_ids, mark_posted
from post_video import (
    estimate_x_weighted_length,
    post_video_tweet,
)

logger = logging.getLogger(__name__)

_TWITTER_URL_WEIGHTED_LENGTH = 24  # URL (23) + preceding space (1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate_weighted(text: str, max_weighted: int) -> str:
    """Truncate *text* so its X-weighted length fits within *max_weighted*."""
    normalized = " ".join(str(text or "").split()).strip()
    if estimate_x_weighted_length(normalized) <= max_weighted:
        return normalized
    result = ""
    for ch in normalized:
        trial = result + ch
        if estimate_x_weighted_length(trial + "…") > max_weighted:
            break
        result = trial
    return result.rstrip() + "…" if result else "…"


def _build_tweet_text(video: Mapping[str, Any], *, max_length: int = 280) -> str:
    """Build tweet text from video metadata, fitting within *max_length* weighted chars."""
    title = str(video.get("title") or "").strip()
    description = str(video.get("description") or "").strip()
    share_url = str(
        video.get("share_url") or video.get("video_page_url") or ""
    ).strip()

    parts = [p for p in [title, description] if p]
    if not parts:
        username = str((video.get("author") or {}).get("username") or "").strip()
        parts = [f"TikTok video by @{username}" if username else "TikTok video"]

    body = " ".join(parts)

    if share_url:
        available = max_length - _TWITTER_URL_WEIGHTED_LENGTH
        body = _truncate_weighted(body, available)
        return f"{body} {share_url}"

    return _truncate_weighted(body, max_length)


def _load_config(config_path: str | Path, category: str) -> dict[str, Any]:
    """Load the account-level configuration from *config_path*."""
    path = Path(config_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults") or {}
    accounts = raw.get("accounts") or {}
    account = accounts.get(category) or {}

    def _merge(key: str, fallback: Any = None) -> Any:
        return account.get(key, defaults.get(key, fallback))

    d_weights = defaults.get("score_weights") or {}
    a_weights = account.get("score_weights") or {}
    d_filters = defaults.get("filters") or {}
    a_filters = account.get("filters") or {}

    return {
        "dry_run": _merge("dry_run", True),
        "max_candidates": int(_merge("max_candidates", 1)),
        "single_post_max_length": int(_merge("single_post_max_length", 280)),
        "state_file": str(_merge("state_file", "")),
        "allowlist_path": str(_merge("allowlist_path", "config/tiktok_allowlist.yaml")),
        "score_weights": {
            "likes": float(a_weights.get("likes", d_weights.get("likes", 1))),
            "retweets": float(a_weights.get("retweets", d_weights.get("retweets", 1))),
            "replies": float(a_weights.get("replies", d_weights.get("replies", 1))),
            "views": float(a_weights.get("views", d_weights.get("views", 1))),
            "velocity": float(a_weights.get("velocity", d_weights.get("velocity", 0))),
            "freshness": float(a_weights.get("freshness", d_weights.get("freshness", 0))),
            "image_bonus": float(a_weights.get("image_bonus", d_weights.get("image_bonus", 0))),
            "author_virality": float(a_weights.get("author_virality", d_weights.get("author_virality", 0))),
        },
        "filters": {
            "max_age_hours": a_filters.get(
                "max_age_hours", d_filters.get("max_age_hours")
            ),
            "required_terms": (
                a_filters.get("required_terms", d_filters.get("required_terms", []))
                or []
            ),
            "exclude_keywords": (
                a_filters.get("exclude_keywords", d_filters.get("exclude_keywords", []))
                or []
            ),
            "min_engagement": int(a_filters.get("min_engagement", 0)),
            "min_likes": int(a_filters.get("min_likes", 0)),
            "min_views": int(a_filters.get("min_views", 0)),
            "min_replies": int(a_filters.get("min_replies", 0)),
            "min_retweets": int(a_filters.get("min_retweets", 0)),
        },
    }


def _resolve_state_path(
    output_dir: Path, configured: str, category: str
) -> Path:
    value = str(configured or "").strip()
    if not value:
        return output_dir / "state" / f"{category}-posted.txt"
    p = Path(value)
    return p if p.is_absolute() else output_dir / p


def _empty_data(
    action: str, dry_run: bool, category: str
) -> dict[str, Any]:
    return {
        "action": action,
        "dry_run": dry_run,
        "category": category,
        "creator": "",
        "video_id": "",
        "video_url": "",
        "tweet_text": "",
        "candidates_fetched": 0,
        "candidates_filtered": 0,
        "candidates_scored": 0,
        "selected_video_id": "",
        "post_result": None,
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_tiktok_pipeline(
    *,
    category: str = "tiktok",
    config_path: str | Path = "config/accounts.yaml",
    output_dir: str | Path = "tmp",
    dry_run: bool | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Orchestrate the TikTok → X posting pipeline."""

    # --- config -----------------------------------------------------------
    try:
        config = _load_config(config_path, category)
    except Exception as exc:
        logger.error("Failed to load config: %s", exc)
        return {
            "ok": False,
            "data": _empty_data("post_tiktok", True, category),
            "message": f"Config load failed: {exc}",
        }

    if dry_run is None:
        dry_run = bool(config.get("dry_run", True))
    live_run = not dry_run
    action = "dry_run_tiktok" if dry_run else "post_tiktok"
    max_length = config["single_post_max_length"]
    raw_filters = config["filters"]
    raw_weights = config["score_weights"]

    # --- allowlist --------------------------------------------------------
    try:
        allowlist = load_allowlist(config["allowlist_path"])
    except Exception as exc:
        logger.error("Failed to load allowlist: %s", exc)
        return {
            "ok": False,
            "data": _empty_data(action, dry_run, category),
            "message": f"Allowlist load failed: {exc}",
        }

    enabled_creators = get_enabled_creators(allowlist)
    if len(enabled_creators) > 1:
        return {
            "ok": False,
            "data": _empty_data(action, dry_run, category),
            "message": "v1 supports exactly one enabled TikTok allowlist creator per refresh token",
        }

    # --- state ------------------------------------------------------------
    out = Path(output_dir)
    state_path = _resolve_state_path(out, config["state_file"], category)
    posted_ids = load_posted_ids(state_path)

    # --- fetch & filter ---------------------------------------------------
    all_fetched = 0
    candidates: list[dict[str, Any]] = []

    for creator in enabled_creators:
        username = str(creator.get("tiktok_username") or "").strip()
        platform_uid = str(creator.get("platform_user_id") or "").strip()
        max_results = int(creator.get("max_results") or 10)

        try:
            client = TikTokClient.from_env(env=env)
            videos = client.fetch_user_videos(max_count=max_results)
        except Exception as exc:
            logger.warning("Fetch failed for %s: %s", username, exc)
            continue

        all_fetched += len(videos)

        for video in videos:
            video["author"] = {
                "username": username,
                "platform_user_id": platform_uid,
            }

            vid = str(video.get("id") or video.get("video_id") or "").strip()
            if not vid or is_posted(vid, posted_ids):
                continue

            allowed = get_allowed_creator(
                username, platform_uid, allowlist, live_run=live_run,
            )
            reasons = candidate_rejection_reasons(
                item=video,
                raw_filters=raw_filters,
                allowed_creator=allowed,
                live_run=live_run,
            )
            if reasons:
                logger.debug("Rejected %s: %s", vid, "; ".join(reasons))
                continue

            candidates.append(video)

    # --- score ------------------------------------------------------------
    for cand in candidates:
        metrics = extract_candidate_metrics(cand)
        score, breakdown = calculate_tiktok_score(
            metrics,
            raw_weights,
            created_at=str(cand.get("created_at") or ""),
            max_age_hours=raw_filters.get("max_age_hours"),
        )
        cand["score"] = score
        cand["score_breakdown"] = breakdown

    scored = [c for c in candidates if "score" in c]

    if not scored:
        data = _empty_data(action, dry_run, category)
        data["candidates_fetched"] = all_fetched
        data["candidates_filtered"] = len(candidates)
        return {"ok": True, "data": data, "message": "no eligible TikTok videos found"}

    # --- select -----------------------------------------------------------
    scored.sort(key=lambda v: float(v.get("score") or 0), reverse=True)
    selected = scored[0]

    sel_id = str(selected.get("id") or selected.get("video_id") or "").strip()
    video_url = str(
        selected.get("share_url") or selected.get("video_page_url") or ""
    ).strip()
    creator_name = str(
        (selected.get("author") or {}).get("username") or ""
    ).strip()
    tweet_text = _build_tweet_text(selected, max_length=max_length)

    # --- download ---------------------------------------------------------
    dl_dir = out / "tiktok-download"
    try:
        video_path = download_tiktok_video(video_url, dl_dir)
    except Exception as exc:
        logger.error("Download failed for %s: %s", video_url, exc)
        data = _empty_data(action, dry_run, category)
        data.update(
            creator=creator_name,
            video_id=sel_id,
            video_url=video_url,
            tweet_text=tweet_text,
            candidates_fetched=all_fetched,
            candidates_filtered=len(candidates),
            candidates_scored=len(scored),
            selected_video_id=sel_id,
        )
        return {"ok": False, "data": data, "message": f"Download failed: {exc}"}

    # --- post -------------------------------------------------------------
    try:
        post_result = post_video_tweet(
            tweet_text=tweet_text,
            video_path=video_path,
            dry_run=dry_run,
            env=env,
        )
    except Exception as exc:
        logger.error("Post failed: %s", exc)
        data = _empty_data(action, dry_run, category)
        data.update(
            creator=creator_name,
            video_id=sel_id,
            video_url=video_url,
            tweet_text=tweet_text,
            candidates_fetched=all_fetched,
            candidates_filtered=len(candidates),
            candidates_scored=len(scored),
            selected_video_id=sel_id,
        )
        return {"ok": False, "data": data, "message": f"Post failed: {exc}"}

    # --- state update -----------------------------------------------------
    if not dry_run and post_result.get("ok"):
        mark_posted(sel_id, state_path)

    pipeline_ok = bool(post_result.get("ok"))
    return {
        "ok": pipeline_ok,
        "data": {
            "action": action,
            "dry_run": dry_run,
            "category": category,
            "creator": creator_name,
            "video_id": sel_id,
            "video_url": video_url,
            "tweet_text": tweet_text,
            "candidates_fetched": all_fetched,
            "candidates_filtered": len(candidates),
            "candidates_scored": len(scored),
            "selected_video_id": sel_id,
            "post_result": post_result,
        },
        "message": (
            f"{'[DRY RUN] ' if dry_run else ''}Posted TikTok video {sel_id}"
            if pipeline_ok
            else str(post_result.get("message") or "Post returned failure")
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch owner TikTok videos and post the best one to X."
    )
    parser.add_argument("--category", default="tiktok")
    parser.add_argument("--dry-run", default="true")
    parser.add_argument("--output-dir", default="tmp")
    parser.add_argument("--config-path", default="config/accounts.yaml")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s] %(message)s"
    )

    dry_run = args.dry_run.lower() in {"true", "1", "yes"}
    result = run_tiktok_pipeline(
        category=args.category,
        dry_run=dry_run,
        output_dir=args.output_dir,
        config_path=args.config_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.get("ok") else 1)
