from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
import logging
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
import yfinance as yf

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TICKERS_PATH = PROJECT_ROOT / "config" / "tickers_jp.csv"
DEFAULT_BATCH_SIZE = 100
DEFAULT_SLEEP_SECONDS = 1.0
INFO_FETCH_MAX_WORKERS = 8


@dataclass(frozen=True)
class TickerRecord:
    ticker: str
    name: str
    sector: str


@dataclass(frozen=True)
class StockSnapshot:
    ticker: str
    name: str
    sector: str
    latest_date: str
    previous_close: float
    current_close: float
    pct_change: float
    volume: int
    trading_value: float
    average_volume_5d: float
    high_price: float
    fifty_two_week_high: float


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def normalize_ticker(raw_ticker: str) -> str:
    ticker = raw_ticker.strip().upper()
    if not ticker:
        raise ValueError("ticker is empty")
    return ticker if ticker.endswith(".T") else f"{ticker}.T"


def load_ticker_records(tickers_path: Path = DEFAULT_TICKERS_PATH) -> list[TickerRecord]:
    if not tickers_path.is_file():
        raise FileNotFoundError(f"ticker config not found: {tickers_path}")

    with tickers_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required_fields = {"ticker", "name", "sector"}
        if not required_fields.issubset(reader.fieldnames or []):
            raise ValueError(f"{tickers_path} must contain columns: ticker,name,sector")

        records: list[TickerRecord] = []
        for line_number, row in enumerate(reader, start=2):
            ticker = normalize_ticker(str(row.get("ticker") or ""))
            name = str(row.get("name") or "").strip()
            sector = str(row.get("sector") or "").strip()
            if not name or not sector:
                raise ValueError(f"{tickers_path}:{line_number} requires name and sector")
            records.append(TickerRecord(ticker=ticker, name=name, sector=sector))

    if not records:
        raise ValueError(f"ticker config is empty: {tickers_path}")
    return records


def chunked(values: Sequence[TickerRecord], chunk_size: int) -> Iterable[Sequence[TickerRecord]]:
    for start in range(0, len(values), chunk_size):
        yield values[start : start + chunk_size]


def _extract_frame(history: pd.DataFrame, ticker: str, batch_size: int) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()

    if not isinstance(history.columns, pd.MultiIndex):
        return history.copy() if batch_size == 1 else pd.DataFrame()

    if ticker in history.columns.get_level_values(0):
        return history[ticker].copy()
    if ticker in history.columns.get_level_values(1):
        return history.xs(ticker, axis=1, level=1).copy()
    return pd.DataFrame()


def _fetch_fifty_two_week_high(ticker: str) -> float:
    try:
        info = yf.Ticker(ticker).info
    except Exception as error:
        raise RuntimeError(f"failed to fetch ticker info for {ticker}") from error

    if not isinstance(info, dict):
        raise ValueError(f"ticker info is invalid for {ticker}")

    raw_value = info.get("fiftyTwoWeekHigh")
    if raw_value is None:
        raise ValueError(f"fiftyTwoWeekHigh is missing for {ticker}")

    try:
        fifty_two_week_high = float(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"fiftyTwoWeekHigh is not numeric for {ticker}") from error

    if not math.isfinite(fifty_two_week_high) or math.isclose(fifty_two_week_high, 0.0) or fifty_two_week_high < 0:
        raise ValueError(f"fiftyTwoWeekHigh is invalid for {ticker}")

    return fifty_two_week_high


def _fetch_fifty_two_week_highs(batch: Sequence[TickerRecord]) -> tuple[dict[str, float], dict[str, Exception]]:
    values: dict[str, float] = {}
    errors: dict[str, Exception] = {}
    max_workers = min(INFO_FETCH_MAX_WORKERS, len(batch))
    if max_workers <= 0:
        return values, errors

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_fetch_fifty_two_week_high, record.ticker): record.ticker
            for record in batch
        }
        for future in as_completed(future_map):
            ticker = future_map[future]
            try:
                values[ticker] = future.result()
            except Exception as error:
                errors[ticker] = error
    return values, errors


