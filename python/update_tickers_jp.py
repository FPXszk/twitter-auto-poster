from __future__ import annotations

import argparse
import csv
import logging
import re
import shutil
from pathlib import Path

import pandas as pd

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "config" / "tickers_jp.csv"
DEFAULT_BACKUP_PATH = PROJECT_ROOT / "config" / "tickers_jp.csv.bak"
TARGET_MARKETS = {
    "東証プライム（内国株式）",
    "プライム（内国株式）",
    "名証プレミア（内国株式）",
    "プレミア（内国株式）",
}
EXCLUDED_NAME_PATTERN = re.compile(r"ETF|ＥＴＦ|ETN|ＥＴＮ|REIT|ＲＥＩＴ|投資法人|優先")
REQUIRED_COLUMNS = ("コード", "銘柄名", "市場・商品区分", "33業種区分")


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build config/tickers_jp.csv from the JPX official XLS.")
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP_PATH)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def load_source_frame(source_url: str) -> pd.DataFrame:
    frame = pd.read_excel(source_url, dtype=str, engine="xlrd")
    frame.columns = [str(column).strip() for column in frame.columns]

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"JPX source is missing columns: {', '.join(missing_columns)}")
    return frame


def build_output_rows(frame: pd.DataFrame) -> list[dict[str, str]]:
    market = frame["市場・商品区分"].fillna("").str.strip()
    code = frame["コード"].fillna("").str.strip()
    name = frame["銘柄名"].fillna("").str.strip()
    sector = frame["33業種区分"].fillna("").str.strip()

    target_mask = (
        market.isin(TARGET_MARKETS)
        & code.str.fullmatch(r"\d{4}")
        & sector.ne("")
        & sector.ne("-")
        & ~name.str.contains(EXCLUDED_NAME_PATTERN)
    )
    filtered = frame.loc[target_mask, list(REQUIRED_COLUMNS)].copy()
    filtered = filtered.drop_duplicates(subset=["コード"], keep="first")
    filtered = filtered.sort_values(by="コード")

    market_counts = filtered["市場・商品区分"].value_counts().to_dict()
    LOGGER.info("selected %s JPX rows by market: %s", len(filtered), market_counts)
    if not any("プレミア" in market_name for market_name in market_counts):
        LOGGER.warning("JPX source did not contain 名証プレミア rows for the configured market labels")

    rows = [
        {
            "ticker": f"{record['コード']}.T",
            "name": record["銘柄名"],
            "sector": record["33業種区分"],
        }
        for record in filtered.to_dict(orient="records")
    ]
    if not rows:
        raise ValueError("no tickers matched the configured JPX filters")
    return rows


def write_rows(rows: list[dict[str, str]], output_path: Path, backup_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")

    try:
        with temp_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("ticker", "name", "sector"))
            writer.writeheader()
            writer.writerows(rows)

        if output_path.exists():
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output_path, backup_path)
            LOGGER.info("backed up existing ticker CSV to %s", backup_path)

        temp_path.replace(output_path)
        LOGGER.info("wrote %s rows to %s", len(rows), output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    try:
        frame = load_source_frame(args.source_url)
        rows = build_output_rows(frame)
        write_rows(rows, args.output, args.backup)
        return 0
    except Exception:
        LOGGER.exception("failed to update %s; keeping existing file", args.output)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
