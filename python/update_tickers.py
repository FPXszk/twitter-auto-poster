from __future__ import annotations

import argparse
import logging
from pathlib import Path

from stock_cache import DEFAULT_STOCK_CACHE_PATH, save_stock_cache
from stock_fetcher import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_SLEEP_SECONDS,
    DEFAULT_TICKERS_PATH,
    configure_logging,
    fetch_stock_snapshots,
)

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Japanese stock snapshots and save a cache file.")
    parser.add_argument("--tickers", type=Path, default=DEFAULT_TICKERS_PATH)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--output", type=Path, default=DEFAULT_STOCK_CACHE_PATH)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    try:
        snapshots = fetch_stock_snapshots(
            tickers_path=args.tickers,
            batch_size=args.batch_size,
            sleep_seconds=args.sleep_seconds,
        )
        if not snapshots:
            LOGGER.error("no stock data fetched; cache file was not written")
            return 1

        output_path = save_stock_cache(snapshots, args.output)
        LOGGER.info("wrote stock cache: %s (%s snapshots)", output_path, len(snapshots))
        return 0
    except Exception:
        LOGGER.exception("stock cache update failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
