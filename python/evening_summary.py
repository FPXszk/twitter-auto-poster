from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence

from jp_market_calendar import current_jst_date, jpx_closure_reason
from stock_cache import load_stock_cache, load_stock_cache_bundle
from stock_fetcher import DEFAULT_BATCH_SIZE, DEFAULT_SLEEP_SECONDS, StockSnapshot, fetch_stock_snapshots
from summary_common import (
    SummaryBuildResult,
    append_state_entries,
    build_variants,
    code_of,
    format_signed_pct,
    latest_trade_date,
    load_state_entries,
    pick_fitting_variant,
    post_summary,
    short_name,
)

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
POSTED_IDS_PATH = PROJECT_ROOT / "tmp" / "posted_ids.txt"
TWITTER_BIN = PROJECT_ROOT / "python" / ".venv" / "bin" / "twitter"
MAX_POST_LENGTH = 140


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post the evening Japanese stock summary.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-repost", action="store_true")
    parser.add_argument("--cache-path", type=Path)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def compute_rankings(
    snapshots: Sequence[StockSnapshot],
) -> tuple[list[StockSnapshot], list[StockSnapshot]]:
    gainers = sorted((item for item in snapshots if item.pct_change > 0), key=lambda item: item.pct_change, reverse=True)[:3]
    losers = sorted((item for item in snapshots if item.pct_change < 0), key=lambda item: item.pct_change)[:3]
    return gainers, losers


def format_gainer_lines(items: Sequence[StockSnapshot], name_limit: int) -> str:
    if not items:
        return "1. なし"

    return "\n".join(
        f"{index}. {short_name(item.name, name_limit)}({code_of(item.ticker)}) {format_signed_pct(item.pct_change)}%"
        for index, item in enumerate(items, start=1)
    )


def format_loser_lines(items: Sequence[StockSnapshot], name_limit: int) -> str:
    if not items:
        return "1. なし"

    return "\n".join(
        f"{index}. {short_name(item.name, name_limit)}({code_of(item.ticker)}) {format_signed_pct(item.pct_change)}%"
        for index, item in enumerate(items, start=1)
    )


def render_post_text(
    trade_date: str,
    gainers: Sequence[StockSnapshot],
    losers: Sequence[StockSnapshot],
    name_limit: int | None = None,
) -> str:
    date_label = trade_date[5:].replace("-", "/")
    candidate_names = [item.name for item in (*gainers, *losers)]
    if name_limit is not None:
        resolved_name_limit = name_limit
    else:
        resolved_name_limit = max((len(name) for name in candidate_names), default=1)
    return (
        f"【🌆 本日の市場総括】{date_label}\n"
        f"上昇\n"
        f"{format_gainer_lines(gainers, resolved_name_limit)}\n"
        f"下落\n"
        f"{format_loser_lines(losers, resolved_name_limit)}"
    )


def build_post_result(snapshots: Sequence[StockSnapshot]) -> SummaryBuildResult:
    if not snapshots:
        raise ValueError("no stock snapshots available")

    gainers, losers = compute_rankings(snapshots)
    trade_date = latest_trade_date([snapshot.latest_date for snapshot in snapshots])
    variant_specs: list[dict[str, object]] = [
        {
            "label": "full-auto",
            "kwargs": {
                "trade_date": trade_date,
                "gainers": gainers,
                "losers": losers,
            },
        },
        {
            "label": "name-limit-6",
            "kwargs": {
                "trade_date": trade_date,
                "gainers": gainers,
                "losers": losers,
                "name_limit": 6,
            },
        },
    ]
    count_options = ((3, 2), (2, 3), (2, 2), (3, 1), (1, 3), (2, 1), (1, 2), (1, 1))
    for gainer_count, loser_count in count_options:
        variant_specs.append(
            {
                "label": f"{gainer_count}up_{loser_count}down",
                "kwargs": {
                    "trade_date": trade_date,
                    "gainers": gainers[:gainer_count],
                    "losers": losers[:loser_count],
                    "name_limit": 6,
                },
            }
        )
    return pick_fitting_variant(trade_date, build_variants(render_post_text, variant_specs), MAX_POST_LENGTH)


def build_post_text(snapshots: Sequence[StockSnapshot]) -> tuple[str, str]:
    result = build_post_result(snapshots)
    return result.trade_date, result.text


