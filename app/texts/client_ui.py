"""Тексты для клиента: мягкая «салонная» подача, светлые акценты и эмодзи."""

from __future__ import annotations

import html

# Кнопки reply-клавиатуры — совпадают с F.text в handlers
BTN_BOOK = "💅 Записаться"
BTN_MY = "🤍 Мои записи"
BTN_SHARE = "📲 Поделиться контактом"
BTN_SKIP = "⏭ Пропустить"
BTN_CONFIRM = "✅ Подтвердить"
BTN_EDIT = "✏️ Изменить"


def start_welcome() -> str:
    return (
        "🤍 Привет, красотка!\n"
        "✨ Я помогу записаться к мастеру маникюра.\n\n"
        "🌸 Выберите действие ниже или нажмите «💅 Записаться»."
    )


def start_admin_hint() -> str:
    return "🔐 Админ-панель"


def pick_services_intro() -> str:
    return (
        "💅 Что делаем сегодня?\n"
        "🌸 Можно выбрать несколько услуг — отметьте и нажмите «Готово»."
    )


def pick_services_hint_selected(name: str, dur: int) -> str:
    return (
        f"🩷 Вы выбрали: {name}\n"
        f"⏱ Всего по времени: {dur} мин\n\n"
        f"{pick_services_intro()}"
    )


def pick_services_hint_empty() -> str:
    return pick_services_intro()


def calendar_intro(service_name: str, dur: int) -> str:
    return (
        f"🤍 Услуги: {service_name}\n"
        f"⏱ {dur} мин\n\n"
        "🌸 Выберите день — подсвечены только даты, где есть свободное окно."
    )


def time_pick_intro(service_name: str, day_label: str) -> str:
    return (
        f"💅 {service_name}\n\n"
        f"🕐 Свободное время на {day_label}:"
    )


def ask_name() -> str:
    return (
        "🌸 Как к вам обращаться?\n"
        "✨ Напишите имя одним сообщением:"
    )


def ask_phone() -> str:
    return (
        "📲 Оставьте номер телефона — текстом или кнопкой ниже.\n"
        "🤍 Мы свяжемся, если понадобится уточнить детали."
    )


def ask_comment() -> str:
    return (
        "💬 Хотите что-то добавить? (необязательно)\n"
        "🌸 Например: форма ногтей, пожелания по цвету…"
    )


def name_too_short() -> str:
    return "🌸 Имя пока коротковато — напишите ещё раз, пожалуйста."


def phone_invalid() -> str:
    return "🤍 Не получилось разобрать номер. Начните снова: /start"


def phone_empty() -> str:
    return "📲 Введите номер телефона текстом или поделитесь контактом."


def summary_title() -> str:
    return "✨ Проверьте, всё ли так:"


def summary_body(
    service_name: str,
    dur: int,
    date_str: str,
    time_str: str,
    client_name: str,
    phone_display: str,
    comment: str | None,
) -> str:
    lines = [
        summary_title(),
        "",
        f"💅 Услуги: {service_name}",
        f"⏱ {dur} мин",
        f"📅 {date_str} · 🕐 {time_str}",
        f"🌸 Имя: {client_name}",
        f"📲 Телефон: {phone_display}",
    ]
    if comment:
        lines.append(f"💬 Комментарий: {comment}")
    lines.append("")
    lines.append("🤍 Если всё верно — подтвердите кнопкой ниже.")
    return "\n".join(lines)


def booking_sent() -> str:
    return (
        "🌸 Заявка отправлена!\n"
        "✨ Как только мастер подтвердит — мы напишем вам здесь.\n\n"
        "🤍 Спасибо за доверие 💕"
    )


def slot_unavailable(reason: str) -> str:
    return (
        f"🥺 К сожалению, это время уже занято ({reason}).\n"
        "🌸 Давайте начнём запись снова: /start"
    )


def phone_day_limit() -> str:
    return (
        "🤍 На этот день у вас уже максимум записей на этот номер.\n"
        "🌸 Выберите другой день или начните сначала: /start"
    )


def cmd_cancel_client() -> str:
    return (
        "🌸 Запись отменена.\n"
        "✨ Когда будете готовы — /start или «💅 Записаться»."
    )


def no_records() -> str:
    return (
        "🤍 Пока нет активных записей.\n"
        "🌸 Когда захотите красоты — жмите «💅 Записаться»."
    )


def my_records_header() -> str:
    return "🤍 Ваши записи ✨"


def record_line(ap_id: int, status: str, day_s: str, time_s: str, service: str) -> str:
    return (
        f"🌸 #{ap_id} · {status}\n"
        f"   📅 {day_s} {time_s}\n"
        f"   💅 {service}"
    )


def record_reschedule_extra(day_s: str, time_s: str) -> str:
    return f"\n   🩷 Предложен перенос: {day_s} {time_s}"


def cancelled_footer() -> str:
    return "\n\n🤍 Запись отменена. Будем рады видеть вас снова ✨"


def reschedule_accepted() -> str:
    return (
        "🩷 Перенос подтверждён!\n"
        "✨ Ждём вас в назначенное время 💅"
    )


def reschedule_declined() -> str:
    return (
        "🤍 Вы остались на прежнем времени.\n"
        "🌸 Если что-то изменится — мы на связи."
    )


# ——— Уведомления от мастера (шлётся в чат клиента) ———


def master_confirmed(ap_id: int, day_s: str, time_s: str) -> str:
    return (
        f"🩷 Заявка #{ap_id} подтверждена!\n"
        f"📅 {day_s} · 🕐 {time_s}\n\n"
        "✨ До встречи — будем готовить идеальный маникюр 🤍"
    )


def master_rejected(ap_id: int, reason: str) -> str:
    safe = html.escape(reason)
    return (
        f"🥺 Заявка #{ap_id} не подошла по расписанию.\n"
        f"💬 Причина: {safe}\n\n"
        "🌸 Вы всегда можете записаться снова — мы рядом 💕"
    )


def master_cancelled(ap_id: int, reason: str) -> str:
    safe = html.escape(reason)
    return (
        f"🤍 Запись #{ap_id} отменена мастером.\n"
        f"💬 Причина: {safe}\n\n"
        "🌸 Напишите, если нужно подобрать другое время ✨"
    )


def master_propose_reschedule(ap_id: int, day_s: str, time_s: str) -> str:
    return (
        f"🩷 Предлагаем перенести запись #{ap_id}\n"
        f"📅 {day_s} · 🕐 {time_s}\n\n"
        "🌸 Нажмите кнопку ниже, если вам подходит 💅"
    )


# ——— Напоминания ———


def reminder_hours_before(hours_before: int, day_s: str, time_s: str, service: str) -> str:
    return (
        f"🤍 Нежное напоминание ✨\n"
        f"Через {hours_before} ч ваша запись.\n\n"
        f"📅 {day_s} · 🕐 {time_s}\n"
        f"💅 {service}\n\n"
        "🌸 До встречи!"
    )
