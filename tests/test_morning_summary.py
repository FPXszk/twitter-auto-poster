from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "python").resolve()))

from python.morning_summary import build_post_text
from python.stock_fetcher import StockSnapshot


def snapshot(ticker: str, name: str, pct_change: float, breakout: bool = True) -> StockSnapshot:
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
        high_price=130.0 if breakout else 110.0,
        fifty_two_week_high=120.0,
    )


class MorningSummaryTests(unittest.TestCase):
    @patch("python.morning_summary.fetch_market_snapshot", return_value=(38200.0, 0.8))
    def test_build_post_text_matches_strategy_template(self, _fetch_market_snapshot: object) -> None:
        snapshots = [
            snapshot("1001.T", "銘柄一", 1.0),
            snapshot("1002.T", "銘柄二", 2.0),
            snapshot("1003.T", "銘柄三", 3.0),
            snapshot("1004.T", "銘柄四", 4.0),
            snapshot("1005.T", "銘柄五", 5.0),
            snapshot("1006.T", "銘柄六", 6.0),
            snapshot("1007.T", "銘柄七", 7.0),
            snapshot("1008.T", "銘柄八", 8.0),
            snapshot("1009.T", "銘柄九", 9.0),
        ]

        trade_date, text = build_post_text(snapshots)

        self.assertEqual(trade_date, "2026-03-19")
        self.assertIn("【🌅 本日の注目銘柄】03/19", text)
        self.assertIn("🌙 日経平均先物(夜間) ¥38,200 +0.8%", text)
        self.assertIn("52週高値更新中", text)
        self.assertIn("1. 銘柄九(1009) +9.0%", text)
        self.assertIn("8. 銘柄二(1002) +2.0%", text)
        self.assertNotIn("銘柄一(1001)", text)

    @patch("python.morning_summary.fetch_market_snapshot", return_value=(38200.0, 0.8))
    def test_build_post_text_falls_back_to_none_when_no_breakouts(self, _fetch_market_snapshot: object) -> None:
        snapshots = [
            snapshot("1001.T", "銘柄一", 1.0, breakout=False),
            snapshot("1002.T", "銘柄二", 2.0, breakout=False),
        ]

        _, text = build_post_text(snapshots)

        self.assertTrue(text.endswith("52週高値更新中\n1. なし"))


if __name__ == "__main__":
    unittest.main()
