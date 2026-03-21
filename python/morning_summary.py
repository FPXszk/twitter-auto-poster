from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

from jp_market_calendar import current_jst_date, jpx_closure_reason, previous_jpx_business_day
from market_snapshot import fetch_market_snapshot
from stock_cache import load_stock_cache_bundle
from stock_fetcher import DEFAULT_BATCH_SIZE, DEFAULT_SLEEP_SECONDS, StockSnapshot, fetch_stock_snapshots
from summary_common import (
    SummaryBuildResult,
    append_state_entries,
    code_of,
    format_price,
    format_signed_pct,
    latest_trade_date,
    load_state_entries,
    post_summary,
    short_name,
)

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
POSTED_IDS_PATH = PROJECT_ROOT / "tmp" / "posted_ids.txt"
TWITTER_BIN = PROJECT_ROOT / "python" / ".venv" / "bin" / "twitter"
NIKKEI_FUTURES_TICKER = "NKD=F"


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post the morning Japanese stock summary.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-repost", action="store_true")
    parser.add_argument("--cache-path", type=Path)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def compute_rankings(snapshots: Sequence[StockSnapshot]) -> list[StockSnapshot]:
    high_breakouts = [
        snapshot
        for snapshot in snapshots
        if snapshot.high_price >= snapshot.fifty_two_week_high
    ]
    return sorted(high_breakouts, key=lambda item: item.pct_change, reverse=True)[:8]


def format_breakout_lines(items: Sequence[StockSnapshot], name_limit: int) -> str:
    if not items:
        return "1. なし"

    return "\n".join(
        f"{index}. {short_name(item.name, name_limit)}({code_of(item.ticker)}) "
        f"{format_signed_pct(item.pct_change)}%"
        for index, item in enumerate(items, start=1)
    )


def render_post_text(
    trade_date: str,
    futures_price: float,
    futures_change: float,
    breakout_items: Sequence[StockSnapshot],
    name_limit: int | None = None,
) -> str:
    date_label = trade_date[5:].replace("-", "/")
    if name_limit is not None:
        resolved_name_limit = name_limit
    elif breakout_items:
        resolved_name_limit = max(len(item.name) for item in breakout_items)
    else:
        resolved_name_limit = 1
    return (
        f"【🌅 本日の注目銘柄】{date_label}\n\n"
        f"🌙 日経平均先物(夜間) ¥{format_price(futures_price)} {format_signed_pct(futures_change)}%\n\n"
        "52週高値更新中\n"
        f"{format_breakout_lines(breakout_items, resolved_name_limit)}"
    )


def build_post_result(snapshots: Sequence[StockSnapshot]) -> SummaryBuildResult:
    if not snapshots:
        raise ValueError("no stock snapshots available")

    breakout_top = compute_rankings(snapshots)
    trade_date = latest_trade_date([snapshot.latest_date for snapshot in snapshots])
    futures_price, futures_change = fetch_market_snapshot(NIKKEI_FUTURES_TICKER)
    text = render_post_text(
        trade_date=trade_date,
        futures_price=futures_price,
        futures_change=futures_change,
        breakout_items=breakout_top,
    )
    return SummaryBuildResult(
        trade_date=trade_date,
        text=text,
        variant_label="posting-strategy-template",
        text_length=len(text),
    )


def build_post_text(snapshots: Sequence[StockSnapshot]) -> tuple[str, str]:
    result = build_post_result(snapshots)
    return result.trade_date, result.text


def write_summary_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def expected_trade_date(today: date) -> str:
    return previous_jpx_business_day(today).isoformat()


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
            LOGGER.info("today is not a JPX business day (%s: %s); skipping morning post", today, closure_reason)
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
            LOGGER.error("no stock data available; skipping morning post")
            return 1

        build_result = build_post_result(snapshots)
        trade_date = build_result.trade_date
        tweet_text = build_result.text
        expected_date = expected_trade_date(today)
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
                "morning summary trade_date=%s does not match expected previous business day=%s; skipping",
                trade_date,
                expected_date,
            )
            return 0
        summary_key = f"stock-morning:{today.isoformat()}"
        state_entries = load_state_entries(POSTED_IDS_PATH)
        if summary_key in state_entries:
            if args.force_repost:
                LOGGER.warning("morning summary already posted for %s; continuing due to --force-repost", trade_date)
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
                LOGGER.warning("morning summary already posted for %s; skipping", trade_date)
                return 0

        LOGGER.info("prepared morning summary: %s", tweet_text.replace("\n", " | "))
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
        LOGGER.info("posted morning summary tweet_id=%s", tweet_id)
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
        LOGGER.exception("morning summary failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
