from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.config import (
    MAX_APPOINTMENTS_PER_PHONE_PER_DAY,
    SERVICES,
    load_settings,
)
from app.keyboards.admin import (
    admin_menu_kb,
    appointment_admin_kb,
    proposal_with_cancel_kb,
)
from app.keyboards.calendar import month_calendar_kb, parse_month_key
from app.keyboards.client import (
    client_main_kb,
    confirm_kb,
    share_phone_kb,
    skip_comment_kb,
)
from app.repository import Database
from app.services.phone import normalize_phone
from app.services.reminders import resync_reminder_jobs_async
from app.services.scheduling import (
    allowed_booking_dates,
    available_start_times,
    date_in_booking_window,
    format_hh_mm,
    slot_is_free,
)
from app.utils.time import format_dd_mm, moscow_today, parse_iso
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler


class ClientBooking(StatesGroup):
    service = State()
    calendar = State()
    time_pick = State()
    name = State()
    phone = State()
    comment = State()
    confirm = State()


router = Router(name="client")


def _tz() -> str:
    return load_settings().timezone


async def _notify_admins(
    bot,
    db: Database,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    for tg_id in await db.list_admin_tg_ids():
        try:
            await bot.send_message(tg_id, text, reply_markup=reply_markup)
        except Exception:
            pass


def _services_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i, s in enumerate(SERVICES):
        name = str(s["name"])
        dur = int(s["duration_minutes"])
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{name} ({dur} мин)",
                    callback_data=f"svc:{i}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _slots_kb(day: date, slots: list[datetime]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, dt in enumerate(slots):
        label = format_hh_mm(dt)
        ds = day.strftime("%Y%m%d")
        hm = dt.strftime("%H%M")
        row.append(
            InlineKeyboardButton(
                text=label, callback_data=f"st:{ds}:{hm}"
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("start"))
async def cmd_start(
    message: Message,
    db: Database,
    state: FSMContext,
) -> None:
    await state.clear()
    settings = load_settings()
    if message.from_user.id == settings.owner_tg_id:
        await db.ensure_owner(
            settings.owner_tg_id,
            message.from_user.username,
        )
    text = (
        "Привет! Я бот записи к мастеру маникюра.\n"
        "Выберите действие или нажмите «📝 Записаться»."
    )
    await message.answer(text, reply_markup=client_main_kb())
    if await db.is_admin(message.from_user.id):
        await message.answer(
            "🔐 Админ-панель:",
            reply_markup=admin_menu_kb(await db.is_owner(message.from_user.id)),
        )


@router.message(F.text == "📝 Записаться")
async def book_start(message: Message, state: FSMContext) -> None:
    await state.set_state(ClientBooking.service)
    await message.answer(
        "Выберите услугу:",
        reply_markup=_services_kb(),
    )


@router.callback_query(F.data.startswith("svc:"), StateFilter(ClientBooking.service))
async def pick_service(
    cq: CallbackQuery,
    state: FSMContext,
) -> None:
    idx = int(cq.data.split(":")[1])
    s = SERVICES[idx]
    await state.update_data(
        service_name=str(s["name"]),
        duration_minutes=int(s["duration_minutes"]),
    )
    await state.set_state(ClientBooking.calendar)
    tz = _tz()
    today = moscow_today(tz)
    first, last = allowed_booking_dates(tz)
    y, m = today.year, today.month
    try:
        await cq.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cq.message.answer(
        "Выберите день:",
        reply_markup=month_calendar_kb(y, m, today, first, last),
    )
    await cq.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Сценарий отменён. Можно начать снова: /start",
        reply_markup=client_main_kb(),
    )


@router.callback_query(F.data.startswith("cm:"), StateFilter(ClientBooking.calendar))
async def cal_month(
    cq: CallbackQuery,
    state: FSMContext,
) -> None:
    if cq.data.endswith("noop"):
        await cq.answer()
        return
    mk = cq.data.split(":")[1]
    y, m = parse_month_key(mk)
    tz = _tz()
    today = moscow_today(tz)
    first, last = allowed_booking_dates(tz)
    await cq.message.edit_reply_markup(
        reply_markup=month_calendar_kb(y, m, today, first, last)
    )
    await cq.answer()


@router.callback_query(F.data.startswith("cd:"), StateFilter(ClientBooking.calendar))
async def cal_day(
    cq: CallbackQuery,
    state: FSMContext,
    db: Database,
) -> None:
    ds = cq.data.split(":")[1]
    y = int(ds[:4])
    mo = int(ds[4:6])
    d = int(ds[6:8])
    day = date(y, mo, d)
    tz = _tz()
    if not date_in_booking_window(day, tz):
        await cq.answer("Дата недоступна", show_alert=True)
        return
    data = await state.get_data()
    dur = int(data["duration_minutes"])
    slots = await available_start_times(db, day, dur, tz)
    if not slots:
        await cq.answer()
        await cq.message.answer(
            "На этот день нет свободных слотов под выбранную услугу. "
            "Выберите другой день.",
            reply_markup=month_calendar_kb(
                day.year,
                day.month,
                moscow_today(tz),
                allowed_booking_dates(tz)[0],
                allowed_booking_dates(tz)[1],
            ),
        )
        return
    await state.update_data(day_iso=day.isoformat())
    await state.set_state(ClientBooking.time_pick)
    await cq.message.answer(
        f"Доступное время на {format_dd_mm(day)}:",
        reply_markup=_slots_kb(day, slots),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("st:"), StateFilter(ClientBooking.time_pick))
async def pick_time(
    cq: CallbackQuery,
    state: FSMContext,
) -> None:
    _, ds, hm = cq.data.split(":")
    y, m, d = int(ds[:4]), int(ds[4:6]), int(ds[6:8])
    day = date(y, m, d)
    hh, mm = int(hm[:2]), int(hm[2:])
    tz = ZoneInfo(_tz())
    start = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
    data = await state.get_data()
    dur = int(data["duration_minutes"])
    end = start + timedelta(minutes=dur)
    await state.update_data(
        start_iso=start.isoformat(),
        end_iso=end.isoformat(),
    )
    await state.set_state(ClientBooking.name)
    await cq.message.answer("Введите ваше имя:")
    await cq.answer()


@router.message(StateFilter(ClientBooking.name))
async def enter_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Имя слишком короткое. Введите ещё раз.")
        return
    await state.update_data(client_name=name)
    await state.set_state(ClientBooking.phone)
    await message.answer(
        "Укажите телефон текстом или нажмите кнопку ниже.",
        reply_markup=share_phone_kb(),
    )


@router.message(StateFilter(ClientBooking.phone), F.contact)
async def phone_contact(
    message: Message,
    state: FSMContext,
) -> None:
    phone = message.contact.phone_number or ""
    await state.update_data(phone_raw=phone)
    await state.set_state(ClientBooking.comment)
    await message.answer(
        "Комментарий к записи (необязательно):",
        reply_markup=skip_comment_kb(),
    )


@router.message(StateFilter(ClientBooking.phone), F.text)
async def phone_text(
    message: Message,
    state: FSMContext,
) -> None:
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Введите номер телефона.")
        return
    await state.update_data(phone_raw=raw)
    await state.set_state(ClientBooking.comment)
    await message.answer(
        "Комментарий к записи (необязательно):",
        reply_markup=skip_comment_kb(),
    )


@router.message(StateFilter(ClientBooking.comment), F.text == "⏭ Пропустить")
async def comment_skip(
    message: Message,
    state: FSMContext,
) -> None:
    await state.update_data(comment=None)
    await state.set_state(ClientBooking.confirm)
    await _show_summary(message, state)


@router.message(StateFilter(ClientBooking.comment))
async def comment_text(
    message: Message,
    state: FSMContext,
) -> None:
    await state.update_data(comment=(message.text or "").strip() or None)
    await state.set_state(ClientBooking.confirm)
    await _show_summary(message, state)


async def _show_summary(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    tz = ZoneInfo(_tz())
    st = datetime.fromisoformat(data["start_iso"])
    if st.tzinfo is None:
        st = st.replace(tzinfo=tz)
    day = st.date()
    dstr = format_dd_mm(day)
    tstr = format_hh_mm(st.astimezone(tz))
    phone = normalize_phone(data.get("phone_raw", ""))
    lines = [
        "Проверьте заявку:",
        f"Услуга: {data['service_name']} ({data['duration_minutes']} мин)",
        f"Дата и время: {dstr} {tstr}",
        f"Имя: {data['client_name']}",
        f"Телефон: {phone or data.get('phone_raw', '')}",
    ]
    if data.get("comment"):
        lines.append(f"Комментарий: {data['comment']}")
    await message.answer("\n".join(lines), reply_markup=confirm_kb())


@router.message(StateFilter(ClientBooking.confirm), F.text == "✏️ Изменить")
async def confirm_edit(
    message: Message,
    state: FSMContext,
) -> None:
    await state.set_state(ClientBooking.service)
    await message.answer("Выберите услугу:", reply_markup=_services_kb())


@router.message(StateFilter(ClientBooking.confirm), F.text == "✅ Подтвердить")
async def confirm_submit(
    message: Message,
    state: FSMContext,
    db: Database,
) -> None:
    data = await state.get_data()
    tz_name = _tz()
    tz = ZoneInfo(tz_name)
    st = datetime.fromisoformat(data["start_iso"])
    en = datetime.fromisoformat(data["end_iso"])
    if st.tzinfo is None:
        st = st.replace(tzinfo=tz)
    if en.tzinfo is None:
        en = en.replace(tzinfo=tz)
    phone_norm = normalize_phone(data.get("phone_raw", ""))
    if len(phone_norm) < 11:
        await message.answer("Некорректный телефон. Начните заново: /start")
        await state.clear()
        return

    ok, reason = await slot_is_free(db, st, en)
    if not ok:
        await message.answer(
            f"Слот больше недоступен ({reason}). Начните запись снова: /start"
        )
        await state.clear()
        return

    day = st.astimezone(tz).date()
    cnt = await db.count_phone_bookings_moscow_day(
        phone_norm, day, tz_name
    )
    if cnt >= MAX_APPOINTMENTS_PER_PHONE_PER_DAY:
        await message.answer(
            "На этот день у вас уже максимум записей (2) на этот номер. "
            "Выберите другой день или /start."
        )
        await state.clear()
        return

    uname = message.from_user.username if message.from_user else None
    cid = message.from_user.id
    ap_id = await db.insert_appointment(
        client_tg_id=cid,
        client_username=uname,
        client_name=data["client_name"],
        client_phone_norm=phone_norm,
        service_name=data["service_name"],
        duration_minutes=int(data["duration_minutes"]),
        start_at=st,
        end_at=en,
        status="PENDING",
        client_comment=data.get("comment"),
    )
    await state.clear()
    await message.answer(
        "Заявка отправлена. Ожидайте подтверждения мастера.",
        reply_markup=client_main_kb(),
    )
    card = (
        f"🆕 Новая заявка #{ap_id}\n"
        f"{data['client_name']} · {phone_norm}\n"
        f"{format_dd_mm(day)} {format_hh_mm(st.astimezone(tz))}\n"
        f"{data['service_name']}"
    )
    await _notify_admins(
        message.bot,
        db,
        card,
        reply_markup=appointment_admin_kb(ap_id),
    )


@router.message(F.text == "📋 Мои записи")
async def my_records(
    message: Message,
    db: Database,
) -> None:
    uid = message.from_user.id
    rows = await db.client_future_appointments(uid)
    if not rows:
        await message.answer("У вас нет активных записей.")
        return
    tz = ZoneInfo(_tz())
    for ap in rows:
        st = parse_iso(ap.start_at).astimezone(tz)
        d = st.date()
        extra = ""
        if ap.status == "RESCHEDULE_PROPOSED" and ap.proposed_start_at:
            pst = parse_iso(ap.proposed_start_at).astimezone(tz)
            extra = (
                f"\n\nПредложен перенос на {format_dd_mm(pst.date())} "
                f"{format_hh_mm(pst)}"
            )
        kb = None
        if ap.status == "RESCHEDULE_PROPOSED" and ap.proposed_start_at:
            kb = proposal_with_cancel_kb(ap.id)
        elif ap.status in ("PENDING", "CONFIRMED"):
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="❌ Отменить",
                            callback_data=f"cx:{ap.id}",
                        )
                    ]
                ]
            )
        await message.answer(
            f"#{ap.id} · {ap.status}\n"
            f"{format_dd_mm(d)} {format_hh_mm(st)} — {ap.service_name}"
            f"{extra}",
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("cx:"))
async def client_cancel(
    cq: CallbackQuery,
    db: Database,
    scheduler: AsyncIOScheduler,
) -> None:
    ap_id = int(cq.data.split(":")[1])
    ap = await db.get_appointment(ap_id)
    if ap is None or ap.client_tg_id != cq.from_user.id:
        await cq.answer("Не найдено", show_alert=True)
        return
    await db.update_status(
        ap_id, "CANCELLED", admin_reason="отмена клиентом", clear_proposed=True
    )
    await cq.answer("Отменено")
    await cq.message.edit_reply_markup(reply_markup=None)
    await cq.message.answer("Запись отменена.")
    tz = ZoneInfo(_tz())
    st = parse_iso(ap.start_at).astimezone(tz)
    text = (
        f"Клиент отменил запись #{ap_id}\n"
        f"{ap.client_name} · {ap.client_phone_norm}\n"
        f"{format_dd_mm(st.date())} {format_hh_mm(st)}"
    )
    await _notify_admins(cq.bot, db, text)
    await resync_reminder_jobs_async(
        cq.bot, db, scheduler, load_settings().timezone
    )


