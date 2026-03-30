from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.repository import Database
from app.texts.client_ui import refresh_manicure_reminder, reminder_hours_before
from app.utils.time import format_day_month_ru, parse_iso
from zoneinfo import ZoneInfo


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _send_reminder(
    bot: Bot,
    db: Database,
    appt_id: int,
    hours_before: int,
    tz_name: str,
) -> None:
    ap = await db.get_appointment(appt_id)
    if ap is None or ap.status != "CONFIRMED":
        return
    if hours_before == 24 and ap.reminder_24_sent:
        return
    if hours_before == 12 and ap.reminder_12_sent:
        return

    st = parse_iso(ap.start_at).astimezone(ZoneInfo(tz_name))
    d = st.date()
    text = reminder_hours_before(
        hours_before,
        format_day_month_ru(d),
        st.strftime("%H:%M"),
        ap.service_name,
    )
    try:
        await bot.send_message(ap.client_tg_id, text)
    except Exception:
        return

    if hours_before == 24:
        await db.set_reminder_flags(appt_id, r24=True)
    else:
        await db.set_reminder_flags(appt_id, r12=True)


async def _send_refresh_30(
    bot: Bot,
    db: Database,
    appt_id: int,
    tz_name: str,
) -> None:
    ap = await db.get_appointment(appt_id)
    if ap is None or ap.status != "CONFIRMED" or ap.refresh_30_sent:
        return
    st = parse_iso(ap.start_at).astimezone(ZoneInfo(tz_name))
    day_s = format_day_month_ru(st.date())
    text = refresh_manicure_reminder(ap.service_name, day_s)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💅 Записаться снова",
                    callback_data="bk:start",
                )
            ]
        ]
    )
    try:
        await bot.send_message(ap.client_tg_id, text, reply_markup=kb)
    except Exception:
        return
    await db.set_refresh_30_sent(appt_id)


async def resync_reminder_jobs_async(
    bot: Bot,
    db: Database,
    scheduler: AsyncIOScheduler,
    tz_name: str,
) -> None:
    for job in list(scheduler.get_jobs()):
        jid = job.id
        if (
            jid.startswith("rem24_")
            or jid.startswith("rem12_")
            or jid.startswith("refresh30_")
        ):
            scheduler.remove_job(jid)

    apts = await db.list_confirmed_future_for_reminders()
    now = _utc_now()
    for ap in apts:
        st = parse_iso(ap.start_at)
        if st.tzinfo is None:
            st = st.replace(tzinfo=timezone.utc)
        else:
            st = st.astimezone(timezone.utc)

        if not ap.reminder_24_sent:
            run_at = st - timedelta(hours=24)
            if run_at > now:
                scheduler.add_job(
                    _send_reminder,
                    "date",
                    run_date=run_at,
                    args=[bot, db, ap.id, 24, tz_name],
                    id=f"rem24_{ap.id}",
                    replace_existing=True,
                    misfire_grace_time=3600,
                )

        if not ap.reminder_12_sent:
            run_at = st - timedelta(hours=12)
            if run_at > now:
                scheduler.add_job(
                    _send_reminder,
                    "date",
                    run_date=run_at,
                    args=[bot, db, ap.id, 12, tz_name],
                    id=f"rem12_{ap.id}",
                    replace_existing=True,
                    misfire_grace_time=3600,
                )

    refresh_rows = await db.list_confirmed_for_refresh_30()
    for ap in refresh_rows:
        en = parse_iso(ap.end_at)
        if en.tzinfo is None:
            en = en.replace(tzinfo=timezone.utc)
        else:
            en = en.astimezone(timezone.utc)
        run_at = en + timedelta(days=30)
        if run_at <= now:
            await _send_refresh_30(bot, db, ap.id, tz_name)
        else:
            scheduler.add_job(
                _send_refresh_30,
                "date",
                run_date=run_at,
                args=[bot, db, ap.id, tz_name],
                id=f"refresh30_{ap.id}",
                replace_existing=True,
                misfire_grace_time=3600,
            )
