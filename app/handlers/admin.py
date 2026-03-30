from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import load_settings
from app.filters.auth import IsAdmin, IsOwner
from app.keyboards.admin import admin_menu_kb, appointment_admin_kb, proposal_client_kb
from app.keyboards.calendar import month_calendar_kb, parse_month_key
from app.repository import Database
from app.services.reminders import resync_reminder_jobs_async
from app.services.scheduling import (
    allowed_booking_dates,
    appointment_card_text,
    available_start_times,
    date_in_booking_window,
    format_hh_mm,
    slot_is_free,
)
from app.texts.client_ui import (
    master_cancelled,
    master_confirmed,
    master_propose_reschedule,
    master_rejected,
)
from app.utils.time import format_day_month_ru, moscow_today, parse_iso
from apscheduler.schedulers.asyncio import AsyncIOScheduler


class AdminStates(StatesGroup):
    bydate_cal = State()
    unblock_cal = State()
    move_cal = State()
    rs_new_cal = State()
    cancel_cal = State()
    block_cal = State()
    block_t1 = State()
    block_t2 = State()
    waiting_reason = State()


router = Router(name="admin")


def _tz() -> str:
    return load_settings().timezone


def _cal(tz: str) -> tuple:
    today = moscow_today(tz)
    lo, hi = allowed_booking_dates(tz)
    return today, lo, hi, today.year, today.month


def _admin_slots_kb(day: date, slots: list[datetime]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for dt in slots:
        label = format_hh_mm(dt)
        ds = day.strftime("%Y%m%d")
        hm = dt.strftime("%H%M")
        row.append(
            InlineKeyboardButton(text=label, callback_data=f"at:{ds}:{hm}")
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _notify_client(
    bot,
    tg_id: int,
    text: str,
    kb: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> None:
    try:
        await bot.send_message(
            tg_id, text, reply_markup=kb, parse_mode=parse_mode
        )
    except Exception:
        pass


@router.message(Command("admin"), IsAdmin())
async def cmd_admin(message: Message, db: Database) -> None:
    own = await db.is_owner(message.from_user.id)
    await message.answer("Админ-меню:", reply_markup=admin_menu_kb(own))


@router.callback_query(F.data == "adm:pending", IsAdmin())
async def adm_pending(cq: CallbackQuery, db: Database) -> None:
    rows = await db.list_pending()
    await cq.answer()
    if not rows:
        await cq.message.answer("Нет заявок в статусе PENDING.")
        return
    chat_id = cq.message.chat.id
    for ap in rows:
        text = appointment_card_text(ap, _tz())
        await cq.bot.send_message(
            chat_id,
            text,
            reply_markup=appointment_admin_kb(ap.id),
        )


@router.callback_query(F.data == "adm:all", IsAdmin())
async def adm_all_list(cq: CallbackQuery, db: Database) -> None:
    rows = await db.list_upcoming_appointments_all()
    await cq.answer()
    if not rows:
        await cq.message.answer("Нет предстоящих записей.")
        return
    tz = ZoneInfo(_tz())
    lines: list[str] = ["📋 Предстоящие записи:\n"]
    kb_rows: list[list[InlineKeyboardButton]] = []
    for ap in rows[:40]:
        st = parse_iso(ap.start_at).astimezone(tz)
        lines.append(
            f"#{ap.id} · {ap.status} · {format_day_month_ru(st.date())} {format_hh_mm(st)} · "
            f"{ap.client_name} · {ap.service_name} ({ap.duration_minutes} мин)"
        )
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 Отменить #{ap.id}",
                    callback_data=f"ac:{ap.id}",
                )
            ]
        )
    if len(rows) > 40:
        lines.append(f"\n… и ещё {len(rows) - 40} (откройте «по дате» для полного списка).")
    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4090] + "…"
    await cq.message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
    )


