from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import json
import logging
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from urllib.request import urlopen

import xlrd
import yaml
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "config" / "tickers_jp.csv"
DEFAULT_BACKUP_PATH = PROJECT_ROOT / "config" / "tickers_jp.csv.bak"
DEFAULT_RULES_PATH = PROJECT_ROOT / "config" / "tickers_jp_rules.yaml"
DEFAULT_SUMMARY_PATH = PROJECT_ROOT / "tmp" / "tickers_jp_update_summary.json"
REQUIRED_COLUMNS = ("コード", "銘柄名", "市場・商品区分", "33業種区分")
OUTPUT_FIELDS = ("ticker", "name", "sector")
DIFF_DETAIL_LIMIT = 10
DIFF_ALERT_THRESHOLD = 50
JST = ZoneInfo("Asia/Tokyo")


@dataclass(frozen=True)
class TickerRules:
    target_markets: tuple[str, ...]
    exclude_name_keywords: tuple[str, ...]

    @cached_property
    def excluded_name_pattern(self) -> re.Pattern[str]:
        escaped_keywords = [re.escape(keyword) for keyword in self.exclude_name_keywords if keyword]
        if not escaped_keywords:
            raise ValueError("rules.exclude_name_keywords must not be empty")
        return re.compile("|".join(escaped_keywords))


@dataclass(frozen=True)
class HeaderMatch:
    sheet_name: str
    row_index: int
    indexes: dict[str, int]
    matched_columns: tuple[str, ...]


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build config/tickers_jp.csv from the JPX official XLS.")
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP_PATH)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def load_rules(rules_path: Path) -> TickerRules:
    payload = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    allowed_keys = {"target_markets", "exclude_name_keywords"}
    unexpected_keys = sorted(set(payload) - allowed_keys)
    if unexpected_keys:
        raise ValueError(f"{rules_path} contains unsupported keys: {', '.join(unexpected_keys)}")
    target_market_values = payload.get("target_markets", []) or []
    exclude_keyword_values = payload.get("exclude_name_keywords", []) or []

    target_markets = tuple(str(value).strip() for value in target_market_values if str(value).strip())
    exclude_name_keywords = tuple(
        str(value).strip() for value in exclude_keyword_values if str(value).strip()
    )

    if not target_markets:
        raise ValueError(f"{rules_path} is missing target_markets")
    if not exclude_name_keywords:
        raise ValueError(f"{rules_path} is missing exclude_name_keywords")

    return TickerRules(target_markets=target_markets, exclude_name_keywords=exclude_name_keywords)


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


def find_header_match(workbook: xlrd.book.Book) -> HeaderMatch:
    best_partial_match: HeaderMatch | None = None

    for sheet in workbook.sheets():
        for row_index in range(sheet.nrows):
            row_values = [cell_to_text(sheet.cell(row_index, column_index)) for column_index in range(sheet.ncols)]
            matched_columns = tuple(column for column in REQUIRED_COLUMNS if column in row_values)
            if not matched_columns:
                continue

            match = HeaderMatch(
                sheet_name=sheet.name,
                row_index=row_index,
                indexes={column: row_values.index(column) for column in matched_columns},
                matched_columns=matched_columns,
            )
            if len(matched_columns) == len(REQUIRED_COLUMNS):
                return match

            if best_partial_match is None or len(matched_columns) > len(best_partial_match.matched_columns):
                best_partial_match = match

    if best_partial_match is not None:
        missing_columns = [column for column in REQUIRED_COLUMNS if column not in best_partial_match.matched_columns]
        raise ValueError(
            "JPX source header mismatch on "
            f"sheet '{best_partial_match.sheet_name}' row {best_partial_match.row_index + 1}: "
            f"missing columns: {', '.join(missing_columns)}; "
            f"matched columns: {', '.join(best_partial_match.matched_columns)}"
        )

    raise ValueError("JPX source header row was not found in any sheet")


