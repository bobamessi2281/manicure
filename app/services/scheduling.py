from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import (
    BOOKING_HORIZON_DAYS,
    SLOT_STEP_MINUTES,
    WORK_END_HOUR,
    WORK_START_HOUR,
)
from app.repository import (
    AppointmentRow,
    Database,
    blocking_intervals_utc,
    intervals_overlap,
)
from app.utils.time import moscow_today, parse_iso


def fix_moscow_day_bounds(d: date, tz_name: str) -> tuple[datetime, datetime]:
    from datetime import time as dtime

    tz = ZoneInfo(tz_name)
    start = datetime.combine(d, dtime.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end


def work_window_for_day(d: date, tz_name: str) -> tuple[datetime, datetime]:
    from datetime import time as dtime

    tz = ZoneInfo(tz_name)
    w0 = datetime.combine(d, dtime(WORK_START_HOUR, 0), tzinfo=tz)
    w1 = datetime.combine(d, dtime(WORK_END_HOUR, 0), tzinfo=tz)
    return w0, w1


def allowed_booking_dates(tz_name: str) -> tuple[date, date]:
    today = moscow_today(tz_name)
    last = today + timedelta(days=BOOKING_HORIZON_DAYS)
    return today, last


def date_in_booking_window(d: date, tz_name: str) -> bool:
    lo, hi = allowed_booking_dates(tz_name)
    return lo <= d <= hi


async def slot_is_free(
    db: Database,
    start: datetime,
    end: datetime,
    *,
    exclude_appointment_id: int | None = None,
) -> tuple[bool, str]:
    """Проверка пересечений с заявками/записями и blocked_windows."""
    appts = await db.fetch_appointments_overlapping_range(
        start, end, exclude_id=exclude_appointment_id
    )
    for ap in appts:
        for a0, a1 in blocking_intervals_utc(ap):
            if intervals_overlap(start, end, a0, a1):
                return False, "слот уже занят"
    blocks = await db.list_blocked_between(start, end)
    for b in blocks:
        b0 = parse_iso(b["start_at"])
        b1 = parse_iso(b["end_at"])
        if intervals_overlap(start, end, b0, b1):
            return False, "время закрыто мастером"
    return True, ""


async def available_start_times(
    db: Database,
    day: date,
    duration_minutes: int,
    tz_name: str,
    exclude_appointment_id: int | None = None,
) -> list[datetime]:
    """Старты в таймзоне tz (Europe/Moscow), пригодные для выбора."""
    if not date_in_booking_window(day, tz_name):
        return []

    w0, w1 = work_window_for_day(day, tz_name)
    step = timedelta(minutes=SLOT_STEP_MINUTES)
    dur = timedelta(minutes=duration_minutes)

    day_lo, day_hi = fix_moscow_day_bounds(day, tz_name)
    appts = await db.fetch_appointments_overlapping_range(
        day_lo, day_hi, exclude_id=exclude_appointment_id
    )
    blocks = await db.list_blocked_between(day_lo, day_hi)

    busy: list[tuple[datetime, datetime]] = []
    for ap in appts:
        busy.extend(blocking_intervals_utc(ap))
    for b in blocks:
        busy.append((parse_iso(b["start_at"]), parse_iso(b["end_at"])))

    out: list[datetime] = []
    t = w0
    while t + dur <= w1:
        ok = True
        for a0, a1 in busy:
            if intervals_overlap(t, t + dur, a0, a1):
                ok = False
                break
        if ok:
            out.append(t)
        t += step
    return out


def format_hh_mm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def appointment_card_text(ap: AppointmentRow, tz_name: str) -> str:
    st = parse_iso(ap.start_at).astimezone(ZoneInfo(tz_name))
    et = parse_iso(ap.end_at).astimezone(ZoneInfo(tz_name))
    from app.utils.time import format_dd_mm

    d = st.date()
    lines = [
        f"#{ap.id} · {ap.status}",
        f"📅 {format_dd_mm(d)} · {format_hh_mm(st)}–{format_hh_mm(et)}",
        f"💅 {ap.service_name} ({ap.duration_minutes} мин)",
        f"👤 {ap.client_name} · 📞 {ap.client_phone_norm}",
    ]
    if ap.client_username:
        lines.append(f"@{ap.client_username}")
    if ap.client_comment:
        lines.append(f"💬 {ap.client_comment}")
    if ap.admin_reason:
        lines.append(f"ℹ️ {ap.admin_reason}")
    return "\n".join(lines)