@router.callback_query(F.data.startswith("ap:ok:"), IsAdmin())
async def ap_confirm(
    cq: CallbackQuery,
    db: Database,
    scheduler: AsyncIOScheduler,
) -> None:
    ap_id = int(cq.data.split(":")[2])
    ap = await db.get_appointment(ap_id)
    if ap is None or ap.status != "PENDING":
        await cq.answer("Недоступно", show_alert=True)
        return
    st = parse_iso(ap.start_at)
    en = parse_iso(ap.end_at)
    ok, msg = await slot_is_free(db, st, en, exclude_appointment_id=ap_id)
    if not ok:
        await cq.answer(f"Слот уже занят: {msg}", show_alert=True)
        return
    await db.update_status(ap_id, "CONFIRMED", clear_proposed=True)
    await cq.answer("Подтверждено")
    await cq.message.edit_reply_markup(reply_markup=None)
    z = ZoneInfo(_tz())
    await _notify_client(
        cq.bot,
        ap.client_tg_id,
        master_confirmed(
            ap_id,
            format_day_month_ru(st.astimezone(z).date()),
            format_hh_mm(st.astimezone(z)),
        ),
    )
    await resync_reminder_jobs_async(cq.bot, db, scheduler, _tz())


@router.callback_query(F.data.startswith("ap:rej:"), IsAdmin())
async def ap_reject_start(cq: CallbackQuery, state: FSMContext) -> None:
    ap_id = int(cq.data.split(":")[2])
    await state.set_state(AdminStates.waiting_reason)
    await state.update_data(reason_kind="reject", appt_id=ap_id)
    await cq.answer()
    await cq.message.answer("Укажите причину отклонения (текстом):")


@router.callback_query(F.data.startswith("ap:rs:"), IsAdmin())
async def ap_reschedule_start(
    cq: CallbackQuery,
    state: FSMContext,
    db: Database,
) -> None:
    ap_id = int(cq.data.split(":")[2])
    ap = await db.get_appointment(ap_id)
    if ap is None or ap.status not in ("PENDING", "CONFIRMED", "RESCHEDULE_PROPOSED"):
        await cq.answer("Недоступно", show_alert=True)
        return
    await state.set_state(AdminStates.rs_new_cal)
    await state.update_data(rs_appt_id=ap_id)
    tz = _tz()
    today, lo, hi, y, m = _cal(tz)
    await cq.answer()
    await cq.message.answer(
        "Выберите новый день для переноса:",
        reply_markup=month_calendar_kb(y, m, today, lo, hi, "am", "ad"),
    )


@router.callback_query(
    F.data.startswith("am:"),
    StateFilter(AdminStates.rs_new_cal),
    IsAdmin(),
)
async def rs_month_am(cq: CallbackQuery) -> None:
    if cq.data.endswith("noop"):
        await cq.answer()
        return
    mk = cq.data.split(":")[1]
    y, m = parse_month_key(mk)
    tz = _tz()
    today, lo, hi, _, _ = _cal(tz)
    await cq.message.edit_reply_markup(
        reply_markup=month_calendar_kb(y, m, today, lo, hi, "am", "ad")
    )
    await cq.answer()


@router.callback_query(
    F.data.startswith("ad:"),
    StateFilter(AdminStates.rs_new_cal),
    IsAdmin(),
)
async def rs_day_ad(
    cq: CallbackQuery,
    state: FSMContext,
    db: Database,
) -> None:
    ds = cq.data.split(":")[1]
    y, mo, d = int(ds[:4]), int(ds[4:6]), int(ds[6:8])
    day = date(y, mo, d)
    tz = _tz()
    if not date_in_booking_window(day, tz):
        await cq.answer("Дата недоступна", show_alert=True)
        return
    data = await state.get_data()
    ap_id = int(data["rs_appt_id"])
    ap = await db.get_appointment(ap_id)
    if ap is None:
        await cq.answer("Ошибка", show_alert=True)
        return
    slots = await available_start_times(
        db, day, ap.duration_minutes, tz, exclude_appointment_id=ap_id
    )
    if not slots:
        await cq.answer()
        await cq.message.answer("Нет свободных слотов. Выберите другой день.")
        return
    await state.update_data(rs_day_iso=day.isoformat())
    await cq.message.answer(
        f"Время на {format_day_month_ru(day)}:",
        reply_markup=_admin_slots_kb(day, slots),
    )
    await cq.answer()