def load_source_rows(source_url: str) -> tuple[list[dict[str, str]], str]:
    workbook = xlrd.open_workbook(file_contents=download_source_bytes(source_url))
    header_match = find_header_match(workbook)
    sheet = workbook.sheet_by_name(header_match.sheet_name)

    rows: list[dict[str, str]] = []
    for row_index in range(header_match.row_index + 1, sheet.nrows):
        row = {
            column: cell_to_text(sheet.cell(row_index, column_index))
            for column, column_index in header_match.indexes.items()
        }
        if any(row.values()):
            rows.append(row)

    if not rows:
        raise ValueError(
            f"JPX source did not contain any data rows after header on sheet '{header_match.sheet_name}'"
        )
    return rows, header_match.sheet_name


def build_output_rows(records: list[dict[str, str]], rules: TickerRules) -> tuple[list[dict[str, str]], dict[str, int]]:
    seen_codes: set[str] = set()
    selected_rows: list[dict[str, str]] = []
    market_counts: Counter[str] = Counter()

    for record in records:
        market = record["市場・商品区分"].strip()
        code = record["コード"].strip()
        name = record["銘柄名"].strip()
        sector = record["33業種区分"].strip()

        if market not in rules.target_markets:
            continue
        if not re.fullmatch(r"\d{4}", code):
            continue
        if sector in ("", "-"):
            continue
        if rules.excluded_name_pattern.search(name):
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
    if not rows:
        raise ValueError("no tickers matched the configured JPX filters")

    LOGGER.info("selected %s JPX rows by market: %s", len(rows), dict(market_counts))
    return rows, dict(market_counts)


def load_existing_rows(output_path: Path) -> list[dict[str, str]]:
    if not output_path.exists():
        return []

    with output_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"existing ticker CSV has no header: {output_path}")

        missing_fields = [field for field in OUTPUT_FIELDS if field not in reader.fieldnames]
        if missing_fields:
            raise ValueError(
                f"existing ticker CSV is missing fields: {', '.join(missing_fields)} ({output_path})"
            )

        rows = []
        for row in reader:
            rows.append({field: (row.get(field) or "").strip() for field in OUTPUT_FIELDS})
        return rows


def limit_details(rows: list[dict[str, str | int]]) -> list[dict[str, str | int]]:
    return rows[:DIFF_DETAIL_LIMIT]


def build_diff_summary(
    existing_rows: list[dict[str, str]],
    next_rows: list[dict[str, str]],
) -> dict[str, object]:
    existing_by_ticker = {row["ticker"]: row for row in existing_rows}
    next_by_ticker = {row["ticker"]: row for row in next_rows}

    added = [next_by_ticker[ticker] for ticker in sorted(set(next_by_ticker) - set(existing_by_ticker))]
    removed = [existing_by_ticker[ticker] for ticker in sorted(set(existing_by_ticker) - set(next_by_ticker))]

    sector_changed = []
    name_changed = []
    for ticker in sorted(set(existing_by_ticker) & set(next_by_ticker)):
        previous = existing_by_ticker[ticker]
        current = next_by_ticker[ticker]
        if previous["name"] != current["name"]:
            name_changed.append(
                {
                    "ticker": ticker,
                    "old_name": previous["name"],
                    "new_name": current["name"],
                    "sector": current["sector"],
                }
            )
        if previous["sector"] != current["sector"]:
            sector_changed.append(
                {
                    "ticker": ticker,
                    "name": current["name"],
                    "old_sector": previous["sector"],
                    "new_sector": current["sector"],
                }
            )

    summary = {
        "existing_count": len(existing_rows),
        "next_count": len(next_rows),
        "added_count": len(added),
        "removed_count": len(removed),
        "name_changed_count": len(name_changed),
        "sector_changed_count": len(sector_changed),
        "added": limit_details(added),
        "removed": limit_details(removed),
        "name_changed": limit_details(name_changed),
        "sector_changed": limit_details(sector_changed),
        "detail_limit": DIFF_DETAIL_LIMIT,
    }
    LOGGER.info(
        "JPX ticker diff: added=%s removed=%s name_changed=%s sector_changed=%s",
        summary["added_count"],
        summary["removed_count"],
        summary["name_changed_count"],
        summary["sector_changed_count"],
    )
    return summary


