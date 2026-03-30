from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import load_settings
from app.handlers import admin as admin_handlers
from app.handlers import client as client_handlers
from app.middlewares.db import DbMiddleware
from app.middlewares.scheduler import SchedulerMiddleware
from app.repository import Database
from app.services.reminders import resync_reminder_jobs_async
from apscheduler.schedulers.asyncio import AsyncIOScheduler


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    db = Database(settings.database_path)
    await db.init()
    await db.ensure_owner(settings.owner_tg_id, None)

    bot = Bot(settings.bot_token)
    scheduler = AsyncIOScheduler()
    scheduler.start()

    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(DbMiddleware(db))
    dp.update.middleware(SchedulerMiddleware(scheduler))

    dp.include_router(admin_handlers.router)
    dp.include_router(client_handlers.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await resync_reminder_jobs_async(bot, db, scheduler, settings.timezone)

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
