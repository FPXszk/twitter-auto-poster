from __future__ import annotations

import sys
import unittest
from pathlib import Path

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
    def test_build_post_text_prefers_three_gainers_two_losers(self) -> None:
        snapshots = [
            snapshot("1111.T", "ベイカレント", 2.7),
            snapshot("2222.T", "古河電気工業", 2.4),
            snapshot("3333.T", "ＩＮＰＥＸ", 0.5),
            snapshot("4444.T", "住友金属鉱山", -8.8),
            snapshot("5555.T", "太平洋セメント", -8.7),
            snapshot("6666.T", "東京電力ホールディングス", -8.4),
        ]

        _, text = build_post_text(snapshots)

        self.assertLessEqual(len(text), 140)
        self.assertNotIn("日経平均", text)
        self.assertIn("3. ＩＮＰＥＸ(3333) +0.5%", text)
        self.assertIn("2. 太平洋セメン(5555) -8.7%", text)
        self.assertNotIn("3. 東京電力ホー(6666) -8.4%", text)

    def test_build_post_text_falls_back_to_two_by_two_when_pct_values_are_wide(self) -> None:
        snapshots = [
            snapshot("1111.T", "ベイカレント", 1000.0),
            snapshot("2222.T", "古河電気工業", 999.0),
            snapshot("3333.T", "ＩＮＰＥＸ", 998.0),
            snapshot("4444.T", "住友金属鉱山", -1000.0),
            snapshot("5555.T", "太平洋セメント", -999.0),
            snapshot("6666.T", "東京電力ホールディングス", -998.0),
        ]

        _, text = build_post_text(snapshots)

        self.assertLessEqual(len(text), 140)
        self.assertIn("2. 古河電気工業(2222) +999.0%", text)
        self.assertIn("2. 太平洋セメン(5555) -999.0%", text)
        self.assertNotIn("3. ＩＮＰＥＸ(3333) +998.0%", text)
        self.assertNotIn("3. 東京電力ホー(6666) -998.0%", text)


if __name__ == "__main__":
    unittest.main()
