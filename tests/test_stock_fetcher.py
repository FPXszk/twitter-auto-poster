from __future__ import annotations

import unittest

import pandas as pd

from python.stock_fetcher import TickerRecord, _build_snapshot


class StockFetcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = TickerRecord(ticker="7203.T", name="トヨタ自動車", sector="輸送用機器")

    def test_build_snapshot_keeps_normal_pct_change(self) -> None:
        frame = pd.DataFrame(
            {
                "Close": [100.0, 110.0],
                "High": [101.0, 112.0],
                "Volume": [1000, 1200],
            },
            index=pd.to_datetime(["2026-03-18", "2026-03-19"]),
        )

        snapshot = _build_snapshot(self.record, frame, fifty_two_week_high=130.0)

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertAlmostEqual(snapshot.pct_change, 10.0)

    def test_build_snapshot_skips_abnormal_pct_change(self) -> None:
        frame = pd.DataFrame(
            {
                "Close": [0.01, 100.0],
                "High": [0.02, 101.0],
                "Volume": [1000, 1200],
            },
            index=pd.to_datetime(["2026-03-18", "2026-03-19"]),
        )

        with self.assertLogs("python.stock_fetcher", level="WARNING") as captured:
            snapshot = _build_snapshot(self.record, frame, fifty_two_week_high=130.0)

        self.assertIsNone(snapshot)
        self.assertIn(
            "skipping 7203.T due to abnormal pct_change: 999900.0%",
            captured.output[0],
        )


if __name__ == "__main__":
    unittest.main()