@router.callback_query(
    F.data.startswith("at:"),
    StateFilter(AdminStates.rs_new_cal),
    IsAdmin(),
)
async def rs_pick_at(
    cq: CallbackQuery,
    state: FSMContext,
    db: Database,
    scheduler: AsyncIOScheduler,
) -> None:
    _, ds, hm = cq.data.split(":")
    y, m, d = int(ds[:4]), int(ds[4:6]), int(ds[6:8])
    day = date(y, m, d)
    hh, mm = int(hm[:2]), int(hm[2:])
    tz = ZoneInfo(_tz())
    start = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
    data = await state.get_data()
    ap_id = int(data["rs_appt_id"])
    ap = await db.get_appointment(ap_id)
    if ap is None:
        await cq.answer("Ошибка", show_alert=True)
        return
    end = start + timedelta(minutes=ap.duration_minutes)
    ok, msg = await slot_is_free(db, start, end, exclude_appointment_id=ap_id)
    if not ok:
        await cq.answer(f"Слот занят: {msg}", show_alert=True)
        return
    await db.set_proposed_times(ap_id, start, end, "RESCHEDULE_PROPOSED")
    await state.clear()
    await cq.answer()
    pst = start.astimezone(tz)
    await _notify_client(
        cq.bot,
        ap.client_tg_id,
        master_propose_reschedule(
            ap_id,
            format_day_month_ru(pst.date()),
            format_hh_mm(pst),
        ),
        proposal_client_kb(ap_id),
    )
    await cq.message.answer("Клиенту отправлено предложение переноса.")
    await resync_reminder_jobs_async(cq.bot, db, scheduler, _tz())


@router.message(StateFilter(AdminStates.waiting_reason), IsAdmin())
async def reason_enter(
    message: Message,
    state: FSMContext,
    db: Database,
    scheduler: AsyncIOScheduler,
) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Причина обязательна.")
        return
    data = await state.get_data()
    kind = data.get("reason_kind")
    ap_id = int(data["appt_id"])
    ap = await db.get_appointment(ap_id)
    if ap is None:
        await state.clear()
        await message.answer("Запись не найдена.")
        return
    await state.clear()
    if kind == "reject":
        await db.update_status(ap_id, "DECLINED", admin_reason=text, clear_proposed=True)
        await _notify_client(
            message.bot,
            ap.client_tg_id,
            master_rejected(ap_id, text),
            parse_mode="HTML",
        )
        await message.answer("Отклонено, клиент уведомлён.")
        await resync_reminder_jobs_async(message.bot, db, scheduler, _tz())
    elif kind == "cancel_adm":
        await db.update_status(ap_id, "CANCELLED", admin_reason=text, clear_proposed=True)
        await _notify_client(
            message.bot,
            ap.client_tg_id,
            master_cancelled(ap_id, text),
            parse_mode="HTML",
        )
        await message.answer("Отменено, клиент уведомлён.")
        await resync_reminder_jobs_async(message.bot, db, scheduler, _tz())
    else:
        await message.answer("Неизвестное действие. Откройте /admin.")


@router.callback_query(F.data == "adm:bydate", IsAdmin())
async def adm_bydate(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.bydate_cal)
    tz = _tz()
    today, lo, hi, y, m = _cal(tz)
    await cq.answer()
    await cq.message.answer(
        "Выберите дату:",
        reply_markup=month_calendar_kb(y, m, today, lo, hi, "am", "ad"),
    )


@router.callback_query(
    F.data.startswith("am:"),
    StateFilter(AdminStates.bydate_cal),
    IsAdmin(),
)
async def bydate_month(cq: CallbackQuery) -> None:
    if cq.data.endswith("noop"):
        await cq.answer()
        return
    mk = cq.data.split(":")[1]
    y, m = parse_month_key(mk)
    tz = _tz()
    today, lo, hi, _, _ = _cal(tz)
    await cq.message.edit_reply_markup(
        reply_markup=month_calendar_kb(y, m, today, lo, hi, "am", "ad")
    )
    await cq.answer()


