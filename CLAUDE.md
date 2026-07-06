# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Телеграм-бот + Mini App учёта времени на увлечениях. Первичная БД — Google Sheets;
вся запись идёт через журнал-буфер на диске (см. «Архитектура»). Пользовательский
сценарий и деплой — в `README.md`. Спека архитектуры:
`docs/superpowers/specs/2026-07-06-mini-app-input-design.md`.

## Команды

```bash
python main.py                 # локальный запуск (нужны .env + service_account.json)
pytest tests/                  # тесты (36 шт.); зависимости: pip install -r requirements-dev.txt
docker compose up -d           # прод-запуск; caddy-docker-proxy подхватывает по labels
docker compose logs -f         # логи
```

- Прод: orion.artfaal.ru, `/var/docker/compose/hobby-tracker` (git-чекаут GitHub).
  Деплой = push → `git pull` на сервере → `docker compose build && up -d`.
  Домен: https://hobby.artfaal.ru (caddy сам получает сертификат).
- **Не запускай `python main.py` локально с прод-токеном, пока прод жив** — два
  поллера на один токен = 409 Conflict.
- venv в репо — Python 3.13, Docker — `python:3.11-slim`. Целевая версия 3.11+.
- Локальная отладка API без Telegram: `AUTH_DISABLED=1` (только локально!).

## Архитектура

Один asyncio-процесс (`main.py:amain`): PTB-бот (polling, ручной lifecycle),
uvicorn/FastAPI на :8000 (API + статика Mini App), sync-воркер, APScheduler.

```
бот (handlers) ──┐
                 ├─ runtime.record_entry ─ journal.jsonl ─ SyncWorker ─> Google Sheets
Mini App (API) ──┘         │                                                │
                           └─ DayCache (7 дней) <── чтение/стартовая сверка ┘
```

- `src/runtime.py` — синглтоны процесса (journal, cache, wake, sheets_lock) и
  **единственный путь записи** `record_entry()` + чтение `get_day_values()`.
  Прямых вызовов `SheetsManager.write_values` из хендлеров/API быть не должно.
- `src/data/journal.py` — append-only jsonl + offset слитых строк. Битые строки
  (обрыв при падении) пропускаются с warning; append защищён от приклеивания к
  оборванному хвосту. Offset двигается **только после успешной записи в Sheets**.
- `src/data/sync_worker.py` — будится по `runtime.wake`, компактит батч
  (последнее значение на пару date+hobby побеждает), retry с backoff до 60с.
- `src/data/daycache.py` — снапшот последних 7 дней (`data/cache/days.json`) +
  `merged()` — оверлей несинканного журнала. Старше 7 дней — прямое чтение Sheets.
- `src/api/` — `auth.py` (HMAC initData, allowlist `ALLOWED_USER_IDS`),
  `server.py` (`GET /api/hobbies`, `GET /api/day/{date}`, `POST /api/entry`,
  `GET /api/queue`). Ответы `/api/*` несут `queue_pending` (число несинканных
  записей); лёгкий `GET /api/queue` фронт опрашивает после записи, пока не 0.
- `frontend/index.html` — Mini App, vanilla JS без сборки. Пресеты часов
  захардкожены там (0.5–3.5 шагом 0.5, дальше целыми до 15); `data/stars.txt`
  влияет только на кнопки бота.
- `src/bot/` — Telegram UI (fallback-ввод), `src/utils/scheduler.py` — напоминания.

### Ключевые вещи, которые нужно знать до правок

- **Все вызовы gspread — через `asyncio.to_thread` под `runtime.sheets_lock`**
  (gspread не thread-safe, и синхронный вызов в хендлере заблокирует event loop —
  именно от этого избавлялись).
- **Состояние диалога бота — глобальный dict `user_states`** (`handlers.py`),
  в памяти, один процесс. Значения-префиксы: `selected_date:<date>`,
  `waiting_new_hobby:<date>`, `awaiting_custom_stars:<hobby>:<date>`,
  `awaiting_alias`, `stats_mode`.
- **Роутинг колбэков — по префиксу `callback_data`** в `button_callback`,
  цепочка `if/elif`, **порядок веток важен** (точные до префиксных). Формат —
  через `:`; двоеточие в ключе хобби недопустимо (API это валидирует).
- **`norm_hobby(name)`** (`files.py`) — канонизация ключа: strip/lower/ё→е.
  Ключ сопоставления для колонок Sheets и алиасов. Красивое имя —
  `get_hobby_display_name` (fallback `📌 Capitalized`).
- **`date_for_time()` ≠ `today_str()`** (`utils/dates.py`): первое — «день для
  записи» (до 6 утра = вчера), это «сегодня» в UI и `default_date` API.
- **`config.validate_config()`** зовётся в `main()`, НЕ при импорте — тесты
  живут без .env (см. `tests/conftest.py`).
- **Runtime-данные не в git**: `data/journal.jsonl`, `data/journal.offset`,
  `data/cache/` — в `.gitignore`, живут на docker volume.
- **Значение 0 валидно** («не было», пишется в ячейку); фронт показывает
  заполненными только значения > 0.
- **Порядок плиток Mini App** = порядок `data/hobbies_history.txt` (недавние
  сверху); `record_entry` обновляет историю автоматически.

## Конвенции

- Коммиты: Conventional Commits, заголовок `<type>: <описание>`, описание на
  русском формой «Добавлен X» (не «Добавил X»).
- Документацию (`README.md`, этот файл) держим в актуальном состоянии при
  изменении поведения.
