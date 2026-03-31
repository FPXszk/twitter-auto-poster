from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

import yaml

try:
    from scripts.lib.post_selection import sort_candidates
    from scripts.lib.tiktok_allowlist import get_allowed_creator, get_enabled_creators, load_allowlist
    from scripts.lib.tiktok_client import TikTokClient
    from scripts.lib.tiktok_downloader import download_tiktok_video
    from scripts.lib.tiktok_filters import candidate_rejection_reasons
    from scripts.lib.tiktok_scoring import calculate_score, extract_candidate_metrics
    from scripts.lib.tiktok_state import is_posted, load_posted_ids, mark_posted
    from scripts.lib.post_video import post_video_tweet
except ImportError:
    from post_selection import sort_candidates
    from tiktok_allowlist import get_allowed_creator, get_enabled_creators, load_allowlist
    from tiktok_client import TikTokClient
    from tiktok_downloader import download_tiktok_video
    from tiktok_filters import candidate_rejection_reasons
    from tiktok_scoring import calculate_score, extract_candidate_metrics
    from tiktok_state import is_posted, load_posted_ids, mark_posted
    from post_video import post_video_tweet

LOGGER = logging.getLogger(__name__)
DEFAULT_OUTPUT_PATH = Path("tmp/tiktok/tiktok-result.json")


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="[%(levelname)s] %(message)s")


def truncate_weighted(text: str, *, limit: int) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(limit - 1, 1)].rstrip() + "…"


def build_post_text(candidate: Mapping[str, Any], *, max_length: int) -> str:
    username = str(candidate.get("tiktok_username") or "").strip()
    title = str(candidate.get("title") or candidate.get("text") or "").strip()
    description = str(candidate.get("description") or "").strip()
    pieces = [piece for piece in [title, description] if piece]
    if not pieces:
        pieces = [f"TikTok video by @{username}" if username else "TikTok video"]
    return truncate_weighted(" ".join(pieces), limit=max_length)


def load_account_config(config_path: Path, category: str) -> dict[str, Any]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults") or {}
    account = (raw.get("accounts") or {}).get(category) or {}
    default_weights = defaults.get("score_weights") or {}
    account_weights = account.get("score_weights") or {}
    default_filters = defaults.get("filters") or {}
    account_filters = account.get("filters") or {}
    return {
        "dry_run": parse_bool(account.get("dry_run", defaults.get("dry_run", True))),
        "max_candidates": int(account.get("max_candidates") or defaults.get("max_candidates") or 1),
        "single_post_max_length": int(account.get("single_post_max_length") or defaults.get("single_post_max_length") or 280),
        "state_file": str(account.get("state_file") or defaults.get("state_file") or ""),
        "allowlist_path": str(account.get("allowlist_path") or "config/tiktok_allowlist.yaml"),
        "download_dir": str(account.get("download_dir") or "tmp/tiktok/downloads"),
        "score_weights": {
            "likes": float(account_weights.get("likes", default_weights.get("likes", 1))),
            "retweets": float(account_weights.get("retweets", default_weights.get("retweets", 1))),
            "replies": float(account_weights.get("replies", default_weights.get("replies", 1))),
            "views": float(account_weights.get("views", default_weights.get("views", 1))),
            "velocity": float(account_weights.get("velocity", default_weights.get("velocity", 0))),
            "freshness": float(account_weights.get("freshness", default_weights.get("freshness", 0))),
        },
        "filters": {
            "max_age_hours": account_filters.get("max_age_hours", default_filters.get("max_age_hours")),
            "required_terms": account_filters.get("required_terms", default_filters.get("required_terms", [])) or [],
            "exclude_keywords": account_filters.get("exclude_keywords", default_filters.get("exclude_keywords", [])) or [],
            "min_likes": int(account_filters.get("min_likes") or 0),
            "min_views": int(account_filters.get("min_views") or 0),
            "min_replies": int(account_filters.get("min_replies") or 0),
            "min_retweets": int(account_filters.get("min_retweets") or 0),
        },
    }


def resolve_state_path(output_dir: Path, configured_path: str, category: str) -> Path:
    value = str(configured_path or "").strip()
    if not value:
        return output_dir / "state" / f"{category}-posted.txt"
    path = Path(value)
    return path if path.is_absolute() else output_dir / path


def build_pipeline_payload(*, ok: bool, message: str, data: Mapping[str, Any]) -> dict[str, Any]:
    return {"ok": ok, "message": message, "data": dict(data)}


