from __future__ import annotations

import unittest
from datetime import date

from python.jp_market_calendar import (
    first_jpx_business_day_of_month,
    is_first_jpx_business_day_of_month,
    is_jpx_business_day,
    japanese_holidays,
    jpx_closure_reason,
    previous_jpx_business_day,
)


class JPMarketCalendarTests(unittest.TestCase):
    def test_weekend_is_not_business_day(self) -> None:
        self.assertFalse(is_jpx_business_day(date(2026, 3, 21)))
        self.assertEqual(jpx_closure_reason(date(2026, 3, 21)), "weekend")

    def test_holiday_is_not_business_day(self) -> None:
        self.assertFalse(is_jpx_business_day(date(2026, 3, 20)))
        self.assertIn("Equinox", jpx_closure_reason(date(2026, 3, 20)) or "")

    def test_year_end_new_year_closure_is_not_business_day(self) -> None:
        self.assertFalse(is_jpx_business_day(date(2026, 1, 2)))
        self.assertEqual(jpx_closure_reason(date(2026, 1, 2)), "JPX year-end/new-year closure")

    def test_previous_business_day_skips_holiday_and_weekend(self) -> None:
        self.assertEqual(previous_jpx_business_day(date(2026, 3, 21)), date(2026, 3, 19))

    def test_first_business_day_of_month_rolls_forward(self) -> None:
        self.assertEqual(first_jpx_business_day_of_month(2026, 3), date(2026, 3, 2))
        self.assertTrue(is_first_jpx_business_day_of_month(date(2026, 3, 2)))

    def test_substitute_holiday_is_generated(self) -> None:
        holidays = japanese_holidays(2026)
        self.assertIn(date(2026, 5, 6), holidays)


if __name__ == "__main__":
    unittest.main()
