from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.update_tickers_jp import (
    DEFAULT_RULES_PATH,
    build_diff_summary,
    build_failure_summary,
    find_header_match,
    load_rules,
    load_source_rows,
    update_tickers,
    write_rows,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


class FakeCell:
    def __init__(self, value: str):
        self.value = value
        self.ctype = 1


class FakeSheet:
    def __init__(self, name: str, rows: list[list[str]]):
        self.name = name
        self._rows = rows
        self.nrows = len(rows)
        self.ncols = max((len(row) for row in rows), default=0)

    def cell(self, row_index: int, column_index: int) -> FakeCell:
        value = ""
        if row_index < len(self._rows) and column_index < len(self._rows[row_index]):
            value = self._rows[row_index][column_index]
        return FakeCell(value)


class FakeWorkbook:
    def __init__(self, sheets: list[FakeSheet]):
        self._sheets = sheets

    def sheets(self) -> list[FakeSheet]:
        return self._sheets

    def sheet_by_name(self, sheet_name: str) -> FakeSheet:
        for sheet in self._sheets:
            if sheet.name == sheet_name:
                return sheet
        raise KeyError(sheet_name)


class UpdateTickersJPTests(unittest.TestCase):
    def test_load_rules_reads_config(self) -> None:
        rules = load_rules(DEFAULT_RULES_PATH)
        self.assertIn("プライム（内国株式）", rules.target_markets)
        self.assertIn("ETF", rules.exclude_name_keywords)

    def test_load_rules_rejects_none_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "rules.yaml"
            rules_path.write_text("target_markets:\nexclude_name_keywords:\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing target_markets"):
                load_rules(rules_path)

    def test_load_source_rows_finds_header_in_fixture(self) -> None:
        fixture_path = (FIXTURE_DIR / "jpx_sample.xls").resolve()
        rows, sheet_name = load_source_rows(fixture_path.as_uri())
        self.assertEqual(sheet_name, "JPXData")
        self.assertEqual(rows[0]["コード"], "7203")
        self.assertEqual(rows[0]["銘柄名"], "トヨタ自動車")

    def test_find_header_match_reports_missing_columns(self) -> None:
        workbook = FakeWorkbook(
            [
                FakeSheet(
                    "broken",
                    [
                        ["コード", "銘柄名", "市場・商品区分"],
                        ["7203", "トヨタ自動車", "プライム（内国株式）"],
                    ],
                )
            ]
        )

        with self.assertRaisesRegex(ValueError, "missing columns: 33業種区分"):
            find_header_match(workbook)

    def test_update_tickers_filters_fixture_and_writes_summary_ready_data(self) -> None:
        fixture_path = (FIXTURE_DIR / "jpx_sample.xls").resolve()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "tickers_jp.csv"
            backup_path = Path(tmpdir) / "tickers_jp.csv.bak"
            output_path.write_text("ticker,name,sector\n7203.T,旧トヨタ,輸送用機器\n6501.T,日立製作所,電気機器\n", encoding="utf-8")

            summary = update_tickers(
                source_url=fixture_path.as_uri(),
                rules_path=DEFAULT_RULES_PATH,
                output_path=output_path,
                backup_path=backup_path,
            )

            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["selected_count"], 2)
            self.assertTrue(summary["backup_created"])
            self.assertEqual(summary["diff"]["added_count"], 1)
            self.assertEqual(summary["diff"]["removed_count"], 1)
            self.assertEqual(summary["diff"]["sector_changed_count"], 0)

            with output_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(
                rows,
                [
                    {"ticker": "6758.T", "name": "ソニーグループ", "sector": "電気機器"},
                    {"ticker": "7203.T", "name": "トヨタ自動車", "sector": "輸送用機器"},
                ],
            )

    def test_build_diff_summary_detects_sector_change(self) -> None:
        summary = build_diff_summary(
            existing_rows=[{"ticker": "7203.T", "name": "トヨタ自動車", "sector": "輸送用機器"}],
            next_rows=[{"ticker": "7203.T", "name": "トヨタ自動車", "sector": "機械"}],
        )
        self.assertEqual(summary["sector_changed_count"], 1)
        self.assertEqual(summary["sector_changed"][0]["old_sector"], "輸送用機器")
        self.assertEqual(summary["sector_changed"][0]["new_sector"], "機械")

    def test_write_rows_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "tickers_jp.csv"
            backup_path = Path(tmpdir) / "tickers_jp.csv.bak"
            output_path.write_text("ticker,name,sector\n1111.T,Old,OldSector\n", encoding="utf-8")

            backup_created = write_rows(
                [{"ticker": "7203.T", "name": "トヨタ自動車", "sector": "輸送用機器"}],
                output_path,
                backup_path,
            )

            self.assertTrue(backup_created)
            self.assertTrue(backup_path.exists())

    def test_build_failure_summary_is_json_serializable(self) -> None:
        summary = build_failure_summary(
            source_url="file:///tmp/example.xls",
            rules_path=DEFAULT_RULES_PATH,
            output_path=Path("config/tickers_jp.csv"),
            backup_path=Path("config/tickers_jp.csv.bak"),
            error=ValueError("broken header"),
        )
        payload = json.dumps(summary, ensure_ascii=False)
        self.assertIn("broken header", payload)

    @patch("python.update_tickers_jp.download_source_bytes", return_value=b"ignored")
    @patch("python.update_tickers_jp.xlrd.open_workbook")
    def test_load_source_rows_uses_specific_header_error(
        self,
        open_workbook_mock,
        _download_source_bytes_mock,
    ) -> None:
        open_workbook_mock.return_value = FakeWorkbook(
            [FakeSheet("broken", [["銘柄名", "市場・商品区分"], ["トヨタ自動車", "プライム（内国株式）"]])]
        )

        with self.assertRaisesRegex(ValueError, "missing columns: コード, 33業種区分"):
            load_source_rows("https://example.invalid/data.xls")


if __name__ == "__main__":
    unittest.main()
