"""Tests for posting window logic (JST 7:00–1:00 hourly run window)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from posting_window import should_run_in_posting_window

JST = ZoneInfo("Asia/Tokyo")


class PostingWindowTest(unittest.TestCase):
    """Boundary tests for should_run_in_posting_window."""

    def test_jst_7am_is_within_window(self) -> None:
        dt = datetime(2026, 3, 31, 7, 0, 0, tzinfo=JST)
        self.assertTrue(should_run_in_posting_window(dt))

    def test_jst_0am_is_within_window(self) -> None:
        dt = datetime(2026, 3, 31, 0, 0, 0, tzinfo=JST)
        self.assertTrue(should_run_in_posting_window(dt))

    def test_jst_0_59_is_within_window(self) -> None:
        dt = datetime(2026, 3, 31, 0, 59, 59, tzinfo=JST)
        self.assertTrue(should_run_in_posting_window(dt))

    def test_jst_1am_is_within_window(self) -> None:
        dt = datetime(2026, 3, 31, 1, 0, 0, tzinfo=JST)
        self.assertTrue(should_run_in_posting_window(dt))

    def test_jst_6am_is_outside_window(self) -> None:
        dt = datetime(2026, 3, 31, 6, 0, 0, tzinfo=JST)
        self.assertFalse(should_run_in_posting_window(dt))

    def test_jst_6_59_is_outside_window(self) -> None:
        dt = datetime(2026, 3, 31, 6, 59, 59, tzinfo=JST)
        self.assertFalse(should_run_in_posting_window(dt))

    def test_jst_23pm_is_within_window(self) -> None:
        dt = datetime(2026, 3, 31, 23, 0, 0, tzinfo=JST)
        self.assertTrue(should_run_in_posting_window(dt))

    def test_jst_12pm_is_within_window(self) -> None:
        dt = datetime(2026, 3, 31, 12, 0, 0, tzinfo=JST)
        self.assertTrue(should_run_in_posting_window(dt))

    def test_jst_3am_is_outside_window(self) -> None:
        dt = datetime(2026, 3, 31, 3, 0, 0, tzinfo=JST)
        self.assertFalse(should_run_in_posting_window(dt))

    def test_naive_datetime_raises_error(self) -> None:
        dt = datetime(2026, 3, 31, 10, 0, 0)
        with self.assertRaises(ValueError):
            should_run_in_posting_window(dt)


if __name__ == "__main__":
    unittest.main()