@router.callback_query(
    F.data.startswith("ad:"),
    StateFilter(AdminStates.bydate_cal),
    IsAdmin(),
)
async def bydate_day(cq: CallbackQuery, db: Database, state: FSMContext) -> None:
    ds = cq.data.split(":")[1]
    y, mo, d = int(ds[:4]), int(ds[4:6]), int(ds[6:8])
    day = date(y, mo, d)
    tz = _tz()
    if not date_in_booking_window(day, tz):
        await cq.answer("Дата недоступна", show_alert=True)
        return
    rows = await db.list_appointments_starting_moscow_day(day, tz)
    await cq.answer()
    await state.clear()
    if not rows:
        await cq.message.answer("На этот день записей нет.")
        return
    for ap in rows:
        await cq.message.answer(appointment_card_text(ap, tz))


@router.callback_query(F.data == "adm:block", IsAdmin())
async def adm_block(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.block_cal)
    tz = _tz()
    today, lo, hi, y, m = _cal(tz)
    await cq.answer()
    await cq.message.answer(
        "Выберите день для блокировки:",
        reply_markup=month_calendar_kb(y, m, today, lo, hi, "am", "ad"),
    )


@router.callback_query(
    F.data.startswith("am:"),
    StateFilter(AdminStates.block_cal),
    IsAdmin(),
)
async def block_month(cq: CallbackQuery) -> None:
    if cq.data.endswith("noop"):
        await cq.answer()
        return
    mk = cq.data.split(":")[1]
    y, m = parse_month_key(mk)
    tz = _tz()
    today, lo, hi, _, _ = _cal(tz)
    await cq.message.edit_reply_markup(
        reply_markup=month_calendar_kb(y, m, today, lo, hi, "am", "ad")
    )
    await cq.answer()


@router.callback_query(
    F.data.startswith("ad:"),
    StateFilter(AdminStates.block_cal),
    IsAdmin(),
)
async def block_day(cq: CallbackQuery, state: FSMContext) -> None:
    ds = cq.data.split(":")[1]
    y, mo, d = int(ds[:4]), int(ds[4:6]), int(ds[6:8])
    day = date(y, mo, d)
    tz = _tz()
    if not date_in_booking_window(day, tz):
        await cq.answer("Дата недоступна", show_alert=True)
        return
    await state.set_state(AdminStates.block_t1)
    await state.update_data(block_day_iso=day.isoformat())
    await cq.answer()
    await cq.message.answer("Введите начало интервала (Москва) в формате HH:MM")