def write_summary_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    try:
        today = current_jst_date()
        closure_reason = jpx_closure_reason(today)
        if closure_reason is not None:
            if args.summary_output is not None:
                write_summary_payload(
                    args.summary_output,
                    {
                        "status": "skipped_market_holiday",
                        "date": today.isoformat(),
                        "reason": closure_reason,
                    },
                )
            LOGGER.info("today is not a JPX business day (%s: %s); skipping evening post", today, closure_reason)
            return 0

        if args.cache_path is not None:
            bundle = load_stock_cache_bundle(args.cache_path)
            snapshots = bundle.snapshots
            LOGGER.info("loaded %s stock snapshots from cache: %s", len(snapshots), args.cache_path)
        else:
            bundle = None
            snapshots = fetch_stock_snapshots(
                batch_size=args.batch_size,
                sleep_seconds=args.sleep_seconds,
            )
        if not snapshots:
            if args.summary_output is not None:
                write_summary_payload(
                    args.summary_output,
                    {
                        "status": "failed_no_stock_data",
                        "date": today.isoformat(),
                    },
                )
            LOGGER.error("no stock data available; skipping evening post")
            return 1

        build_result = build_post_result(snapshots)
        trade_date = build_result.trade_date
        tweet_text = build_result.text
        expected_date = today.isoformat()
        if trade_date != expected_date:
            if args.summary_output is not None:
                write_summary_payload(
                    args.summary_output,
                    {
                        "status": "skipped_stale_trade_date",
                        "date": today.isoformat(),
                        "trade_date": trade_date,
                        "expected_trade_date": expected_date,
                        "cache_metadata": (bundle.metadata if args.cache_path is not None and bundle is not None else {}),
                    },
                )
            LOGGER.warning(
                "evening summary trade_date=%s does not match expected business day=%s; skipping",
                trade_date,
                expected_date,
            )
            return 0
        summary_key = f"stock-evening:{today.isoformat()}"
        state_entries = load_state_entries(POSTED_IDS_PATH)
        if summary_key in state_entries:
            if args.force_repost:
                LOGGER.warning("evening summary already posted for %s; continuing due to --force-repost", trade_date)
            else:
                if args.summary_output is not None:
                    write_summary_payload(
                        args.summary_output,
                        {
                            "status": "skipped_duplicate",
                            "date": today.isoformat(),
                            "trade_date": trade_date,
                            "variant": build_result.variant_label,
                            "text_length": build_result.text_length,
                            "tweet_text": tweet_text,
                            "cache_metadata": (bundle.metadata if args.cache_path is not None and bundle is not None else {}),
                        },
                    )
                LOGGER.warning("evening summary already posted for %s; skipping", trade_date)
                return 0

        LOGGER.info("prepared evening summary: %s", tweet_text.replace("\n", " | "))
        if args.dry_run:
            if args.summary_output is not None:
                write_summary_payload(
                    args.summary_output,
                    {
                        "status": "dry_run",
                        "date": today.isoformat(),
                        "trade_date": trade_date,
                        "variant": build_result.variant_label,
                        "text_length": build_result.text_length,
                        "tweet_text": tweet_text,
                        "cache_metadata": (bundle.metadata if args.cache_path is not None and bundle is not None else {}),
                    },
                )
            sys.stdout.write(f"{tweet_text}\n")
            return 0

        tweet_id = post_summary(tweet_text, TWITTER_BIN)
        append_state_entries((summary_key, tweet_id), POSTED_IDS_PATH)
        if args.summary_output is not None:
            write_summary_payload(
                args.summary_output,
                {
                    "status": "posted",
                    "date": today.isoformat(),
                    "trade_date": trade_date,
                    "variant": build_result.variant_label,
                    "text_length": build_result.text_length,
                    "tweet_text": tweet_text,
                    "tweet_id": tweet_id,
                    "cache_metadata": (bundle.metadata if args.cache_path is not None and bundle is not None else {}),
                },
            )
        LOGGER.info("posted evening summary tweet_id=%s", tweet_id)
        return 0
    except Exception:
        if args.summary_output is not None:
            write_summary_payload(
                args.summary_output,
                {
                    "status": "failed_exception",
                    "date": current_jst_date().isoformat(),
                },
            )
        LOGGER.exception("evening summary failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
