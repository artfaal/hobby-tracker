# 🎯 Hobby Tracker Bot

Telegram-бот и Mini App для отслеживания увлечений с хранением данных в Google Sheets.

## 🌟 Возможности

- ⚡ **Mini App** (https://hobby.artfaal.ru) — основной способ ввода: сетка всех активностей одним экраном, тап по плитке → пресеты часов, мгновенный отклик
- 🛡️ **Надёжная запись**: журнал-буфер на диске + фоновый синк в Google Sheets с retry — ни одна запись не теряется, даже если Sheets недоступен
- 📈 **Google Sheets — первичная БД**: данные всегда доступны и переносимы независимо от приложения
- ⭐ **Гибкая система времени**: от 0.5 до 15 часов пресетами, custom-ввод любых значений 0–24
- 🚀 **Бот-fallback**: старый ввод инлайн-кнопками работает как раньше (только быстрее)
- 📊 **Статистика**: по дням, за 7 дней с графиком, топ-3 за последние 7 и 30 дней
- 🌍 **Умная дата**: записи до 6 утра относятся к предыдущему дню
- ⏰ **Напоминания**: настраиваемые, с полной статистикой дня
- 📝 **Алиасы с эмодзи**: красивые названия активностей

## 🏗 Архитектура

Один процесс (один контейнер), внутри asyncio:

```
Telegram ──── бот (PTB, polling) ────┐
                                     ├── record_entry ── journal.jsonl ── sync-воркер ──> Google Sheets
Mini App ──── HTTP API (FastAPI) ────┘        │                                              │
  (статика с того же сервера)                 └── DayCache (7 дней) <── чтение/сверка ───────┘
```

- **Запись** (бот и Mini App) идёт через `src/runtime.py:record_entry()` → append в `data/journal.jsonl` → мгновенный ответ UI. Фоновый воркер (`src/data/sync_worker.py`) сливает журнал в Sheets батчами с retry/backoff; offset двигается только после успешной записи. Рестарт контейнера доигрывает несинканный хвост.
- **Чтение** — из `DayCache` (`data/cache/days.json`, последние 7 дней) с оверлеем несинканного журнала; старые даты — напрямую из Sheets.
- **Auth Mini App** — HMAC-проверка Telegram `initData` + allowlist `ALLOWED_USER_IDS`.

## 🛠 Установка и настройка

### Требования

- Python 3.11+ (Docker: `python:3.11-slim`)
- Telegram Bot Token
- Google Sheets API с Service Account
- Для Mini App: HTTPS-домен (прод использует caddy-docker-proxy)

### Быстрый старт

1. **Клонируйте репозиторий**
   ```bash
   git clone https://github.com/artfaal/hobby-tracker.git
   cd hobby-tracker
   ```

2. **Установите зависимости**
   ```bash
   pip install -r requirements.txt
   ```

3. **Настройте окружение**
   ```bash
   cp .env.example .env
   # Отредактируйте .env файл со своими данными
   ```

4. **Настройте Google Sheets API**
   - Создайте проект в Google Cloud Console
   - Включите Google Sheets API
   - Создайте Service Account и скачайте JSON ключ
   - Поместите файл как `service_account.json`
   - Предоставьте доступ к таблице вашему Service Account

5. **Запустите**
   ```bash
   python main.py
   ```

### Тесты

```bash
pip install -r requirements-dev.txt
pytest tests/
```

Покрыто ядро надёжности: журнал (offset, битые строки, компактация), sync-воркер (retry, батч), кэш с оверлеем, auth, API.

## 🐳 Docker / Деплой

```bash
cp .env.example .env   # заполнить
docker compose up -d
```

Прод (orion): caddy-docker-proxy подхватывает контейнер по labels в `docker-compose.yml` (`caddy: hobby.artfaal.ru` + external network `caddy`), сам получает сертификат. Порт наружу не пробрасывается. URL Mini App прописывается в menu button бота автоматически при старте (`WEBAPP_URL`).

### Переменные окружения

| Переменная | Описание | Обязательная |
|------------|----------|--------------|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | ✅ |
| `SPREADSHEET_ID` | ID Google таблицы | ✅ |
| `ALLOWED_USER_IDS` | user_id через запятую — кому доступен Mini App | ✅ для Mini App |
| `WEBAPP_URL` | URL Mini App (menu button) | для Mini App |
| `SHEET_NAME` | Название листа (по умолчанию: «Данные») | ❌ |
| `TIMEZONE` | Часовой пояс (по умолчанию: Europe/Moscow) | ❌ |
| `API_PORT` | Порт HTTP API (по умолчанию: 8000) | ❌ |
| `AUTH_DISABLED` | `1` = API без auth — только локальная отладка | ❌ |

## 📱 Использование

**Mini App (основной путь):** menu button «📝 Записать» в боте (или кнопка «⚡ Открыть Mini App» в `/quick`) → сетка активностей → тап по плитке → пресеты часов (0.5–3.5 шагом 0.5, дальше целыми до 15) + ✏️ custom + ✕ сброс. Переключатель Сегодня/Вчера/📅. В sticky-шапке — итог дня и индикатор записи в таблицу («⏳ пишу в таблицу…» → «✓ всё в таблице»).

**Команды бота:**

- `/start`, `/help` — приветствие и помощь
- `/quick` — ввод инлайн-кнопками (fallback)
- `/stats` — статистика по дням, аналитика 7 дней, топ-3
- `/list` — все увлечения
- `/reminders` — настройка напоминаний

## 📂 Структура проекта

```
hobby-tracker/
├── src/
│   ├── api/
│   │   ├── auth.py          # HMAC initData + allowlist
│   │   └── server.py        # FastAPI: /api/hobbies, /api/day, /api/entry, /api/queue, статика
│   ├── bot/
│   │   ├── handlers.py      # Обработчики команд и кнопок
│   │   ├── keyboards.py     # Инлайн клавиатуры
│   │   └── messages.py      # Тексты сообщений
│   ├── data/
│   │   ├── daycache.py      # Кэш последних 7 дней + оверлей журнала
│   │   ├── files.py         # История увлечений, алиасы
│   │   ├── journal.py       # Журнал-буфер записи (jsonl + offset)
│   │   ├── reminders.py     # Напоминания
│   │   ├── stars.py         # Значения пресетов бота
│   │   ├── sheets.py        # Google Sheets (+bulk-чтение)
│   │   └── sync_worker.py   # Фоновый слив журнала в Sheets
│   ├── utils/
│   │   ├── config.py        # Конфигурация (+validate_config)
│   │   ├── dates.py         # Даты, правило «до 6 утра»
│   │   └── scheduler.py     # Планировщик напоминаний
│   └── runtime.py           # Синглтоны + record_entry/get_day_values
├── frontend/
│   └── index.html           # Mini App (vanilla JS, без сборки)
├── tests/                   # pytest (журнал, воркер, кэш, auth, API)
├── data/                    # Данные (volume, не в git)
│   ├── journal.jsonl        # Журнал несинканных записей
│   ├── journal.offset       # Сколько строк уже в Sheets
│   ├── cache/days.json      # Кэш последних дней
│   ├── aliases.txt          # Алиасы с эмодзи
│   ├── hobbies_history.txt  # История увлечений (порядок плиток)
│   ├── reminders.txt        # Напоминания
│   └── stars.txt            # Пресеты бота
├── main.py                  # Точка входа: бот + API + воркер
├── docker-compose.yml       # Docker Compose (+caddy labels)
└── requirements.txt         # Зависимости
```

## 🔧 Настройка Google Sheets

1. Создайте новую Google таблицу
2. Скопируйте ID таблицы из URL (длинная строка между `/d/` и `/edit`)
3. Создайте Service Account в Google Cloud Console
4. Скачайте JSON ключ и поместите как `service_account.json`
5. Предоставьте доступ к таблице email'у из JSON ключа

Структура таблицы создается автоматически:
- Колонка A: Дата (YYYY-MM-DD)
- Остальные колонки: Увлечения (создаются динамически)

Повторная запись той же активности в тот же день перезаписывает значение.

## 📈 Дополнительные возможности

- **Алиасы**: `data/aliases.txt` (`ключ=🎮 Название`), управление через меню настроек бота
- **История**: `data/hobbies_history.txt` — задаёт порядок плиток (недавние сверху)
- **Пресеты бота**: настраиваются в `data/stars.txt` (Mini App использует свой фиксированный ряд)
- **Напоминания**: любое время, с полной статистикой дня
- **Редактирование на сервере**: файлы в `data/` доступны для прямого редактирования; правки в самой таблице подтянутся при рестарте (стартовая сверка кэша)

## 📄 Лицензия

MIT License