@router.message(StateFilter(AdminStates.block_t1), IsAdmin())
async def block_t1_msg(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    try:
        hh, mm = map(int, raw.replace(":", " ").split())
    except ValueError:
        await message.answer("Формат HH:MM, например 14:30")
        return
    await state.update_data(block_h1=hh, block_m1=mm)
    await state.set_state(AdminStates.block_t2)
    await message.answer("Введите конец интервала (Москва) в формате HH:MM")


@router.message(StateFilter(AdminStates.block_t2), IsAdmin())
async def block_t2_msg(message: Message, state: FSMContext, db: Database) -> None:
    raw = (message.text or "").strip()
    try:
        hh, mm = map(int, raw.replace(":", " ").split())
    except ValueError:
        await message.answer("Формат HH:MM")
        return
    data = await state.get_data()
    day = date.fromisoformat(data["block_day_iso"])
    tz = ZoneInfo(_tz())
    h1, m1 = int(data["block_h1"]), int(data["block_m1"])
    start = datetime(day.year, day.month, day.day, h1, m1, tzinfo=tz)
    end = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
    if end <= start:
        await message.answer("Конец должен быть позже начала.")
        return
    uname = message.from_user.username if message.from_user else None
    await db.insert_blocked(start, end, uname)
    await state.clear()
    await message.answer("Интервал закрыт.")


@router.callback_query(F.data == "adm:unblock", IsAdmin())
async def adm_unblock(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.unblock_cal)
    tz = _tz()
    today, lo, hi, y, m = _cal(tz)
    await cq.answer()
    await cq.message.answer(
        "Выберите день:",
        reply_markup=month_calendar_kb(y, m, today, lo, hi, "am", "ad"),
    )


@router.callback_query(
    F.data.startswith("am:"),
    StateFilter(AdminStates.unblock_cal),
    IsAdmin(),
)
async def unblock_month(cq: CallbackQuery) -> None:
    if cq.data.endswith("noop"):
        await cq.answer()
        return
    mk = cq.data.split(":")[1]
    y, m = parse_month_key(mk)
    tz = _tz()
    today, lo, hi, _, _ = _cal(tz)
    await cq.message.edit_reply_markup(
        reply_markup=month_calendar_kb(y, m, today, lo, hi, "am", "ad")
    )
    await cq.answer()


@router.callback_query(
    F.data.startswith("ad:"),
    StateFilter(AdminStates.unblock_cal),
    IsAdmin(),
)
async def unblock_day(cq: CallbackQuery, db: Database, state: FSMContext) -> None:
    ds = cq.data.split(":")[1]
    y, mo, d = int(ds[:4]), int(ds[4:6]), int(ds[6:8])
    day = date(y, mo, d)
    tz = _tz()
    z = ZoneInfo(tz)
    lo = datetime.combine(day, dtime.min, tzinfo=z)
    hi = lo + timedelta(days=1)
    blocks = await db.list_blocked_between(lo, hi)
    await cq.answer()
    await state.clear()
    if not blocks:
        await cq.message.answer("Нет закрытых окон на этот день.")
        return
    for b in blocks:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"Удалить #{b['id']}",
                        callback_data=f"ub:{b['id']}",
                    )
                ]
            ]
        )
        s = parse_iso(b["start_at"]).astimezone(z)
        e = parse_iso(b["end_at"]).astimezone(z)
        await cq.message.answer(
            f"#{b['id']} · {format_hh_mm(s)}–{format_hh_mm(e)}",
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("ub:"), IsAdmin())
async def unblock_delete(cq: CallbackQuery, db: Database) -> None:
    bid = int(cq.data.split(":")[1])
    ok = await db.delete_blocked(bid)
    await cq.answer("Удалено" if ok else "Не найдено", show_alert=not ok)
    await cq.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data == "adm:move", IsAdmin())
async def adm_move(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.move_cal)
    tz = _tz()
    today, lo, hi, y, m = _cal(tz)
    await cq.answer()
    await cq.message.answer(
        "Выберите день, чтобы увидеть записи:",
        reply_markup=month_calendar_kb(y, m, today, lo, hi, "am", "ad"),
    )


@router.callback_query(
    F.data.startswith("am:"),
    StateFilter(AdminStates.move_cal),
    IsAdmin(),
)
async def move_month(cq: CallbackQuery) -> None:
    if cq.data.endswith("noop"):
        await cq.answer()
        return
    mk = cq.data.split(":")[1]
    y, m = parse_month_key(mk)
    tz = _tz()
    today, lo, hi, _, _ = _cal(tz)
    await cq.message.edit_reply_markup(
        reply_markup=month_calendar_kb(y, m, today, lo, hi, "am", "ad")
    )
    await cq.answer()


@router.callback_query(
    F.data.startswith("ad:"),
    StateFilter(AdminStates.move_cal),
    IsAdmin(),
)
async def move_day(cq: CallbackQuery, db: Database) -> None:
    ds = cq.data.split(":")[1]
    y, mo, d = int(ds[:4]), int(ds[4:6]), int(ds[6:8])
    day = date(y, mo, d)
    tz = _tz()
    if not date_in_booking_window(day, tz):
        await cq.answer("Дата недоступна", show_alert=True)
        return
    rows = await db.list_appointments_starting_moscow_day(day, tz)
    rows = [r for r in rows if r.status in ("PENDING", "CONFIRMED", "RESCHEDULE_PROPOSED")]
    await cq.answer()
    if not rows:
        await cq.message.answer("Нет заявок на этот день.")
        return
    for ap in rows:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"Перенести #{ap.id}",
                        callback_data=f"mv:{ap.id}",
                    )
                ]
            ]
        )
        await cq.message.answer(
            appointment_card_text(ap, tz),
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("mv:"), IsAdmin())
async def move_pick(
    cq: CallbackQuery,
    state: FSMContext,
    db: Database,
) -> None:
    ap_id = int(cq.data.split(":")[1])
    ap = await db.get_appointment(ap_id)
    if ap is None:
        await cq.answer("Не найдено", show_alert=True)
        return
    await state.set_state(AdminStates.rs_new_cal)
    await state.update_data(rs_appt_id=ap_id)
    tz = _tz()
    today, lo, hi, y, m = _cal(tz)
    await cq.answer()
    await cq.message.answer(
        "Выберите новый день:",
        reply_markup=month_calendar_kb(y, m, today, lo, hi, "am", "ad"),
    )


