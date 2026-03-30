# Telegram-бот записи к мастеру маникюра

Стек: **Python 3.11+**, **aiogram v3**, **SQLite** (`database.db`), **APScheduler** (напоминания), таймзона **Europe/Moscow**.

## Возможности

- Заявка клиента → **PENDING**, запись активна после **CONFIRMED** админом.
- Напоминания **за 24 ч и 12 ч** только для **CONFIRMED**.
- Не больше **2** записей на **один нормализованный телефон** в **календарный день по Москве**.
- Рабочие часы **11:00–20:00**, запись на **30 дней** вперёд, слоты с шагом **15** минут.
- Админы: **OWNER** в переменных окружения, остальные через `/addadmin` / `/deladmin` (по **tg_id**).

## Как пользоваться ботом (без терминала на Mac)

**Рабочий режим:** бот крутится в **Railway**, вы общаетесь с ним только в **Telegram**. На Mac не нужно ничего запускать вручную в Terminal.

1. Залейте код на **GitHub** (удобно через [GitHub Desktop](https://desktop.github.com/) — без команд в терминале).
2. В [Railway](https://railway.app) подключите репозиторий и задайте переменные (см. ниже).
3. После деплоя откройте бота в Telegram и нажмите **/start**.

Секреты (`BOT_TOKEN`, `OWNER_TG_ID`) только в **Railway → Variables** и в **`.env` локально** (файл `.env` в git не коммитится).

---

## Запуск в Railway (основной способ)

**В репозиторий не коммить** `.env`.

### Код на GitHub

- Репозиторий можно создать и загрузить файлы через **веб-интерфейс GitHub** или **GitHub Desktop** (без `git` в терминале, если так удобнее).

### Проект на Railway

1. [Railway](https://railway.app) → **New Project** → **Deploy from GitHub repo** → выберите репозиторий.
2. Вкладка **Variables** — добавьте:

| Переменная       | Описание |
|------------------|----------|
| `BOT_TOKEN`      | токен от @BotFather |
| `OWNER_TG_ID`    | ваш числовой Telegram ID |
| `TIMEZONE`       | `Europe/Moscow` (опционально) |
| `DATABASE_PATH`  | см. ниже про том |

3. **Start command** уже задан в `railway.toml` и `Procfile`: `python -m app.main`.

### SQLite и том

Без постоянного диска файл БД пропадёт при перезапуске. В Railway:

1. Добавьте **Volume**, смонтируйте, например, в `/data`.
2. Установите переменную: `DATABASE_PATH=/data/database.db`.

---

## Опционально: локальный запуск на компьютере

Нужен только если вы **разрабатываете** бота и хотите гонять его на своей машине. Обычно для работы салона это не требуется.

1. Python **3.11+**, `cp .env.example .env`, заполните `BOT_TOKEN`, `OWNER_TG_ID`.
2. `pip install -r requirements.txt` и `python -m app.main` (или запуск из IDE).

При первом запуске создаётся `database.db` (если не задан другой путь).

---

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
