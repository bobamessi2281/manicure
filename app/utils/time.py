from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def tz_from_name(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def moscow_today(tz_name: str) -> date:
    return datetime.now(tz_from_name(tz_name)).date()


def combine_moscow(d: date, hour: int, minute: int, tz_name: str) -> datetime:
    tz = tz_from_name(tz_name)
    return datetime.combine(d, time(hour, minute), tzinfo=tz)


def format_dd_mm(d: date) -> str:
    """Устаревший формат «31 03» — предпочтительнее format_day_month_ru."""
    return f"{d.day:02d} {d.month:02d}"


_MONTHS_GENITIVE_RU = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def format_day_month_ru(d: date) -> str:
    """Человекочитаемо: «31 марта»."""
    return f"{d.day} {_MONTHS_GENITIVE_RU[d.month]}"


def days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    first = date(year, month, 1)
    return (next_month - first).days


def parse_iso(dt: str) -> datetime:
    if dt.endswith("Z"):
        dt = dt[:-1] + "+00:00"
    return datetime.fromisoformat(dt).astimezone()
