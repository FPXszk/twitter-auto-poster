from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def current_jst_date() -> date:
    return datetime.now(JST).date()


def nth_weekday_of_month(year: int, month: int, weekday: int, occurrence: int) -> date:
    if occurrence <= 0:
        raise ValueError("occurrence must be > 0")

    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current + timedelta(days=7 * (occurrence - 1))


def vernal_equinox_day(year: int) -> int:
    if year < 1980 or year > 2099:
        raise ValueError(f"vernal equinox is unsupported for year: {year}")
    return int(20.8431 + 0.242194 * (year - 1980) - ((year - 1980) // 4))


def autumn_equinox_day(year: int) -> int:
    if year < 1980 or year > 2099:
        raise ValueError(f"autumn equinox is unsupported for year: {year}")
    return int(23.2488 + 0.242194 * (year - 1980) - ((year - 1980) // 4))


def base_japanese_holidays(year: int) -> dict[date, str]:
    holidays: dict[date, str] = {}

    holidays[date(year, 1, 1)] = "New Year's Day"
    holidays[
        nth_weekday_of_month(year, 1, 0, 2) if year >= 2000 else date(year, 1, 15)
    ] = "Coming of Age Day"

    if year >= 1967:
        holidays[date(year, 2, 11)] = "National Foundation Day"
    if year >= 2020:
        holidays[date(year, 2, 23)] = "Emperor's Birthday"
    elif 1989 <= year <= 2018:
        holidays[date(year, 12, 23)] = "Emperor's Birthday"

    holidays[date(year, 3, vernal_equinox_day(year))] = "Vernal Equinox Day"

    if year >= 2007:
        holidays[date(year, 4, 29)] = "Showa Day"
    elif year >= 1989:
        holidays[date(year, 4, 29)] = "Greenery Day"
    else:
        holidays[date(year, 4, 29)] = "Emperor's Birthday"
    holidays[date(year, 5, 3)] = "Constitution Memorial Day"
    if year >= 2007:
        holidays[date(year, 5, 4)] = "Greenery Day"
    holidays[date(year, 5, 5)] = "Children's Day"

    if year == 2020:
        holidays[date(year, 7, 23)] = "Marine Day"
        holidays[date(year, 7, 24)] = "Sports Day"
    elif year == 2021:
        holidays[date(year, 7, 22)] = "Marine Day"
        holidays[date(year, 7, 23)] = "Sports Day"
    else:
        marine_day = nth_weekday_of_month(year, 7, 0, 3) if year >= 2003 else date(year, 7, 20)
        sports_day = nth_weekday_of_month(year, 10, 0, 2) if year >= 2000 else date(year, 10, 10)
        holidays[marine_day] = "Marine Day"
        holidays[sports_day] = "Sports Day"

    if year == 2020:
        holidays[date(year, 8, 10)] = "Mountain Day"
    elif year == 2021:
        holidays[date(year, 8, 8)] = "Mountain Day"
    elif year >= 2016:
        holidays[date(year, 8, 11)] = "Mountain Day"

    respect_for_aged_day = nth_weekday_of_month(year, 9, 0, 3) if year >= 2003 else date(year, 9, 15)
    holidays[respect_for_aged_day] = "Respect for the Aged Day"
    holidays[date(year, 9, autumn_equinox_day(year))] = "Autumnal Equinox Day"

    holidays[date(year, 11, 3)] = "Culture Day"
    holidays[date(year, 11, 23)] = "Labour Thanksgiving Day"
    return holidays


def japanese_holidays(year: int) -> dict[date, str]:
    holidays = dict(base_japanese_holidays(year))

    current = date(year, 1, 2)
    end = date(year, 12, 30)
    while current <= end:
        previous_day = current - timedelta(days=1)
        next_day = current + timedelta(days=1)
        if current not in holidays and previous_day in holidays and next_day in holidays:
            holidays[current] = "Citizen's Holiday"
        current += timedelta(days=1)

    observed = dict(holidays)
    for holiday_date, holiday_name in sorted(holidays.items()):
        if holiday_date.weekday() != 6:
            continue

        substitute_date = holiday_date + timedelta(days=1)
        while substitute_date in observed:
            substitute_date += timedelta(days=1)
        observed[substitute_date] = f"Substitute Holiday for {holiday_name}"

    return observed


def jpx_closure_reason(target_date: date) -> str | None:
    if target_date.weekday() >= 5:
        return "weekend"
    if (target_date.month, target_date.day) in {(1, 2), (1, 3), (12, 31)}:
        return "JPX year-end/new-year closure"

    holiday_name = japanese_holidays(target_date.year).get(target_date)
    if holiday_name is not None:
        return holiday_name
    return None


def is_jpx_business_day(target_date: date) -> bool:
    return jpx_closure_reason(target_date) is None


def previous_jpx_business_day(target_date: date) -> date:
    current = target_date - timedelta(days=1)
    while not is_jpx_business_day(current):
        current -= timedelta(days=1)
    return current


def first_jpx_business_day_of_month(year: int, month: int) -> date:
    current = date(year, month, 1)
    while not is_jpx_business_day(current):
        current += timedelta(days=1)
    return current


def is_first_jpx_business_day_of_month(target_date: date) -> bool:
    return target_date == first_jpx_business_day_of_month(target_date.year, target_date.month)
