"""Tests for posting window logic."""

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

    def test_default_window_still_allows_jst_7am(self) -> None:
        dt = datetime(2026, 3, 31, 7, 0, 0, tzinfo=JST)
        self.assertTrue(should_run_in_posting_window(dt))

    def test_explicit_slot_allows_jst_8am(self) -> None:
        dt = datetime(2026, 3, 31, 8, 0, 0, tzinfo=JST)
        self.assertTrue(should_run_in_posting_window(dt, allowed_times=[(8, 0), (12, 30), (21, 0)]))

    def test_explicit_slot_allows_jst_12_30pm(self) -> None:
        dt = datetime(2026, 3, 31, 12, 30, 0, tzinfo=JST)
        self.assertTrue(should_run_in_posting_window(dt, allowed_times=[(8, 0), (12, 30), (21, 0)]))

    def test_explicit_slot_allows_jst_9pm(self) -> None:
        dt = datetime(2026, 3, 31, 21, 0, 0, tzinfo=JST)
        self.assertTrue(should_run_in_posting_window(dt, allowed_times=[(8, 0), (12, 30), (21, 0)]))

    def test_explicit_slot_rejects_jst_8_01am(self) -> None:
        dt = datetime(2026, 3, 31, 8, 1, 0, tzinfo=JST)
        self.assertFalse(should_run_in_posting_window(dt, allowed_times=[(8, 0), (12, 30), (21, 0)]))

    def test_explicit_slot_rejects_jst_12pm(self) -> None:
        dt = datetime(2026, 3, 31, 12, 0, 0, tzinfo=JST)
        self.assertFalse(should_run_in_posting_window(dt, allowed_times=[(8, 0), (12, 30), (21, 0)]))

    def test_explicit_slot_rejects_jst_20_59pm(self) -> None:
        dt = datetime(2026, 3, 31, 20, 59, 0, tzinfo=JST)
        self.assertFalse(should_run_in_posting_window(dt, allowed_times=[(8, 0), (12, 30), (21, 0)]))

    def test_default_window_rejects_jst_3am(self) -> None:
        dt = datetime(2026, 3, 31, 3, 0, 0, tzinfo=JST)
        self.assertFalse(should_run_in_posting_window(dt))

    def test_naive_datetime_raises_error(self) -> None:
        dt = datetime(2026, 3, 31, 10, 0, 0)
        with self.assertRaises(ValueError):
            should_run_in_posting_window(dt)


if __name__ == "__main__":
    unittest.main()
