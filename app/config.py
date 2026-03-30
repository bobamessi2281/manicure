from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    bot_token: str
    owner_tg_id: int
    database_path: str
    timezone: str


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("BOT_TOKEN is required")

    owner_raw = os.getenv("OWNER_TG_ID", "").strip()
    if not owner_raw.isdigit():
        raise ValueError(
            "В .env укажите OWNER_TG_ID — ваш числовой Telegram ID "
            "(например от @userinfobot), только цифры."
        )

    db_path = os.getenv("DATABASE_PATH", "database.db").strip()
    tz = os.getenv("TIMEZONE", "Europe/Moscow").strip()

    return Settings(
        bot_token=token,
        owner_tg_id=int(owner_raw),
        database_path=str(Path(db_path)),
        timezone=tz,
    )


# Услуги: редактируйте названия и длительность здесь (клиент может выбрать несколько)
SERVICES: list[dict[str, object]] = [
    {"name": "Маникюр классический", "duration_minutes": 60},
    {"name": "Покрытие гель-лак", "duration_minutes": 45},
    {"name": "Маникюр + покрытие", "duration_minutes": 90},
    {"name": "Наращивание", "duration_minutes": 120},
    {"name": "Педикюр", "duration_minutes": 75},
    {"name": "Маникюр + дизайн", "duration_minutes": 120},
    {"name": "Комплекс (руки+ноги)", "duration_minutes": 180},
]

# Рабочие часы (Europe/Moscow)
WORK_START_HOUR = 11
WORK_END_HOUR = 20

# Запись не дальше N дней от сегодня (включительно сегодня в пределах окна)
BOOKING_HORIZON_DAYS = 30

# Максимум записей на один номер в календарный день (Москва)
MAX_APPOINTMENTS_PER_PHONE_PER_DAY = 2

# Шаг сетки стартовых слотов (минуты)
SLOT_STEP_MINUTES = 15
