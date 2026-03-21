from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "python").resolve()))

from python.evening_summary import build_post_text
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
            snapshot("1111.T", "ベイカレント", 2.7),
            snapshot("2222.T", "古河電気工業", 2.4),
            snapshot("3333.T", "ＩＮＰＥＸ", 0.5),
            snapshot("4444.T", "住友金属鉱山", -8.8),
            snapshot("5555.T", "太平洋セメント", -8.7),
            snapshot("6666.T", "東京電力ホールディングス", -8.4),
        ]

        _, text = build_post_text(snapshots)

        self.assertIn("【🌆 本日の市場総括】03/19", text)
        self.assertIn("🗾 日経平均 ¥38,123 -1.2%", text)
        self.assertIn("値上がり率TOP3", text)
        self.assertIn("値下がり率TOP3", text)
        self.assertIn("3. ＩＮＰＥＸ(3333) +0.5%", text)
        self.assertIn("3. 東京電力ホールディングス(6666) -8.4%", text)

    @patch("python.evening_summary.fetch_market_snapshot", return_value=(38123.0, -1.2))
    def test_build_post_text_falls_back_to_none_when_one_side_is_empty(self, _fetch_market_snapshot: object) -> None:
        snapshots = [
            snapshot("1111.T", "ベイカレント", 2.7),
            snapshot("2222.T", "古河電気工業", 2.4),
        ]

        _, text = build_post_text(snapshots)

        self.assertIn("値下がり率TOP3\n1. なし", text)


if __name__ == "__main__":
    unittest.main()
