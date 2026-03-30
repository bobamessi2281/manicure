from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_menu_kb(is_owner: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="🧾 Заявки", callback_data="adm:pending"
            ),
        ],
        [
            InlineKeyboardButton(
                text="📅 Записи по дате", callback_data="adm:bydate"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🚫 Закрыть время", callback_data="adm:block"
            ),
        ],
        [
            InlineKeyboardButton(
                text="✅ Открыть время", callback_data="adm:unblock"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔁 Перенести запись", callback_data="adm:move"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🗑 Отменить запись", callback_data="adm:cancelap"
            ),
        ],
    ]
    if is_owner:
        rows.append(
            [
                InlineKeyboardButton(
                    text="👤 Админы", callback_data="adm:users"
                ),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def appointment_admin_kb(appt_id: int) -> InlineKeyboardMarkup:
    aid = str(appt_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data=f"ap:ok:{aid}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить", callback_data=f"ap:rej:{aid}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Другое время", callback_data=f"ap:rs:{aid}"
                ),
            ],
        ]
    )


def proposal_client_kb(appt_id: int) -> InlineKeyboardMarkup:
    aid = str(appt_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять", callback_data=f"rs:ok:{aid}"
                ),
                InlineKeyboardButton(
                    text="❌ Отказаться", callback_data=f"rs:no:{aid}"
                ),
            ],
        ]
    )


def proposal_with_cancel_kb(appt_id: int) -> InlineKeyboardMarkup:
    """Перенос + отмена записи (для «Мои записи»)."""
    aid = str(appt_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять", callback_data=f"rs:ok:{aid}"
                ),
                InlineKeyboardButton(
                    text="❌ Отказаться", callback_data=f"rs:no:{aid}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить запись", callback_data=f"cx:{aid}"
                ),
            ],
        ]
    )
