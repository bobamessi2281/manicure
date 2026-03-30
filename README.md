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

**В репозиторий не коммить** `.env` (токен и ID только в переменных Railway).

### 1. GitHub

Создайте пустой репозиторий на GitHub, затем в каталоге проекта:

```bash
git remote add origin https://github.com/ВАШ_ЛОГИН/ИМЯ_РЕПО.git
git branch -M main
git push -u origin main
```

(или SSH: `git@github.com:ВАШ_ЛОГИН/ИМЯ_РЕПО.git`)

### 2. Проект на Railway

1. [Railway](https://railway.app) → **New Project** → **Deploy from GitHub repo** → выберите репозиторий.
2. Вкладка **Variables** — добавьте:

| Переменная       | Пример / описание |
|------------------|-------------------|
| `BOT_TOKEN`      | токен от @BotFather |
| `OWNER_TG_ID`    | ваш числовой Telegram ID |
| `TIMEZONE`       | `Europe/Moscow` (опционально) |
| `DATABASE_PATH`  | см. ниже про том |

3. **Start command** задаётся в `railway.toml` и `Procfile`: `python -m app.main`.

### 3. SQLite и том

Без постоянного диска файл БД пропадёт при перезапуске. В Railway:

1. Добавьте **Volume**, смонтируйте, например, в `/data`.
2. Установите переменную: `DATABASE_PATH=/data/database.db`.

Локально по умолчанию используется `database.db` в корне (см. `.env.example`).

## Команды (OWNER)

- `/addadmin <tg_id>` — добавить админа
- `/deladmin <tg_id>` — удалить админа (не OWNER)

## Структура проекта

```
manicure/
├── .env.example
├── Procfile
├── railway.toml
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