@router.callback_query(F.data == "adm:cancelap", IsAdmin())
async def adm_cancel(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.cancel_cal)
    tz = _tz()
    today, lo, hi, y, m = _cal(tz)
    await cq.answer()
    await cq.message.answer(
        "Выберите день:",
        reply_markup=month_calendar_kb(y, m, today, lo, hi, "am", "ad"),
    )


@router.callback_query(
    F.data.startswith("am:"),
    StateFilter(AdminStates.cancel_cal),
    IsAdmin(),
)
async def cancel_month(cq: CallbackQuery) -> None:
    if cq.data.endswith("noop"):
        await cq.answer()
        return
    mk = cq.data.split(":")[1]
    y, m = parse_month_key(mk)
    tz = _tz()
    today, lo, hi, _, _ = _cal(tz)
    await cq.message.edit_reply_markup(
        reply_markup=month_calendar_kb(y, m, today, lo, hi, "am", "ad")
    )
    await cq.answer()


@router.callback_query(
    F.data.startswith("ad:"),
    StateFilter(AdminStates.cancel_cal),
    IsAdmin(),
)
async def cancel_day(cq: CallbackQuery, db: Database) -> None:
    ds = cq.data.split(":")[1]
    y, mo, d = int(ds[:4]), int(ds[4:6]), int(ds[6:8])
    day = date(y, mo, d)
    tz = _tz()
    if not date_in_booking_window(day, tz):
        await cq.answer("Дата недоступна", show_alert=True)
        return
    rows = await db.list_appointments_starting_moscow_day(day, tz)
    rows = [r for r in rows if r.status in ("PENDING", "CONFIRMED", "RESCHEDULE_PROPOSED")]
    await cq.answer()
    if not rows:
        await cq.message.answer("Нет записей.")
        return
    for ap in rows:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"Отменить #{ap.id}",
                        callback_data=f"ac:{ap.id}",
                    )
                ]
            ]
        )
        await cq.message.answer(
            appointment_card_text(ap, tz),
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("ac:"), IsAdmin())
async def cancel_pick(cq: CallbackQuery, state: FSMContext) -> None:
    ap_id = int(cq.data.split(":")[1])
    await state.set_state(AdminStates.waiting_reason)
    await state.update_data(reason_kind="cancel_adm", appt_id=ap_id)
    await cq.answer()
    await cq.message.answer("Укажите причину отмены (текстом):")


@router.callback_query(F.data == "adm:users", IsAdmin(), IsOwner())
async def adm_users(cq: CallbackQuery, db: Database) -> None:
    rows = await db.list_admins()
    lines = [
        f"· {r['role']}: tg_id={r['tg_id']} @{r['username'] or '—'}" for r in rows
    ]
    await cq.answer()
    await cq.message.answer("Админы:\n" + "\n".join(lines))


@router.message(Command("addadmin"), IsAdmin(), IsOwner())
async def add_admin_cmd(message: Message, db: Database) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /addadmin <tg_id>")
        return
    if not parts[1].isdigit():
        await message.answer("Нужен числовой Telegram ID (например: @userinfobot).")
        return
    tid = int(parts[1])
    await db.add_admin(tid, None, "admin")
    await message.answer("Админ добавлен.")


@router.message(Command("deladmin"), IsAdmin(), IsOwner())
async def del_admin_cmd(message: Message, db: Database) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /deladmin <tg_id>")
        return
    if not parts[1].isdigit():
        await message.answer("Нужен числовой Telegram ID.")
        return
    tid = int(parts[1])
    settings = load_settings()
    if tid == settings.owner_tg_id:
        await message.answer("Нельзя удалить владельца.")
        return
    ok = await db.remove_admin_by_tg_id(tid)
    await message.answer("Удалено." if ok else "Не найден или нельзя удалить.")