@router.callback_query(F.data.startswith("rs:ok:"))
async def accept_reschedule(
    cq: CallbackQuery,
    db: Database,
    scheduler: AsyncIOScheduler,
) -> None:
    ap_id = int(cq.data.split(":")[2])
    ap = await db.get_appointment(ap_id)
    if ap is None or ap.client_tg_id != cq.from_user.id:
        await cq.answer("Не найдено", show_alert=True)
        return
    if ap.status != "RESCHEDULE_PROPOSED":
        await cq.answer("Устарело", show_alert=True)
        return
    tz_name = _tz()
    tz = ZoneInfo(tz_name)
    st = parse_iso(ap.proposed_start_at).astimezone(tz)
    en = parse_iso(ap.proposed_end_at).astimezone(tz)
    ok, reason = await slot_is_free(db, st, en, exclude_appointment_id=ap_id)
    if not ok:
        await cq.answer(f"Слот занят: {reason}", show_alert=True)
        return
    await db.accept_reschedule(ap_id)
    await cq.answer()
    await cq.message.edit_reply_markup(reply_markup=None)
    await cq.message.answer("Перенос подтверждён. Ждём вас!")
    await resync_reminder_jobs_async(
        cq.bot, db, scheduler, tz_name
    )


@router.callback_query(F.data.startswith("rs:no:"))
async def decline_reschedule(
    cq: CallbackQuery,
    db: Database,
    scheduler: AsyncIOScheduler,
) -> None:
    ap_id = int(cq.data.split(":")[2])
    ap = await db.get_appointment(ap_id)
    if ap is None or ap.client_tg_id != cq.from_user.id:
        await cq.answer("Не найдено", show_alert=True)
        return
    if ap.status != "RESCHEDULE_PROPOSED":
        await cq.answer("Устарело", show_alert=True)
        return
    await db.update_status(
        ap_id,
        "DECLINED",
        admin_reason="клиент отказался от переноса",
        clear_proposed=True,
    )
    await cq.answer()
    await cq.message.edit_reply_markup(reply_markup=None)
    await cq.message.answer("Перенос отклонён.")
    await _notify_admins(
        cq.bot,
        db,
        f"Клиент отказался от переноса #{ap_id}",
    )
    await resync_reminder_jobs_async(
        cq.bot, db, scheduler, load_settings().timezone
    )