def write_pipeline_result(output_path: str | Path, payload: Mapping[str, Any]) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_tiktok_pipeline(
    *,
    category: str,
    config_path: Path,
    output_dir: Path,
    dry_run: bool | None = None,
    client: TikTokClient | None = None,
    downloader=download_tiktok_video,
    post_video=post_video_tweet,
) -> dict[str, Any]:
    account = load_account_config(config_path, category)
    live_run = not (account["dry_run"] if dry_run is None else dry_run)
    allowlist = load_allowlist(account["allowlist_path"])
    enabled_creators = get_enabled_creators(allowlist)
    if len(enabled_creators) > 1:
        raise RuntimeError("v1 supports exactly one enabled TikTok allowlist creator per refresh token")
    state_path = resolve_state_path(output_dir, account["state_file"], category)
    posted_ids = load_posted_ids(state_path)
    tik_client = client or TikTokClient.from_env()
    candidates: list[dict[str, Any]] = []

    for creator in enabled_creators:
        videos = tik_client.fetch_user_videos(int(creator.get("max_results") or 10))
        for item in videos:
            video_id = str(item.get("id") or "").strip()
            if not video_id or is_posted(video_id, posted_ids):
                continue
            allowed_creator = get_allowed_creator(
                str(creator.get("tiktok_username") or ""),
                str(creator.get("platform_user_id") or ""),
                allowlist,
                live_run=live_run,
            )
            reasons = candidate_rejection_reasons(
                item=item,
                raw_filters=account["filters"],
                allowed_creator=allowed_creator,
                live_run=live_run,
            )
            if reasons:
                continue
            metrics = extract_candidate_metrics(item)
            score, breakdown = calculate_score(
                metrics,
                account["score_weights"],
                created_at=str(item.get("created_at") or ""),
                max_age_hours=account["filters"].get("max_age_hours"),
                source_boost=float(creator.get("score_boost") or 0.0),
            )
            candidates.append(
                {
                    **dict(item),
                    "tiktok_username": creator["tiktok_username"],
                    "platform_user_id": creator["platform_user_id"],
                    "score": score,
                    "score_breakdown": breakdown,
                    **metrics,
                }
            )

    sorted_candidates = sort_candidates(candidates)
    if not sorted_candidates:
        return build_pipeline_payload(
            ok=True,
            message="no eligible TikTok videos found",
            data={"action": "skip", "dry_run": not live_run, "candidate_count": 0},
        )

    selected = sorted_candidates[0]
    download_dir = Path(account["download_dir"])
    download_path = downloader(str(selected.get("video_page_url") or ""), output_dir / download_dir)
    try:
        result = post_video(
            tweet_text=build_post_text(selected, max_length=account["single_post_max_length"]),
            video_path=download_path,
            dry_run=not live_run,
        )
    finally:
        if download_path.exists() and download_path.parent.name.startswith("tiktok-"):
            shutil.rmtree(download_path.parent, ignore_errors=True)
    if result.get("ok") and live_run:
        mark_posted(str(selected.get("id") or ""), state_path)
    data = dict(result.get("data") or {})
    data.update(
        {
            "candidate_count": len(sorted_candidates),
            "candidate_id": str(selected.get("id") or ""),
            "candidate_url": str(selected.get("video_page_url") or ""),
            "candidate_score": float(selected.get("score") or 0.0),
            "tiktok_username": str(selected.get("tiktok_username") or ""),
            "state_path": str(state_path),
        }
    )
    return build_pipeline_payload(ok=bool(result.get("ok")), message=str(result.get("message") or ""), data=data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch owner TikTok videos and post the best one to X.")
    parser.add_argument("--category", default="tiktok")
    parser.add_argument("--dry-run", default="true")
    parser.add_argument("--accounts-path", type=Path, default=Path("config/accounts.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("tmp"))
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    try:
        payload = run_tiktok_pipeline(
            category=args.category,
            config_path=args.accounts_path,
            output_dir=args.output_dir,
            dry_run=parse_bool(args.dry_run),
        )
    except Exception as error:
        payload = build_pipeline_payload(ok=False, message=str(error), data={"action": "post_tiktok"})
        write_pipeline_result(args.output_path, payload)
        LOGGER.error("%s", payload["message"])
        return 1
    write_pipeline_result(args.output_path, payload)
    if payload.get("ok"):
        LOGGER.info("%s", payload["message"])
        return 0
    LOGGER.error("%s", payload["message"])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