def _build_snapshot(
    record: TickerRecord,
    frame: pd.DataFrame,
    fifty_two_week_high: float,
) -> StockSnapshot | None:
    if frame.empty:
        LOGGER.warning("no data returned for %s", record.ticker)
        return None

    required_columns = {"Close", "High", "Volume"}
    if not required_columns.issubset(frame.columns):
        LOGGER.warning("missing OHLCV columns for %s", record.ticker)
        return None

    numeric_frame = (
        frame.loc[:, ["Close", "High", "Volume"]]
        .apply(pd.to_numeric, errors="coerce")
        .dropna(subset=["Close", "High", "Volume"])
    )
    if len(numeric_frame.index) < 2:
        LOGGER.warning("insufficient price history for %s", record.ticker)
        return None

    previous_close = float(numeric_frame["Close"].iloc[-2])
    current_close = float(numeric_frame["Close"].iloc[-1])
    if math.isclose(previous_close, 0.0):
        LOGGER.warning("previous close is zero for %s", record.ticker)
        return None

    volume = int(numeric_frame["Volume"].iloc[-1])
    high_price = float(numeric_frame["High"].iloc[-1])
    volume_baseline = numeric_frame["Volume"].iloc[-6:-1]
    if volume_baseline.empty:
        volume_baseline = numeric_frame["Volume"].iloc[:-1]
    if volume_baseline.empty:
        LOGGER.warning("insufficient volume history for %s", record.ticker)
        return None
    average_volume_5d = float(volume_baseline.tail(5).mean())
    pct_change = ((current_close - previous_close) / previous_close) * 100.0
    if (
        previous_close < current_close * 0.5
        or previous_close > current_close * 2.0
        or pct_change < -50.0
        or pct_change > 50.0
    ):
        LOGGER.warning(
            "skipping %s due to abnormal pct_change: %.1f%%",
            record.ticker,
            pct_change,
        )
        return None
    latest_date = pd.Timestamp(numeric_frame.index[-1]).date().isoformat()

    return StockSnapshot(
        ticker=record.ticker,
        name=record.name,
        sector=record.sector,
        latest_date=latest_date,
        previous_close=previous_close,
        current_close=current_close,
        pct_change=pct_change,
        volume=volume,
        trading_value=current_close * volume,
        average_volume_5d=average_volume_5d,
        high_price=high_price,
        fifty_two_week_high=fifty_two_week_high,
    )


def _download_batch(batch: Sequence[TickerRecord]) -> list[StockSnapshot]:
    tickers = [record.ticker for record in batch]
    try:
        history = yf.download(
            tickers=tickers,
            period="1y",
            interval="1d",
            auto_adjust=False,
            group_by="ticker",
            progress=False,
            threads=False,
        )
    except Exception:
        LOGGER.exception("failed to download batch starting with %s", tickers[0])
        return []

    snapshots: list[StockSnapshot] = []
    fifty_two_week_highs, info_errors = _fetch_fifty_two_week_highs(batch)
    for record in batch:
        try:
            frame = _extract_frame(history, record.ticker, len(batch))
            error = info_errors.get(record.ticker)
            if error is not None:
                raise error
            fifty_two_week_high = fifty_two_week_highs[record.ticker]
            snapshot = _build_snapshot(record, frame, fifty_two_week_high)
        except (RuntimeError, ValueError) as error:
            LOGGER.warning("%s", error)
            snapshot = None
        except Exception:
            LOGGER.exception("failed to normalize data for %s", record.ticker)
            snapshot = None
        if snapshot is not None:
            snapshots.append(snapshot)
    return snapshots


def fetch_stock_snapshots(
    tickers_path: Path = DEFAULT_TICKERS_PATH,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
) -> list[StockSnapshot]:
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if sleep_seconds < 0:
        raise ValueError("sleep_seconds must be >= 0")

    records = load_ticker_records(tickers_path)
    batches = list(chunked(records, batch_size))
    snapshots: list[StockSnapshot] = []

    for index, batch in enumerate(batches, start=1):
        LOGGER.info("fetching batch %s/%s (%s tickers)", index, len(batches), len(batch))
        snapshots.extend(_download_batch(batch))
        if index < len(batches) and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    LOGGER.info("fetched %s/%s tickers successfully", len(snapshots), len(records))
    return snapshots


def snapshots_to_dicts(snapshots: Sequence[StockSnapshot]) -> list[dict[str, object]]:
    return [asdict(snapshot) for snapshot in snapshots]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Japanese stock snapshots with yfinance.")
    parser.add_argument("--tickers", type=Path, default=DEFAULT_TICKERS_PATH)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--limit", type=int, default=0, help="Limit JSON output rows.")
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
    except Exception:
        LOGGER.exception("stock fetch failed")
        return 1

    output_rows = snapshots_to_dicts(snapshots)
    if args.limit > 0:
        output_rows = output_rows[: args.limit]

    json.dump(output_rows, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if snapshots else 1


if __name__ == "__main__":
    raise SystemExit(main())
