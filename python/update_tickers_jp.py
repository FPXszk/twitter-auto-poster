from __future__ import annotations

import argparse
import csv
import logging
import re
import shutil
from collections import Counter
from pathlib import Path
from urllib.request import urlopen

import xlrd

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "config" / "tickers_jp.csv"
DEFAULT_BACKUP_PATH = PROJECT_ROOT / "config" / "tickers_jp.csv.bak"
TARGET_MARKETS = {
    "東証プライム（内国株式）",
    "プライム（内国株式）",
}
EXCLUDED_NAME_PATTERN = re.compile(r"ETF|ＥＴＦ|REIT|ＲＥＩＴ|投資法人|優先株|優先")
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


def download_source_bytes(source_url: str) -> bytes:
    with urlopen(source_url, timeout=60) as response:
        return response.read()


def cell_to_text(cell: xlrd.sheet.Cell) -> str:
    value = cell.value
    if value in ("", None):
        return ""

    if cell.ctype == xlrd.XL_CELL_NUMBER:
        number = float(value)
        if number.is_integer():
            return str(int(number))

    return str(value).strip()


def load_source_rows(source_url: str) -> list[dict[str, str]]:
    workbook = xlrd.open_workbook(file_contents=download_source_bytes(source_url))
    sheet = workbook.sheet_by_index(0)

    header_row_index: int | None = None
    header_indexes: dict[str, int] = {}
    for row_index in range(sheet.nrows):
        row_values = [cell_to_text(sheet.cell(row_index, column_index)) for column_index in range(sheet.ncols)]
        candidate_indexes = {column: row_values.index(column) for column in REQUIRED_COLUMNS if column in row_values}
        if len(candidate_indexes) == len(REQUIRED_COLUMNS):
            header_row_index = row_index
            header_indexes = candidate_indexes
            break

    if header_row_index is None:
        raise ValueError(f"JPX source is missing columns: {', '.join(REQUIRED_COLUMNS)}")

    rows: list[dict[str, str]] = []
    for row_index in range(header_row_index + 1, sheet.nrows):
        row = {
            column: cell_to_text(sheet.cell(row_index, column_index))
            for column, column_index in header_indexes.items()
        }
        if any(row.values()):
            rows.append(row)

    if not rows:
        raise ValueError("JPX source did not contain any data rows")
    return rows


def build_output_rows(records: list[dict[str, str]]) -> list[dict[str, str]]:
    seen_codes: set[str] = set()
    selected_rows: list[dict[str, str]] = []
    market_counts: Counter[str] = Counter()

    for record in records:
        market = record["市場・商品区分"].strip()
        code = record["コード"].strip()
        name = record["銘柄名"].strip()
        sector = record["33業種区分"].strip()

        if market not in TARGET_MARKETS:
            continue
        if not re.fullmatch(r"\d{4}", code):
            continue
        if sector in ("", "-"):
            continue
        if EXCLUDED_NAME_PATTERN.search(name):
            continue
        if code in seen_codes:
            continue

        seen_codes.add(code)
        market_counts[market] += 1
        selected_rows.append(
            {
                "ticker": f"{code}.T",
                "name": name,
                "sector": sector,
            }
        )

    rows = sorted(selected_rows, key=lambda row: row["ticker"])
    LOGGER.info("selected %s JPX rows by market: %s", len(rows), dict(market_counts))
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
        source_rows = load_source_rows(args.source_url)
        rows = build_output_rows(source_rows)
        write_rows(rows, args.output, args.backup)
        return 0
    except Exception:
        LOGGER.exception("failed to update %s; keeping existing file", args.output)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
