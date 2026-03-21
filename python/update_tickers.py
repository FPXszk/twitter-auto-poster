from __future__ import annotations

import argparse
import logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from jp_market_calendar import current_jst_date, jpx_closure_reason
from stock_cache import DEFAULT_STOCK_CACHE_PATH, save_stock_cache
from stock_fetcher import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CONFIG_PATH,
    DEFAULT_SLEEP_SECONDS,
    DEFAULT_TICKERS_PATH,
    configure_logging,
    fetch_stock_snapshots_with_report,
)

LOGGER = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Japanese stock snapshots and save a cache file.")
    parser.add_argument("--tickers", type=Path, default=DEFAULT_TICKERS_PATH)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--output", type=Path, default=DEFAULT_STOCK_CACHE_PATH)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--summary-output", type=Path, default=Path("tmp/stock_cache_summary.json"))
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def write_summary_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    try:
        today = current_jst_date()
        closure_reason = jpx_closure_reason(today)
        if closure_reason is not None:
            write_summary_payload(
                args.summary_output,
                {
                    "status": "skipped_market_holiday",
                    "date": today.isoformat(),
                    "reason": closure_reason,
                },
            )
            LOGGER.info("today is not a JPX business day (%s: %s); skipping stock cache update", today, closure_reason)
            return 0

        snapshots, report = fetch_stock_snapshots_with_report(
            tickers_path=args.tickers,
            batch_size=args.batch_size,
            sleep_seconds=args.sleep_seconds,
            config_path=args.config,
        )
        if not snapshots:
            write_summary_payload(
                args.summary_output,
                {
                    "status": "failed_no_snapshots",
                    "date": today.isoformat(),
                    "fetch_report": report.to_dict(),
                },
            )
            LOGGER.error("no stock data fetched; cache file was not written")
            return 1

        trade_date = max(snapshot.latest_date for snapshot in snapshots)
        metadata = {
            "generated_at_jst": datetime.now(JST).isoformat(),
            "trade_date": trade_date,
            "snapshot_count": len(snapshots),
            "fetch_report": report.to_dict(),
        }
        output_path = save_stock_cache(snapshots, args.output, metadata=metadata)
        write_summary_payload(
            args.summary_output,
            {
                "status": "success",
                "date": today.isoformat(),
                "trade_date": trade_date,
                "output_path": str(output_path),
                "fetch_report": report.to_dict(),
            },
        )
        LOGGER.info("wrote stock cache: %s (%s snapshots)", output_path, len(snapshots))
        return 0
    except Exception:
        write_summary_payload(
            args.summary_output,
            {
                "status": "failed_exception",
                "date": current_jst_date().isoformat(),
            },
        )
        LOGGER.exception("stock cache update failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
