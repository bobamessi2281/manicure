from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Tuple

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def _month_key(y: int, m: int) -> str:
    return f"{y:04d}{m:02d}"


def parse_month_key(s: str) -> tuple[int, int]:
    return int(s[:4]), int(s[4:6])


def _shift_month(y: int, m: int, delta: int) -> tuple[int, int]:
    d = date(y, m, 1) + timedelta(days=32 * delta)
    return d.year, d.month


def month_title_ru(y: int, m: int) -> str:
    months = (
        "янв",
        "фев",
        "мар",
        "апр",
        "май",
        "июн",
        "июл",
        "авг",
        "сен",
        "окт",
        "ноя",
        "дек",
    )
    return f"{months[m - 1]} {y}"


def month_calendar_kb(
    year: int,
    month: int,
    today: date,
    first_allowed: date,
    last_allowed: date,
    nav_prefix: str = "cm",
    day_prefix: str = "cd",
) -> InlineKeyboardMarkup:
    """Inline-календарь: дни 1..31, навигация ◀️/▶️.

    nav_prefix/day_prefix — префиксы callback (клиент: cm/cd, админ: am/ad).
    """
    mk = _month_key(year, month)
    prev_y, prev_m = _shift_month(year, month, -1)
    next_y, next_m = _shift_month(year, month, 1)
    prev_mk = _month_key(prev_y, prev_m)
    next_mk = _month_key(next_y, next_m)
    noop = f"{nav_prefix}:noop"

    rows: list[list[InlineKeyboardButton]] = []
    rows.append(
        [
            InlineKeyboardButton(
                text="◀️", callback_data=f"{nav_prefix}:{prev_mk}"
            ),
            InlineKeyboardButton(
                text=month_title_ru(year, month), callback_data=noop
            ),
            InlineKeyboardButton(
                text="▶️", callback_data=f"{nav_prefix}:{next_mk}"
            ),
        ]
    )

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)
    for week in weeks:
        row: list[InlineKeyboardButton] = []
        for d in week:
            if d.month != month:
                row.append(InlineKeyboardButton(text="·", callback_data=noop))
                continue
            label = str(d.day)
            if d < first_allowed or d > last_allowed:
                row.append(
                    InlineKeyboardButton(text=f"·{label}", callback_data=noop)
                )
            else:
                ds = d.strftime("%Y%m%d")
                row.append(
                    InlineKeyboardButton(
                        text=label, callback_data=f"{day_prefix}:{ds}"
                    )
                )
        rows.append(row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_day_key(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()