def write_rows(rows: list[dict[str, str]], output_path: Path, backup_path: Path) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    backup_created = False

    try:
        with temp_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

        if output_path.exists():
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output_path, backup_path)
            backup_created = True
            LOGGER.info("backed up existing ticker CSV to %s", backup_path)

        temp_path.replace(output_path)
        LOGGER.info("wrote %s rows to %s", len(rows), output_path)
        return backup_created
    finally:
        if temp_path.exists():
            temp_path.unlink()


def write_summary(summary: dict[str, object], summary_output_path: Path) -> None:
    summary_output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def update_tickers(
    source_url: str,
    rules_path: Path,
    output_path: Path,
    backup_path: Path,
) -> dict[str, object]:
    rules = load_rules(rules_path)
    source_rows, sheet_name = load_source_rows(source_url)
    next_rows, market_counts = build_output_rows(source_rows, rules)

    warnings: list[str] = []
    try:
        existing_rows = load_existing_rows(output_path)
    except ValueError as error:
        warning = f"existing CSV diff was skipped: {error}"
        warnings.append(warning)
        LOGGER.warning(warning)
        existing_rows = []

    diff_summary = build_diff_summary(existing_rows, next_rows)
    total_changes = (
        int(diff_summary["added_count"])
        + int(diff_summary["removed_count"])
        + int(diff_summary["name_changed_count"])
        + int(diff_summary["sector_changed_count"])
    )
    if total_changes >= DIFF_ALERT_THRESHOLD:
        warning = f"JPX diff is large ({total_changes} changes >= {DIFF_ALERT_THRESHOLD}); review the monthly update carefully"
        warnings.append(warning)
        LOGGER.warning(warning)
    backup_created = write_rows(next_rows, output_path, backup_path)
    generated_at = datetime.now(JST).isoformat()
    rules_hash = hashlib.sha256(rules_path.read_bytes()).hexdigest()
    previous_updated_at = datetime.fromtimestamp(output_path.stat().st_mtime, JST).isoformat() if output_path.exists() else ""

    return {
        "status": "success",
        "generated_at_jst": generated_at,
        "source_url": source_url,
        "rules_path": str(rules_path),
        "rules_sha256": rules_hash,
        "sheet_name": sheet_name,
        "selected_count": len(next_rows),
        "market_counts": market_counts,
        "backup_created": backup_created,
        "output_path": str(output_path),
        "backup_path": str(backup_path),
        "previous_output_updated_at_jst": previous_updated_at,
        "diff": diff_summary,
        "warnings": warnings,
    }


def build_failure_summary(
    source_url: str,
    rules_path: Path,
    output_path: Path,
    backup_path: Path,
    error: Exception,
) -> dict[str, object]:
    return {
        "status": "failure",
        "generated_at_jst": datetime.now(JST).isoformat(),
        "source_url": source_url,
        "rules_path": str(rules_path),
        "output_path": str(output_path),
        "backup_path": str(backup_path),
        "error": str(error),
    }


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    try:
        summary = update_tickers(args.source_url, args.rules, args.output, args.backup)
        write_summary(summary, args.summary_output)
        return 0
    except Exception as error:
        failure_summary = build_failure_summary(args.source_url, args.rules, args.output, args.backup, error)
        try:
            write_summary(failure_summary, args.summary_output)
        except Exception:
            LOGGER.exception("failed to write summary output to %s", args.summary_output)
        LOGGER.exception("failed to update %s; keeping existing file", args.output)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
