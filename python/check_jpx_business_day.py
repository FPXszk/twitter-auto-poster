from __future__ import annotations

import argparse
import os
from datetime import date

from jp_market_calendar import (
    current_jst_date,
    first_jpx_business_day_of_month,
    is_jpx_business_day,
    jpx_closure_reason,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check whether a JST date is a JPX business day.")
    parser.add_argument("--date", help="Target JST date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument(
        "--mode",
        choices=("business-day", "first-business-day-of-month"),
        default="business-day",
    )
    parser.add_argument("--github-output", action="store_true")
    return parser.parse_args()


def parse_target_date(raw_date: str | None) -> date:
    if not raw_date:
        return current_jst_date()
    return date.fromisoformat(raw_date)


def main() -> int:
    args = parse_args()
    target_date = parse_target_date(args.date)

    if args.mode == "first-business-day-of-month":
        first_business_day = first_jpx_business_day_of_month(target_date.year, target_date.month)
        should_run = target_date == first_business_day
        reason = "" if should_run else f"not first JPX business day of month (first day: {first_business_day.isoformat()})"
    else:
        first_business_day = None
        should_run = is_jpx_business_day(target_date)
        reason = jpx_closure_reason(target_date) or ""

    print(
        f"target_date={target_date.isoformat()} "
        f"should_run={str(should_run).lower()} "
        f"reason={reason or 'business-day'}"
    )

    if args.github_output:
        output_path = os.environ.get("GITHUB_OUTPUT")
        if not output_path:
            raise RuntimeError("GITHUB_OUTPUT is not set")
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"should_run={'true' if should_run else 'false'}\n")
            handle.write(f"target_date={target_date.isoformat()}\n")
            handle.write(f"reason={reason}\n")
            if first_business_day is not None:
                handle.write(f"first_business_day={first_business_day.isoformat()}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
