from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from python.stock_cache import load_stock_cache_bundle, save_stock_cache
from python.stock_fetcher import StockSnapshot


class StockCacheTests(unittest.TestCase):
    def test_save_and_load_cache_bundle_with_metadata(self) -> None:
        snapshot = StockSnapshot(
            ticker="7203.T",
            name="トヨタ自動車",
            sector="輸送用機器",
            latest_date="2026-03-19",
            previous_close=100.0,
            current_close=101.0,
            pct_change=1.0,
            volume=1000,
            trading_value=101000.0,
            average_volume_5d=900.0,
            high_price=102.0,
            fifty_two_week_high=120.0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stock_cache.json"
            save_stock_cache([snapshot], path, metadata={"trade_date": "2026-03-19"})
            bundle = load_stock_cache_bundle(path)

        self.assertEqual(bundle.metadata["trade_date"], "2026-03-19")
        self.assertEqual(len(bundle.snapshots), 1)
        self.assertEqual(bundle.snapshots[0].ticker, "7203.T")


if __name__ == "__main__":
    unittest.main()
