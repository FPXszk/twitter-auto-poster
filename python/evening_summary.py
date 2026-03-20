from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

import yfinance as yf

from stock_fetcher import DEFAULT_BATCH_SIZE, DEFAULT_SLEEP_SECONDS, StockSnapshot, fetch_stock_snapshots

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
POSTED_IDS_PATH = PROJECT_ROOT / "tmp" / "posted_ids.txt"
TWITTER_BIN = PROJECT_ROOT / "python" / ".venv" / "bin" / "twitter"
MAX_POST_LENGTH = 140
NIKKEI_TICKER = "^N225"
MEDALS = ("🥇", "🥈", "🥉")


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post the evening Japanese stock summary.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-repost", action="store_true")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def ensure_state_file(path: Path = POSTED_IDS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    return path


def load_state_entries(path: Path = POSTED_IDS_PATH) -> set[str]:
    return {
        line.strip()
        for line in ensure_state_file(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def append_state_entries(entries: Iterable[str], path: Path = POSTED_IDS_PATH) -> None:
    existing = load_state_entries(path)
    with ensure_state_file(path).open("a", encoding="utf-8") as handle:
        for entry in entries:
            normalized = entry.strip()
            if normalized and normalized not in existing:
                handle.write(f"{normalized}\n")
                existing.add(normalized)


def short_name(name: str, limit: int) -> str:
    return name if len(name) <= limit else name[:limit]


def code_of(ticker: str) -> str:
    return ticker.removesuffix(".T")


def format_abs_pct(value: float) -> str:
    return f"{abs(value):.1f}"


def format_price(value: float) -> str:
    return f"{value:,.0f}"


def arrow_of(value: float) -> str:
    return "📈" if value >= 0 else "📉"


def latest_trade_date(snapshots: Sequence[StockSnapshot]) -> str:
    return max(snapshot.latest_date for snapshot in snapshots)


def current_jst_date() -> str:
    return datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()


def fetch_market_snapshot(ticker: str) -> tuple[float, float]:
    try:
        history = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=False)
    except Exception as error:
        raise RuntimeError(f"failed to download market data for {ticker}") from error

    if history.empty or "Close" not in history.columns:
        raise ValueError(f"no market close data returned for {ticker}")

    closes = history["Close"].dropna()
    if len(closes.index) < 2:
        raise ValueError(f"insufficient market close history for {ticker}")

    previous_close = float(closes.iloc[-2])
    current_close = float(closes.iloc[-1])
    if previous_close == 0:
        raise ValueError(f"previous market close is zero for {ticker}")

    pct_change = ((current_close - previous_close) / previous_close) * 100.0
    return current_close, pct_change


def compute_rankings(
    snapshots: Sequence[StockSnapshot],
) -> tuple[list[StockSnapshot], list[StockSnapshot], list[StockSnapshot]]:
    trading_top = sorted(snapshots, key=lambda item: item.trading_value, reverse=True)[:3]
    gainers = sorted((item for item in snapshots if item.pct_change > 0), key=lambda item: item.pct_change, reverse=True)[:3]
    losers = sorted((item for item in snapshots if item.pct_change < 0), key=lambda item: item.pct_change)[:3]
    return trading_top, gainers, losers


def format_trading_lines(items: Sequence[StockSnapshot], name_limit: int) -> str:
    if not items:
        return "🥇 なし"

    return "\n".join(
        f"{medal} {short_name(item.name, name_limit)}({code_of(item.ticker)}) "
        f"¥{format_price(item.current_close)} {arrow_of(item.pct_change)}{format_abs_pct(item.pct_change)}%"
        for medal, item in zip(MEDALS, items)
    )


def format_gainer_lines(items: Sequence[StockSnapshot], name_limit: int) -> str:
    if not items:
        return "1. なし"

    return "\n".join(
        f"{index}. {short_name(item.name, name_limit)}({code_of(item.ticker)}) 📈+{format_abs_pct(item.pct_change)}%"
        for index, item in enumerate(items, start=1)
    )


def format_loser_lines(items: Sequence[StockSnapshot], name_limit: int) -> str:
    if not items:
        return "1. なし"

    return "\n".join(
        f"{index}. {short_name(item.name, name_limit)}({code_of(item.ticker)}) 📉-{format_abs_pct(item.pct_change)}%"
        for index, item in enumerate(items, start=1)
    )


def build_post_text(snapshots: Sequence[StockSnapshot]) -> tuple[str, str]:
    if not snapshots:
        raise ValueError("no stock snapshots available")

    trading_top, gainers, losers = compute_rankings(snapshots)
    trade_date = latest_trade_date(snapshots)
    date_label = trade_date[5:].replace("-", "/")
    nikkei_price, nikkei_change = fetch_market_snapshot(NIKKEI_TICKER)

    count_options = (
        (3, 3, 3),
        (3, 3, 2),
        (3, 2, 2),
        (3, 2, 1),
        (2, 2, 2),
        (2, 2, 1),
        (2, 1, 1),
        (1, 1, 1),
    )
    name_limits = (12, 10, 8, 6, 4, 3, 2, 1)

    for trading_count, gainer_count, loser_count in count_options:
        for name_limit in name_limits:
            trading_items = trading_top[:trading_count]
            gainer_items = gainers[:gainer_count]
            loser_items = losers[:loser_count]
            trading_label = len(trading_items) if trading_items else 1
            gainer_label = len(gainer_items) if gainer_items else 1
            loser_label = len(loser_items) if loser_items else 1

            tweet_text = (
                f"【🌆 本日の市場総括】{date_label}\n\n"
                f"🗾 日経平均 ¥{format_price(nikkei_price)} {arrow_of(nikkei_change)}{format_abs_pct(nikkei_change)}%\n\n"
                f"💴 売買代金TOP{trading_label}\n"
                f"{format_trading_lines(trading_items, name_limit)}\n\n"
                f"📈 値上がりTOP{gainer_label}\n"
                f"{format_gainer_lines(gainer_items, name_limit)}\n\n"
                f"📉 値下がりTOP{loser_label}\n"
                f"{format_loser_lines(loser_items, name_limit)}"
            )
            if len(tweet_text) <= MAX_POST_LENGTH:
                return trade_date, tweet_text

    raise ValueError("could not fit evening summary within 140 characters")


def extract_tweet_id(payload: object) -> str:
    def walk(node: object) -> str:
        if isinstance(node, dict):
            for key in ("id", "rest_id", "tweet_id"):
                value = node.get(key)
                if isinstance(value, str) and value.isdigit():
                    return value
                if isinstance(value, int):
                    return str(value)
            for value in node.values():
                candidate = walk(value)
                if candidate:
                    return candidate
        elif isinstance(node, list):
            for item in node:
                candidate = walk(item)
                if candidate:
                    return candidate
        return ""

    return walk(payload)


def post_summary(tweet_text: str) -> str:
    if not TWITTER_BIN.is_file():
        raise FileNotFoundError(f"twitter-cli executable not found: {TWITTER_BIN}")

    auth_result = subprocess.run(
        [str(TWITTER_BIN), "status", "--yaml"],
        capture_output=True,
        text=True,
        check=False,
    )
    if auth_result.returncode != 0:
        raise RuntimeError("twitter-cli authentication required before posting")

    post_result = subprocess.run(
        [str(TWITTER_BIN), "post", tweet_text, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if post_result.returncode != 0:
        raise RuntimeError(post_result.stderr.strip() or "twitter post command failed")

    try:
        payload = json.loads(post_result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"twitter-cli returned invalid JSON: {error}") from error
    if payload.get("ok") is not True:
        raise RuntimeError("twitter post response did not indicate success")

    tweet_id = extract_tweet_id(payload.get("data") or payload)
    if not tweet_id:
        match = re.search(r"/status/(\d+)", post_result.stdout)
        if match:
            tweet_id = match.group(1)
    if not tweet_id:
        raise RuntimeError("could not extract posted tweet ID")
    return tweet_id


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    try:
        snapshots = fetch_stock_snapshots(
            batch_size=args.batch_size,
            sleep_seconds=args.sleep_seconds,
        )
        if not snapshots:
            LOGGER.error("no stock data available; skipping evening post")
            return 1

        trade_date, tweet_text = build_post_text(snapshots)
        summary_key = f"stock-evening:{current_jst_date()}"
        state_entries = load_state_entries()
        if summary_key in state_entries:
            if args.force_repost:
                LOGGER.warning("evening summary already posted for %s; continuing due to --force-repost", trade_date)
            else:
                LOGGER.warning("evening summary already posted for %s; skipping", trade_date)
                return 0

        LOGGER.info("prepared evening summary: %s", tweet_text.replace("\n", " | "))
        if args.dry_run:
            sys.stdout.write(f"{tweet_text}\n")
            return 0

        tweet_id = post_summary(tweet_text)
        append_state_entries((summary_key, tweet_id))
        LOGGER.info("posted evening summary tweet_id=%s", tweet_id)
        return 0
    except Exception:
        LOGGER.exception("evening summary failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
