from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.repository import Database


class IsAdmin(Filter):
    async def __call__(self, event: TelegramObject, db: Database) -> bool:
        uid = _user_id(event)
        if uid is None:
            return False
        return await db.is_admin(uid)


class IsOwner(Filter):
    async def __call__(self, event: TelegramObject, db: Database) -> bool:
        uid = _user_id(event)
        if uid is None:
            return False
        return await db.is_owner(uid)


def _user_id(event: TelegramObject) -> int | None:
    if isinstance(event, Message) and event.from_user:
        return event.from_user.id
    if isinstance(event, CallbackQuery) and event.from_user:
        return event.from_user.id
    return None
