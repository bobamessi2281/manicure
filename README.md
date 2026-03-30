# Telegram-бот записи к мастеру маникюра

Стек: **Python 3.11+**, **aiogram v3**, **SQLite** (`database.db`), **APScheduler** (напоминания), таймзона **Europe/Moscow**.

## Возможности

- Заявка клиента → **PENDING**, запись активна после **CONFIRMED** админом.
- Напоминания **за 24 ч и 12 ч** только для **CONFIRMED**.
- Не больше **2** записей на **один нормализованный телефон** в **календарный день по Москве**.
- Рабочие часы **11:00–20:00**, запись на **30 дней** вперёд, слоты с шагом **15** минут.
- Админы: **OWNER** в `.env`, остальные через `/addadmin` / `/deladmin` (по **tg_id**).

## Локальный запуск

1. Python **3.11+** (рекомендуется).

2. Скопируйте окружение:

   ```bash
   cp .env.example .env
   ```

3. Заполните в `.env`:

   - `BOT_TOKEN` — токен от [@BotFather](https://t.me/BotFather)
   - `OWNER_TG_ID` — числовой Telegram ID владельца (можно узнать у [@userinfobot](https://t.me/userinfobot))
   - при необходимости `DATABASE_PATH`, `TIMEZONE`

4. Установка зависимостей и запуск:

   ```bash
   pip install -r requirements.txt
   python -m app.main
   ```

При первом запуске создаётся файл БД (по умолчанию `database.db`) и таблицы.

## Railway

1. Репозиторий на GitHub, проект на [Railway](https://railway.app) с подключением репозитория.

2. Переменные окружения: те же, что в `.env` (`BOT_TOKEN`, `OWNER_TG_ID`, …).

3. **Start command** (или `Procfile`):

   ```bash
   python -m app.main
   ```

4. Диск: для сохранения SQLite между деплоями подключите **Volume** и укажите путь, например:

   - `DATABASE_PATH=/data/database.db`

   и смонтируйте том в `/data`.

## Команды (OWNER)

- `/addadmin <tg_id>` — добавить админа
- `/deladmin <tg_id>` — удалить админа (не OWNER)

## Структура проекта

```
manicure/
├── .env.example
├── Procfile
├── README.md
├── requirements.txt
├── runtime.txt
└── app/
    ├── main.py
    ├── config.py
    ├── db.py
    ├── repository.py
    ├── middlewares/
    │   ├── db.py
    │   └── scheduler.py
    ├── filters/
    │   └── auth.py
    ├── keyboards/
    │   ├── calendar.py
    │   ├── client.py
    │   └── admin.py
    ├── services/
    │   ├── phone.py
    │   ├── scheduling.py
    │   └── reminders.py
    ├── utils/
    │   └── time.py
    └── handlers/
        ├── client.py
        └── admin.py
```

- `app/main.py` — точка входа, polling, планировщик напоминаний
- `app/config.py` — настройки и список **услуг** (название + длительность)
- `app/db.py` — SQL-схема
- `app/repository.py` — доступ к БД
- `app/services/scheduling.py` — слоты и пересечения
- `app/services/reminders.py` — APScheduler
- `app/handlers/client.py`, `app/handlers/admin.py` — сценарии

Клиент: `/cancel` — сброс незавершённой записи (FSM).
