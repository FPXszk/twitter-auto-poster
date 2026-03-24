from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "python").resolve()))

from python.evening_summary import MAX_X_WEIGHTED_LENGTH, build_post_result, build_post_text
from python.summary_common import estimate_x_weighted_length
from python.stock_fetcher import StockSnapshot


def snapshot(ticker: str, name: str, pct_change: float) -> StockSnapshot:
    return StockSnapshot(
        ticker=ticker,
        name=name,
        sector="Test",
        latest_date="2026-03-19",
        previous_close=100.0,
        current_close=100.0 + pct_change,
        pct_change=pct_change,
        volume=1000,
        trading_value=100000.0,
        average_volume_5d=1000.0,
        high_price=110.0,
        fifty_two_week_high=120.0,
    )


class EveningSummaryTests(unittest.TestCase):
    @patch("python.evening_summary.fetch_market_snapshot", return_value=(38123.0, -1.2))
    def test_build_post_text_matches_strategy_template(self, _fetch_market_snapshot: object) -> None:
        snapshots = [
            snapshot("0001.T", "ディスコ", 5.1),
            snapshot("0002.T", "アドバンテスト", 4.8),
            snapshot("0003.T", "東京エレクトロン", 3.4),
            snapshot("1111.T", "ベイカレント", 2.7),
            snapshot("2222.T", "古河電気工業", 2.4),
            snapshot("3333.T", "ＩＮＰＥＸ", -0.5),
            snapshot("4444.T", "住友金属鉱山", -8.8),
            snapshot("5555.T", "太平洋セメント", -8.7),
            snapshot("6666.T", "東京電力ホールディングス", -8.4),
            snapshot("7777.T", "三菱重工業", -7.9),
            snapshot("8888.T", "日本郵船", -7.5),
        ]

        _, text = build_post_text(snapshots, headline_date=date(2026, 3, 23))

        self.assertIn("【🌆 本日の市場総括】03/23", text)
        self.assertIn("🗾 日経平均 ¥38,123 -1.2%", text)
        self.assertIn("値上がり率TOP5", text)
        self.assertIn("値下がり率TOP5", text)
        self.assertIn("5. 古河電気工業(2222) +2.4%", text)
        self.assertIn("5. 日本郵船(8888) -7.5%", text)

    @patch("python.evening_summary.fetch_market_snapshot", return_value=(38123.0, -1.2))
    def test_build_post_text_falls_back_to_none_when_one_side_is_empty(self, _fetch_market_snapshot: object) -> None:
        snapshots = [
            snapshot("1111.T", "ベイカレント", 2.7),
            snapshot("2222.T", "古河電気工業", 2.4),
        ]

        _, text = build_post_text(snapshots, headline_date=date(2026, 3, 23))

        self.assertIn("値下がり率TOP5\n1. なし", text)

    @patch("python.evening_summary.fetch_market_snapshot", return_value=(38123.0, -1.2))
    def test_build_post_text_honors_custom_rank_counts(self, _fetch_market_snapshot: object) -> None:
        snapshots = [
            snapshot("0001.T", "ディスコ", 5.1),
            snapshot("0002.T", "アドバンテスト", 4.8),
            snapshot("0003.T", "東京エレクトロン", 3.4),
            snapshot("1111.T", "ベイカレント", 2.7),
            snapshot("2222.T", "古河電気工業", 2.4),
            snapshot("4444.T", "住友金属鉱山", -8.8),
            snapshot("5555.T", "太平洋セメント", -8.7),
            snapshot("6666.T", "東京電力ホールディングス", -8.4),
        ]

        _, text = build_post_text(
            snapshots,
            headline_date=date(2026, 3, 23),
            gainers_count=3,
            losers_count=2,
        )

        self.assertIn("値上がり率TOP3", text)
        self.assertIn("値下がり率TOP2", text)
        self.assertIn("3. 東京エレクトロン(0003) +3.4%", text)
        self.assertNotIn("4. ベイカレント(1111)", text)
        self.assertIn("2. 太平洋セメント(5555) -8.7%", text)
        self.assertNotIn("3. 東京電力ホールディングス(6666)", text)

    @patch("python.evening_summary.fetch_market_snapshot", return_value=(38123.0, -1.2))
    def test_build_post_result_respects_x_weighted_limit(self, _fetch_market_snapshot: object) -> None:
        snapshots = [
            snapshot("1111.T", "超長い銘柄名サンプルホールディングス一号", 4.8),
            snapshot("2222.T", "超長い銘柄名サンプルホールディングス二号", 4.1),
            snapshot("3333.T", "超長い銘柄名サンプルホールディングス三号", 3.7),
            snapshot("4444.T", "超長い銘柄名サンプルホールディングス四号", 3.2),
            snapshot("5555.T", "超長い銘柄名サンプルホールディングス五号", 2.9),
            snapshot("6666.T", "超長い銘柄名サンプルホールディングス六号", -8.8),
            snapshot("7777.T", "超長い銘柄名サンプルホールディングス七号", -8.7),
            snapshot("8888.T", "超長い銘柄名サンプルホールディングス八号", -8.4),
            snapshot("9999.T", "超長い銘柄名サンプルホールディングス九号", -8.1),
            snapshot("1010.T", "超長い銘柄名サンプルホールディングス十号", -7.9),
        ]

        result = build_post_result(snapshots, headline_date=date(2026, 3, 23))

        self.assertLessEqual(estimate_x_weighted_length(result.text), MAX_X_WEIGHTED_LENGTH)
        self.assertIn("【🌆 本日の市場総括】03/23", result.text)


if __name__ == "__main__":
    unittest.main()
