from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.texts.client_ui import (
    BTN_BOOK,
    BTN_CONFIRM,
    BTN_EDIT,
    BTN_MY,
    BTN_SHARE,
    BTN_SKIP,
)


def client_main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_BOOK),
                KeyboardButton(text=BTN_MY),
            ],
        ],
        resize_keyboard=True,
    )


def share_phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_SHARE, request_contact=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def skip_comment_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SKIP)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def confirm_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_CONFIRM),
                KeyboardButton(text=BTN_EDIT),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
