# Mini App ввода + буферная запись в Sheets — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Telegram Mini App для быстрого ввода активностей (тап→пресеты) + журнал-буфер, развязывающий UI от Google Sheets; починка задержек существующего бота.

**Architecture:** Один asyncio-процесс: PTB-бот (polling, ручной lifecycle) + FastAPI/uvicorn (API + статика Mini App) + sync-воркер (журнал → Sheets, retry). Вся запись — через `data/journal.jsonl`; чтение — DayCache (7 дней) + оверлей журнала. Sheets остаётся первичной БД.

**Tech Stack:** Python 3.11, python-telegram-bot 21.4, FastAPI + uvicorn, gspread, vanilla JS Mini App (без сборки), pytest.

**Spec:** `docs/superpowers/specs/2026-07-06-mini-app-input-design.md` — читать перед работой.

## Global Constraints

- Python 3.11 (Docker `python:3.11-slim`); зависимости пиновать точно (`==`)
- Google Sheets — истина; журнал никогда не теряет записи; offset двигается только после успешной записи в Sheets
- Часы: 0–24, шаг 0.5; значение 0 валидно («не было»)
- Все вызовы gspread — через `asyncio.to_thread` под общим `asyncio.Lock` (gspread не thread-safe)
- Ключи хобби: нижний регистр, нормализация `norm_hobby` (strip/lower/ё→е); `:` в callback_data — разделитель, в ключах не допускается
- Коммиты: Conventional Commits, описание на русском формой «Добавлен X»
- Auth Mini App: HMAC initData (паттерн budget-bot) + allowlist `ALLOWED_USER_IDS`; `AUTH_DISABLED=1` — только для локальной отладки
- Тесты: pytest, без сети; gspread в тестах не трогаем (мокаем/инжектим)

## Карта файлов

| Файл | Роль |
|---|---|
| `src/utils/config.py` (mod) | +WEBAPP_URL, ALLOWED_USER_IDS, API_PORT, AUTH_DISABLED, пути журнала/кэша; валидация из import-time в `validate_config()` |
| `src/data/journal.py` (new) | Journal: append/pending/advance/compact |
| `src/data/daycache.py` (new) | DayCache: снапшот 7 дней + `merged()` оверлей |
| `src/data/sheets.py` (mod) | +`parse_days()`, `get_days_bulk()`, ленивый синглтон `get_sheets_manager()` |
| `src/data/sync_worker.py` (new) | SyncWorker + `compact_entries()` |
| `src/runtime.py` (new) | Синглтоны (journal, cache, lock, wake) + `record_entry()`, `get_day_values()` |
| `src/api/auth.py` (new) | verify_init_data + FastAPI dependency |
| `src/api/server.py` (new) | FastAPI: /api/hobbies, /api/day/{date}, /api/entry, статика |
| `frontend/index.html` (new) | Mini App (вариант B из прототипа) |
| `main.py` (mod) | asyncio main: PTB + uvicorn + worker + scheduler |
| `src/bot/handlers.py` (mod) | запись через runtime, без sleep, статистика через кэш, batch-аналитика |
| `src/bot/keyboards.py` (mod) | кнопка web_app |
| `src/utils/scheduler.py` (mod) | напоминания читают через runtime |
| `Dockerfile`, `docker-compose.yml`, `.env.example` (mod) | frontend, caddy labels, env |
| `tests/…` (new) | conftest + тесты journal/daycache/worker/auth/api |

---

### Task 1: Зависимости, конфиг, каркас тестов

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-dev.txt`
- Modify: `src/utils/config.py`
- Modify: `main.py:42-48` (вызов validate_config)
- Create: `tests/__init__.py`, `tests/conftest.py`

**Interfaces:**
- Produces: `config.validate_config()`, константы `WEBAPP_URL: str`, `ALLOWED_USER_IDS: list[int]`, `API_PORT: int`, `AUTH_DISABLED: bool`, `JOURNAL_FILE`, `JOURNAL_OFFSET_FILE`, `DAYCACHE_FILE`. Импорт `config` больше НЕ падает без .env — это разблокирует все тесты.

- [ ] **Step 1: requirements**

`requirements.txt` — добавить в конец:

```
fastapi==0.115.6
uvicorn==0.34.0
```

`requirements-dev.txt` (новый):

```
-r requirements.txt
pytest==8.3.4
pytest-asyncio==0.25.2
httpx==0.28.1
```

- [ ] **Step 2: конфиг**

В `src/utils/config.py` заменить блок валидации (строки 32–37) и добавить новые константы:

```python
# Mini App / API
WEBAPP_URL = os.getenv("WEBAPP_URL", "")
ALLOWED_USER_IDS = [int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()]
API_PORT = int(os.getenv("API_PORT", "8000"))
AUTH_DISABLED = os.getenv("AUTH_DISABLED") == "1"  # только локальная отладка

# Журнал и кэш
JOURNAL_FILE = "data/journal.jsonl"
JOURNAL_OFFSET_FILE = "data/journal.offset"
DAYCACHE_FILE = "data/cache/days.json"


def validate_config() -> None:
    """Вызывается из main() — НЕ при импорте, чтобы тесты жили без .env"""
    if not BOT_TOKEN or not SPREADSHEET_ID:
        raise SystemExit("Отсутствуют TELEGRAM_BOT_TOKEN или SPREADSHEET_ID в .env")
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise SystemExit(f"Нет файла {SERVICE_ACCOUNT_FILE} рядом с main.py")
```

Import-time `raise SystemExit` (старые строки 33–37) — удалить.

В `main.py` внутри `try` блока конфигурации (строка 43, перед `create_sample_aliases()`):

```python
from src.utils.config import validate_config
validate_config()
```

- [ ] **Step 3: conftest**

`tests/conftest.py`:

```python
import os

# До любых импортов src: фейковое окружение для тестов
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST-TOKEN")
os.environ.setdefault("SPREADSHEET_ID", "test-spreadsheet-id")
```

`tests/__init__.py` — пустой.

- [ ] **Step 4: проверить, что всё живо**

Run: `python -c "import sys; sys.path.insert(0,'.'); from src.utils.config import validate_config; print('ok')"` (без .env-переменных упасть не должно)
Expected: `ok`

Run: `pip install -r requirements-dev.txt && pytest tests/ -v`
Expected: `no tests ran` (пока пусто), без ошибок импорта

- [ ] **Step 5: Commit**

```bash
git add requirements.txt requirements-dev.txt src/utils/config.py main.py tests/
git commit -m "chore: добавлены зависимости API и вынесена валидация конфига из import-time"
```

---

### Task 2: Journal (WriteBuffer)

**Files:**
- Create: `src/data/journal.py`
- Test: `tests/test_journal.py`

**Interfaces:**
- Produces:
  - `Journal(journal_path: str, offset_path: str)`
  - `.append(date: str, hobby: str, hours: float, source: str) -> None`
  - `.pending() -> list[dict]` — записи после offset; ключи `ts,date,hobby,hours,source`; битые строки пропускаются
  - `.pending_count() -> int`
  - `.advance(n: int) -> None` — offset += n, персистентно
  - `.compact_if_synced() -> None` — если offset == всего строк, усечь оба файла в 0

- [ ] **Step 1: Failing tests**

`tests/test_journal.py`:

```python
import pytest
from src.data.journal import Journal


@pytest.fixture
def j(tmp_path):
    return Journal(str(tmp_path / "journal.jsonl"), str(tmp_path / "journal.offset"))


def test_append_and_pending(j):
    j.append("2026-07-06", "игры", 2.0, "miniapp")
    j.append("2026-07-06", "мото", 1.5, "bot")
    p = j.pending()
    assert len(p) == 2
    assert p[0]["hobby"] == "игры" and p[0]["hours"] == 2.0
    assert p[1]["source"] == "bot"
    assert "ts" in p[0] and p[0]["date"] == "2026-07-06"


def test_advance_offset(j):
    j.append("2026-07-06", "игры", 2.0, "bot")
    j.append("2026-07-06", "мото", 1.0, "bot")
    j.advance(1)
    assert [e["hobby"] for e in j.pending()] == ["мото"]
    assert j.pending_count() == 1


def test_state_survives_restart(j, tmp_path):
    j.append("2026-07-06", "игры", 2.0, "bot")
    j.advance(1)
    j.append("2026-07-06", "мото", 1.0, "bot")
    j2 = Journal(str(tmp_path / "journal.jsonl"), str(tmp_path / "journal.offset"))
    assert [e["hobby"] for e in j2.pending()] == ["мото"]


def test_broken_line_skipped(j, tmp_path):
    j.append("2026-07-06", "игры", 2.0, "bot")
    with open(tmp_path / "journal.jsonl", "a", encoding="utf-8") as f:
        f.write('{"обрыв на пол')  # недописанная при падении строка
    j.append("2026-07-06", "мото", 1.0, "bot")
    hobbies = [e["hobby"] for e in j.pending()]
    assert hobbies == ["игры", "мото"]


def test_compact_if_synced(j, tmp_path):
    j.append("2026-07-06", "игры", 2.0, "bot")
    j.compact_if_synced()          # не всё слито — не трогает
    assert j.pending_count() == 1
    j.advance(1)
    j.compact_if_synced()          # всё слито — усекает
    assert (tmp_path / "journal.jsonl").read_text() == ""
    assert j.pending() == [] and j.pending_count() == 0


def test_missing_files_ok(tmp_path):
    j = Journal(str(tmp_path / "nope.jsonl"), str(tmp_path / "nope.offset"))
    assert j.pending() == [] and j.pending_count() == 0
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_journal.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'src.data.journal'`

- [ ] **Step 3: Implementation**

`src/data/journal.py`:

```python
"""Журнал-буфер записи: append-only jsonl + offset слитых в Sheets строк."""

import json
import logging
import os
from datetime import datetime

from ..utils.dates import get_tz

logger = logging.getLogger(__name__)


class Journal:
    def __init__(self, journal_path: str, offset_path: str):
        self.journal_path = journal_path
        self.offset_path = offset_path

    def append(self, date: str, hobby: str, hours: float, source: str) -> None:
        entry = {
            "ts": datetime.now(tz=get_tz()).isoformat(),
            "date": date,
            "hobby": hobby,
            "hours": hours,
            "source": source,
        }
        os.makedirs(os.path.dirname(self.journal_path) or ".", exist_ok=True)
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _read_offset(self) -> int:
        try:
            with open(self.offset_path, "r", encoding="utf-8") as f:
                return int(f.read().strip() or 0)
        except (FileNotFoundError, ValueError):
            return 0

    def _write_offset(self, value: int) -> None:
        os.makedirs(os.path.dirname(self.offset_path) or ".", exist_ok=True)
        with open(self.offset_path, "w", encoding="utf-8") as f:
            f.write(str(value))
            f.flush()
            os.fsync(f.fileno())

    def _read_lines(self) -> list[str]:
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                return [ln for ln in f.read().splitlines() if ln.strip()]
        except FileNotFoundError:
            return []

    def pending(self) -> list[dict]:
        entries = []
        for line in self._read_lines()[self._read_offset():]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Пропущена битая строка журнала: %r", line[:80])
        return entries

    def pending_count(self) -> int:
        return len(self.pending())

    def advance(self, n: int) -> None:
        self._write_offset(self._read_offset() + n)

    def compact_if_synced(self) -> None:
        lines = self._read_lines()
        if lines and self._read_offset() >= len(lines):
            with open(self.journal_path, "w", encoding="utf-8") as f:
                f.truncate(0)
            self._write_offset(0)
```

Внимание на `test_broken_line_skipped`: битая строка **считается** в offset-арифметике (`_read_lines` вернёт её, `json.loads` упадёт → skip, но advance двигается на число обработанных записей `pending()`). Чтобы арифметика не разъехалась: воркер вызывает `advance(len(raw_после_offset))` — см. Task 4, где `SyncWorker` берёт `raw_count`. Для этого добавить метод:

```python
    def pending_with_raw_count(self) -> tuple[list[dict], int]:
        raw = self._read_lines()[self._read_offset():]
        entries = []
        for line in raw:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Пропущена битая строка журнала: %r", line[:80])
        return entries, len(raw)
```

И тест к нему (добавить в `tests/test_journal.py`):

```python
def test_pending_with_raw_count(j, tmp_path):
    j.append("2026-07-06", "игры", 2.0, "bot")
    with open(tmp_path / "journal.jsonl", "a", encoding="utf-8") as f:
        f.write('{"обрыв\n')
    entries, raw = j.pending_with_raw_count()
    assert len(entries) == 1 and raw == 2
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_journal.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/data/journal.py tests/test_journal.py
git commit -m "feat: добавлен журнал-буфер записи (jsonl + offset)"
```

---

### Task 3: Sheets — bulk-чтение и ленивый синглтон

**Files:**
- Modify: `src/data/sheets.py`
- Test: `tests/test_sheets_parse.py`

**Interfaces:**
- Consumes: существующий `SheetsManager`
- Produces:
  - `parse_days(all_values: list[list[str]], dates: list[str]) -> dict[str, dict[str, float]]` — pure, без сети; только значения > 0… нет: включает и 0 как записанный 0.0? **Нет** — включает все непустые ячейки как float (0 в ячейке → 0.0 в результате); пустые ячейки не включаются
  - `SheetsManager.get_days_bulk(dates: list[str]) -> dict[str, dict[str, float]]` — ОДИН запрос `get_all_values()`
  - `get_sheets_manager() -> SheetsManager` — ленивый синглтон (модульный)

- [ ] **Step 1: Failing tests**

`tests/test_sheets_parse.py`:

```python
from src.data.sheets import parse_days

ALL_VALUES = [
    ["Дата", "игры", "мото", "спортзал"],
    ["2026-07-04", "2", "", "1,5"],
    ["2026-07-05", "0", "3.5", ""],
    ["2026-07-06", "", "", ""],
]


def test_parse_days_basic():
    out = parse_days(ALL_VALUES, ["2026-07-04", "2026-07-05"])
    assert out["2026-07-04"] == {"игры": 2.0, "спортзал": 1.5}
    assert out["2026-07-05"] == {"игры": 0.0, "мото": 3.5}


def test_parse_days_missing_date_is_empty():
    out = parse_days(ALL_VALUES, ["2026-07-06", "2026-01-01"])
    assert out["2026-07-06"] == {}
    assert out["2026-01-01"] == {}


def test_parse_days_bad_cell_ignored():
    vals = [["Дата", "игры"], ["2026-07-04", "абв"]]
    assert parse_days(vals, ["2026-07-04"]) == {"2026-07-04": {}}


def test_parse_days_empty_sheet():
    assert parse_days([], ["2026-07-04"]) == {"2026-07-04": {}}
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_sheets_parse.py -v`
Expected: FAIL, `ImportError: cannot import name 'parse_days'`

- [ ] **Step 3: Implementation**

В `src/data/sheets.py` добавить (после импортов, до класса):

```python
def parse_days(all_values: list[list[str]], dates: list[str]) -> dict[str, dict[str, float]]:
    """Разбирает результат get_all_values() в {дата: {хобби: часы}}. Pure, без сети."""
    result: dict[str, dict[str, float]] = {d: {} for d in dates}
    if not all_values:
        return result
    headers = all_values[0]
    wanted = set(dates)
    for row in all_values[1:]:
        if not row or row[0] not in wanted:
            continue
        day: dict[str, float] = {}
        for j, header in enumerate(headers[1:], start=1):
            if j < len(row) and row[j].strip():
                try:
                    day[header] = float(row[j].replace(",", "."))
                except ValueError:
                    continue
        result[row[0]] = day
    return result
```

В класс `SheetsManager` добавить метод:

```python
    def get_days_bulk(self, dates: list[str]) -> dict[str, dict[str, float]]:
        """Данные за несколько дат ОДНИМ запросом к API"""
        try:
            all_values = self.ws.get_all_values()
        except Exception:
            return {d: {} for d in dates}
        return parse_days(all_values, dates)
```

В конец файла — ленивый синглтон:

```python
_manager: "SheetsManager | None" = None


def get_sheets_manager() -> "SheetsManager":
    global _manager
    if _manager is None:
        _manager = SheetsManager()
    return _manager
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_sheets_parse.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/data/sheets.py tests/test_sheets_parse.py
git commit -m "feat: добавлено bulk-чтение дней из Sheets одним запросом"
```

---

### Task 4: DayCache + оверлей журнала

**Files:**
- Create: `src/data/daycache.py`
- Test: `tests/test_daycache.py`

**Interfaces:**
- Consumes: формат записей журнала из Task 2 (`{date, hobby, hours, ...}`)
- Produces:
  - `DayCache(path: str, days_window: int = 7)`
  - `.get(date: str) -> dict[str, float] | None` — None = cache miss
  - `.set(date: str, values: dict[str, float]) -> None` — персистит; даты вне окна не сохраняет
  - `.apply_entry(date: str, hobby: str, hours: float) -> None` — точечное обновление (только если дата уже в кэше или в окне)
  - `.prune(today: str) -> None` — выкинуть даты старше окна
  - `merged(base: dict[str, float], pending: list[dict], date: str) -> dict[str, float]` — модульная pure-функция: оверлей несинканных записей журнала поверх базы (по порядку, последняя побеждает)

- [ ] **Step 1: Failing tests**

`tests/test_daycache.py`:

```python
import pytest
from src.data.daycache import DayCache, merged


@pytest.fixture
def c(tmp_path):
    return DayCache(str(tmp_path / "days.json"), days_window=7)


def test_set_get_roundtrip_persists(c, tmp_path):
    c.set("2026-07-06", {"игры": 2.0})
    assert c.get("2026-07-06") == {"игры": 2.0}
    c2 = DayCache(str(tmp_path / "days.json"), days_window=7)
    assert c2.get("2026-07-06") == {"игры": 2.0}


def test_get_miss_returns_none(c):
    assert c.get("2026-01-01") is None


def test_apply_entry_updates_existing_day(c):
    c.set("2026-07-06", {"игры": 2.0})
    c.apply_entry("2026-07-06", "мото", 1.5)
    c.apply_entry("2026-07-06", "игры", 3.0)
    assert c.get("2026-07-06") == {"игры": 3.0, "мото": 1.5}


def test_apply_entry_creates_day(c):
    c.apply_entry("2026-07-06", "игры", 1.0)
    assert c.get("2026-07-06") == {"игры": 1.0}


def test_prune_drops_old_dates(c):
    c.set("2026-07-06", {"игры": 1.0})
    c.set("2026-06-01", {"мото": 1.0})
    c.prune(today="2026-07-06")
    assert c.get("2026-06-01") is None
    assert c.get("2026-07-06") is not None


def test_merged_overlay_order_and_date_filter():
    base = {"игры": 1.0, "мото": 2.0}
    pending = [
        {"date": "2026-07-06", "hobby": "игры", "hours": 2.0},
        {"date": "2026-07-05", "hobby": "мото", "hours": 9.0},   # другая дата — мимо
        {"date": "2026-07-06", "hobby": "игры", "hours": 3.5},   # последняя побеждает
        {"date": "2026-07-06", "hobby": "чтение", "hours": 0.5},
    ]
    out = merged(base, pending, "2026-07-06")
    assert out == {"игры": 3.5, "мото": 2.0, "чтение": 0.5}
    assert base == {"игры": 1.0, "мото": 2.0}  # не мутирует базу
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_daycache.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implementation**

`src/data/daycache.py`:

```python
"""Локальный снапшот значений последних N дней + оверлей журнала."""

import datetime as dt
import json
import os


def merged(base: dict[str, float], pending: list[dict], date: str) -> dict[str, float]:
    """Оверлей несинканных записей журнала поверх базы (последняя запись побеждает)."""
    out = dict(base)
    for e in pending:
        if e.get("date") == date:
            out[e["hobby"]] = e["hours"]
    return out


class DayCache:
    def __init__(self, path: str, days_window: int = 7):
        self.path = path
        self.days_window = days_window
        self._data: dict[str, dict[str, float]] = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)

    def get(self, date: str) -> dict[str, float] | None:
        values = self._data.get(date)
        return dict(values) if values is not None else None

    def set(self, date: str, values: dict[str, float]) -> None:
        self._data[date] = dict(values)
        self._save()

    def apply_entry(self, date: str, hobby: str, hours: float) -> None:
        self._data.setdefault(date, {})[hobby] = hours
        self._save()

    def prune(self, today: str) -> None:
        cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=self.days_window)).isoformat()
        stale = [d for d in self._data if d < cutoff]
        for d in stale:
            del self._data[d]
        if stale:
            self._save()
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_daycache.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/data/daycache.py tests/test_daycache.py
git commit -m "feat: добавлен кэш дней с оверлеем журнала"
```

---

### Task 5: SyncWorker (журнал → Sheets)

**Files:**
- Create: `src/data/sync_worker.py`
- Test: `tests/test_sync_worker.py`

**Interfaces:**
- Consumes: `Journal.pending_with_raw_count()`, `.advance()`, `.compact_if_synced()` (Task 2)
- Produces:
  - `compact_entries(entries: list[dict]) -> dict[str, dict[str, float]]` — pure: группировка по дате, последнее значение на (date, hobby) побеждает
  - `SyncWorker(journal, wake: asyncio.Event, write_day, sheets_lock: asyncio.Lock)` — `write_day(values: dict, date: str)` — sync-callable (в проде `get_sheets_manager().write_values`), зовётся через `asyncio.to_thread`
  - `.run() -> None` — вечный цикл: ждать wake/таймаут 60с → `drain()`
  - `.drain() -> bool` — True = журнал пуст/слит; False = ошибка (retry снаружи, offset НЕ двигался)

- [ ] **Step 1: Failing tests**

`tests/test_sync_worker.py`:

```python
import asyncio

import pytest

from src.data.journal import Journal
from src.data.sync_worker import SyncWorker, compact_entries


def test_compact_entries_last_wins_groups_by_date():
    entries = [
        {"date": "2026-07-06", "hobby": "игры", "hours": 1.0},
        {"date": "2026-07-05", "hobby": "мото", "hours": 2.0},
        {"date": "2026-07-06", "hobby": "игры", "hours": 3.0},
        {"date": "2026-07-06", "hobby": "чтение", "hours": 0.5},
    ]
    assert compact_entries(entries) == {
        "2026-07-06": {"игры": 3.0, "чтение": 0.5},
        "2026-07-05": {"мото": 2.0},
    }


@pytest.fixture
def j(tmp_path):
    return Journal(str(tmp_path / "j.jsonl"), str(tmp_path / "j.offset"))


def make_worker(j, write_day):
    return SyncWorker(j, asyncio.Event(), write_day, asyncio.Lock())


def test_drain_writes_and_advances(j):
    written = []
    j.append("2026-07-06", "игры", 2.0, "bot")
    j.append("2026-07-06", "игры", 3.0, "miniapp")
    w = make_worker(j, lambda values, date: written.append((date, values)))
    ok = asyncio.run(w.drain())
    assert ok is True
    assert written == [("2026-07-06", {"игры": 3.0})]  # compaction
    assert j.pending() == []


def test_drain_failure_keeps_offset(j):
    def boom(values, date):
        raise RuntimeError("sheets down")

    j.append("2026-07-06", "игры", 2.0, "bot")
    w = make_worker(j, boom)
    ok = asyncio.run(w.drain())
    assert ok is False
    assert j.pending_count() == 1  # ничего не потеряно


def test_drain_empty_journal_ok(j):
    w = make_worker(j, lambda values, date: None)
    assert asyncio.run(w.drain()) is True
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_sync_worker.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implementation**

`src/data/sync_worker.py`:

```python
"""Фоновый слив журнала в Google Sheets: батч, retry с backoff, offset после успеха."""

import asyncio
import logging

logger = logging.getLogger(__name__)

MAX_BACKOFF = 60


def compact_entries(entries: list[dict]) -> dict[str, dict[str, float]]:
    """{дата: {хобби: часы}}, последняя запись на пару (date, hobby) побеждает"""
    batch: dict[str, dict[str, float]] = {}
    for e in entries:
        batch.setdefault(e["date"], {})[e["hobby"]] = e["hours"]
    return batch


class SyncWorker:
    def __init__(self, journal, wake: asyncio.Event, write_day, sheets_lock: asyncio.Lock):
        self.journal = journal
        self.wake = wake
        self.write_day = write_day          # sync callable: (values: dict, date: str)
        self.sheets_lock = sheets_lock
        self._backoff = 1

    async def drain(self) -> bool:
        entries, raw_count = self.journal.pending_with_raw_count()
        if raw_count == 0:
            self.journal.compact_if_synced()
            return True
        try:
            for date, values in compact_entries(entries).items():
                async with self.sheets_lock:
                    await asyncio.to_thread(self.write_day, values, date)
        except Exception as e:
            logger.error("Синк в Sheets не удался (retry через %sс): %s", self._backoff, e)
            return False
        self.journal.advance(raw_count)
        self.journal.compact_if_synced()
        logger.info("Синк: %d записей слито в Sheets", len(entries))
        return True

    async def run(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass
            self.wake.clear()
            if await self.drain():
                self._backoff = 1
            else:
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, MAX_BACKOFF)
                self.wake.set()  # немедленный повтор после паузы
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_sync_worker.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/data/sync_worker.py tests/test_sync_worker.py
git commit -m "feat: добавлен sync-воркер журнала с retry и компактацией батча"
```

---

### Task 6: Runtime — сборка синглтонов и сервисные функции

**Files:**
- Create: `src/runtime.py`
- Test: `tests/test_runtime.py`

**Interfaces:**
- Consumes: Journal (T2), DayCache/merged (T4), get_sheets_manager (T3), `save_hobby_to_history` из `src/data/files.py`, `date_for_time` из `src/utils/dates.py`
- Produces (импортируют handlers, server, scheduler, main):
  - `init_runtime() -> None` — создаёт `journal`, `cache`, `wake`, `sheets_lock` (модульные переменные)
  - `record_entry(date: str, hobby: str, hours: float, source: str) -> int` — журнал + кэш + история + wake; возвращает `pending_count`
  - `async get_day_values(date: str) -> dict[str, float]` — кэш → (miss: Sheets через to_thread под lock, в кэш если в окне) → оверлей журнала
  - `pending_count() -> int`

- [ ] **Step 1: Failing tests**

`tests/test_runtime.py`:

```python
import asyncio

import pytest

import src.runtime as runtime


@pytest.fixture
def rt(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "JOURNAL_FILE", str(tmp_path / "j.jsonl"))
    monkeypatch.setattr(runtime, "JOURNAL_OFFSET_FILE", str(tmp_path / "j.offset"))
    monkeypatch.setattr(runtime, "DAYCACHE_FILE", str(tmp_path / "days.json"))
    monkeypatch.setattr(runtime, "save_hobby_to_history", lambda h: None)
    runtime.init_runtime()
    return runtime


def test_record_entry_journal_and_cache(rt):
    n = rt.record_entry("2026-07-06", "игры", 2.0, "miniapp")
    assert n == 1
    assert rt.journal.pending()[0]["hobby"] == "игры"
    assert rt.cache.get("2026-07-06") == {"игры": 2.0}
    assert rt.wake.is_set()


def test_get_day_values_from_cache_with_overlay(rt):
    rt.cache.set("2026-07-06", {"мото": 1.0})
    rt.record_entry("2026-07-06", "игры", 2.0, "bot")
    out = asyncio.run(rt.get_day_values("2026-07-06"))
    assert out == {"мото": 1.0, "игры": 2.0}


def test_get_day_values_miss_fetches_sheets(rt, monkeypatch):
    calls = []

    class FakeSheets:
        def get_day_data(self, date):
            calls.append(date)
            return {"чтение": 0.5}

    monkeypatch.setattr(rt, "get_sheets_manager", lambda: FakeSheets())
    out = asyncio.run(rt.get_day_values("2026-07-01"))
    assert out == {"чтение": 0.5}
    assert calls == ["2026-07-01"]
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_runtime.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implementation**

`src/runtime.py`:

```python
"""Синглтоны процесса (журнал, кэш, локи) и сервисные операции записи/чтения.

Единственный путь записи для бота И Mini App — record_entry().
"""

import asyncio
import datetime as dt

from .data.daycache import DayCache, merged
from .data.files import save_hobby_to_history
from .data.journal import Journal
from .data.sheets import get_sheets_manager
from .utils.config import DAYCACHE_FILE, JOURNAL_FILE, JOURNAL_OFFSET_FILE
from .utils.dates import date_for_time

journal: Journal
cache: DayCache
wake: asyncio.Event
sheets_lock: asyncio.Lock


def init_runtime() -> None:
    global journal, cache, wake, sheets_lock
    journal = Journal(JOURNAL_FILE, JOURNAL_OFFSET_FILE)
    cache = DayCache(DAYCACHE_FILE, days_window=7)
    wake = asyncio.Event()
    sheets_lock = asyncio.Lock()


def _in_window(date: str, window: int = 7) -> bool:
    today = dt.date.fromisoformat(date_for_time())
    return (today - dt.date.fromisoformat(date)).days <= window


def record_entry(date: str, hobby: str, hours: float, source: str) -> int:
    journal.append(date, hobby, hours, source)
    if _in_window(date):
        cache.apply_entry(date, hobby, hours)
    save_hobby_to_history(hobby)
    wake.set()
    return journal.pending_count()


def pending_count() -> int:
    return journal.pending_count()


async def get_day_values(date: str) -> dict[str, float]:
    base = cache.get(date)
    if base is None:
        async with sheets_lock:
            base = await asyncio.to_thread(lambda: get_sheets_manager().get_day_data(date))
        if _in_window(date):
            cache.set(date, base)
    return merged(base, journal.pending(), date)
```

Примечание: тест патчит `runtime.JOURNAL_FILE` — значит `init_runtime()` должен брать модульные переменные, а не замыкать импортированные константы. Так и написано (импорт кладёт их в модульное пространство `runtime`).

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_runtime.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/runtime.py tests/test_runtime.py
git commit -m "feat: добавлен runtime-слой с единым путём записи record_entry"
```

---

### Task 7: Auth (Telegram initData)

**Files:**
- Create: `src/api/__init__.py` (пустой), `src/api/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `config.BOT_TOKEN`, `config.ALLOWED_USER_IDS`, `config.AUTH_DISABLED`
- Produces:
  - `verify_init_data(init_data: str, bot_token: str) -> dict | None` — pure; dict распарсенных полей или None
  - `async require_tg_auth(request: Request) -> dict` — FastAPI dependency; 401 нет заголовка `Telegram-Init-Data`, 403 невалидная подпись/чужой user_id

- [ ] **Step 1: Failing tests**

`tests/test_auth.py`:

```python
import hashlib
import hmac
import json
from urllib.parse import urlencode

from src.api.auth import verify_init_data

TOKEN = "123456:TEST-TOKEN"


def make_init_data(user_id: int, token: str = TOKEN, tamper: bool = False) -> str:
    params = {
        "auth_date": "1700000000",
        "user": json.dumps({"id": user_id, "first_name": "Max"}),
    }
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    if tamper:
        params["user"] = json.dumps({"id": 999, "first_name": "Evil"})
    return urlencode({**params, "hash": h})


def test_valid_signature():
    parsed = verify_init_data(make_init_data(42), TOKEN)
    assert parsed is not None
    assert json.loads(parsed["user"])["id"] == 42


def test_tampered_payload_rejected():
    assert verify_init_data(make_init_data(42, tamper=True), TOKEN) is None


def test_wrong_token_rejected():
    assert verify_init_data(make_init_data(42, token="999:OTHER"), TOKEN) is None


def test_garbage_rejected():
    assert verify_init_data("hash=zzz", TOKEN) is None
    assert verify_init_data("", TOKEN) is None
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implementation**

`src/api/auth.py` (паттерн budget-bot, проверен на этой же инфре):

```python
"""Аутентификация Telegram Mini App: HMAC-валидация initData + allowlist."""

import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request

from ..utils.config import ALLOWED_USER_IDS, AUTH_DISABLED, BOT_TOKEN


def verify_init_data(init_data: str, bot_token: str) -> dict | None:
    """HMAC-SHA256 проверка подписи initData. None = невалидно."""
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=False))
    except ValueError:
        return None
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None
    return parsed


async def require_tg_auth(request: Request) -> dict:
    """FastAPI dependency: валидирует заголовок Telegram-Init-Data."""
    if AUTH_DISABLED:
        return {"user": json.dumps({"id": 0, "dev": True})}
    init_data = request.headers.get("Telegram-Init-Data", "")
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing Telegram-Init-Data header")
    parsed = verify_init_data(init_data, BOT_TOKEN)
    if parsed is None:
        raise HTTPException(status_code=403, detail="Invalid Telegram initData")
    if ALLOWED_USER_IDS:
        try:
            user_id = json.loads(parsed.get("user", "{}")).get("id")
        except json.JSONDecodeError:
            user_id = None
        if user_id not in ALLOWED_USER_IDS:
            raise HTTPException(status_code=403, detail="User not allowed")
    return parsed
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_auth.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/api/__init__.py src/api/auth.py tests/test_auth.py
git commit -m "feat: добавлена auth Mini App по подписи initData"
```

---

### Task 8: API-сервер (FastAPI)

**Files:**
- Create: `src/api/server.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `runtime` (T6), `require_tg_auth` (T7), `get_all_hobbies`/`get_hobby_display_name` из `src/data/files.py`, `date_for_time`
- Produces:
  - `create_app(serve_static: bool = True) -> FastAPI`
  - `GET /api/hobbies` → `{"hobbies": [{"key": str, "display": str}], "default_date": "YYYY-MM-DD", "queue_pending": int}`
  - `GET /api/day/{date}` → `{"values": {hobby: hours}, "queue_pending": int}` (400 на кривую дату)
  - `POST /api/entry` `{"date", "hobby", "hours"}` → `{"ok": true, "queue_pending": int}` (422/400 на кривые данные)
  - Статика `frontend/` на `/` (mount последним, чтобы не перекрыть /api)

- [ ] **Step 1: Failing tests**

`tests/test_api.py`:

```python
import asyncio

import pytest
from fastapi.testclient import TestClient

import src.runtime as runtime
from src.api.server import create_app
from tests.test_auth import make_init_data

AUTH = {"Telegram-Init-Data": make_init_data(42)}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "JOURNAL_FILE", str(tmp_path / "j.jsonl"))
    monkeypatch.setattr(runtime, "JOURNAL_OFFSET_FILE", str(tmp_path / "j.offset"))
    monkeypatch.setattr(runtime, "DAYCACHE_FILE", str(tmp_path / "days.json"))
    monkeypatch.setattr(runtime, "save_hobby_to_history", lambda h: None)
    runtime.init_runtime()
    runtime.cache.set("2026-07-06", {"мото": 1.0})

    import src.api.server as server
    monkeypatch.setattr(server, "get_all_hobbies", lambda: ["игры", "мото"])
    monkeypatch.setattr(server, "get_hobby_display_name", lambda h: f"🎮 {h}")
    monkeypatch.setattr("src.api.auth.ALLOWED_USER_IDS", [42])
    return TestClient(create_app(serve_static=False))


def test_hobbies(client):
    r = client.get("/api/hobbies", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["hobbies"][0] == {"key": "игры", "display": "🎮 игры"}
    assert "default_date" in body and body["queue_pending"] == 0


def test_day_returns_cache_plus_overlay(client):
    client.post("/api/entry", headers=AUTH,
                json={"date": "2026-07-06", "hobby": "игры", "hours": 2.5})
    r = client.get("/api/day/2026-07-06", headers=AUTH)
    assert r.json() == {"values": {"мото": 1.0, "игры": 2.5}, "queue_pending": 1}


def test_entry_validation(client):
    bad = [
        {"date": "2026-07-06", "hobby": "игры", "hours": 25},     # > 24
        {"date": "2026-07-06", "hobby": "игры", "hours": -1},     # < 0
        {"date": "06.07.2026", "hobby": "игры", "hours": 1},      # кривая дата
        {"date": "2026-07-06", "hobby": "", "hours": 1},          # пустое хобби
        {"date": "2026-07-06", "hobby": "а:б", "hours": 1},       # двоеточие
    ]
    for payload in bad:
        r = client.post("/api/entry", headers=AUTH, json=payload)
        assert r.status_code in (400, 422), payload


def test_no_auth_401(client):
    assert client.get("/api/hobbies").status_code == 401


def test_wrong_user_403(client):
    r = client.get("/api/hobbies", headers={"Telegram-Init-Data": make_init_data(777)})
    assert r.status_code == 403
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_api.py -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implementation**

`src/api/server.py`:

```python
"""HTTP API Mini App + раздача статики фронта."""

import datetime as dt
import re

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .. import runtime
from ..data.files import get_all_hobbies, get_hobby_display_name, norm_hobby
from ..utils.dates import date_for_time
from .auth import require_tg_auth

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class EntryRequest(BaseModel):
    date: str
    hobby: str = Field(min_length=1, max_length=64)
    hours: float = Field(ge=0, le=24)

    @field_validator("date")
    @classmethod
    def _date_iso(cls, v: str) -> str:
        if not DATE_RE.match(v):
            raise ValueError("date must be YYYY-MM-DD")
        dt.date.fromisoformat(v)  # ValueError на несуществующую дату
        return v

    @field_validator("hobby")
    @classmethod
    def _hobby_clean(cls, v: str) -> str:
        v = norm_hobby(v)
        if not v or ":" in v:
            raise ValueError("bad hobby key")
        return v


def create_app(serve_static: bool = True) -> FastAPI:
    app = FastAPI(title="Hobby Tracker API")

    @app.get("/api/hobbies")
    async def hobbies(_: dict = Depends(require_tg_auth)):
        return {
            "hobbies": [{"key": h, "display": get_hobby_display_name(h)}
                        for h in get_all_hobbies()],
            "default_date": date_for_time(),
            "queue_pending": runtime.pending_count(),
        }

    @app.get("/api/day/{date}")
    async def day(date: str, _: dict = Depends(require_tg_auth)):
        if not DATE_RE.match(date):
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        values = await runtime.get_day_values(date)
        return {"values": values, "queue_pending": runtime.pending_count()}

    @app.post("/api/entry")
    async def entry(req: EntryRequest, _: dict = Depends(require_tg_auth)):
        pending = runtime.record_entry(req.date, req.hobby, req.hours, source="miniapp")
        return {"ok": True, "queue_pending": pending}

    if serve_static:
        app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
    return app
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_api.py -v`
Expected: 5 passed. Также прогнать весь набор: `pytest tests/ -v` — всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add src/api/server.py tests/test_api.py
git commit -m "feat: добавлен HTTP API Mini App (hobbies, day, entry)"
```

---

### Task 9: Фронт Mini App

**Files:**
- Create: `frontend/index.html`

**Interfaces:**
- Consumes: API из Task 8 (контракты выше), `telegram-web-app.js`
- Produces: статический Mini App, который caddy/uvicorn отдаёт на `/`

- [ ] **Step 1: Файл целиком**

`frontend/index.html` (механика — победивший вариант B из `prototype/input-ux.html`, пресеты 0.5–3.5 шагом 0.5 и далее целыми до 15):

```html
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>Hobby Tracker</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: var(--tg-theme-bg-color, #17212b);
    --card: var(--tg-theme-secondary-bg-color, #232e3c);
    --card-filled: #2b5278;
    --text: var(--tg-theme-text-color, #f5f5f5);
    --muted: var(--tg-theme-hint-color, #708499);
    --accent: var(--tg-theme-button-color, #5eb5f7);
    --accent-text: var(--tg-theme-button-text-color, #08131d);
    --chip: #3a4a5c;
    --danger: #e26a6a;
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font-family: -apple-system, Roboto, "Segoe UI", sans-serif; }
  header { padding: 12px 14px 8px; display: flex; align-items: center;
           justify-content: space-between; position: sticky; top: 0;
           background: var(--bg); z-index: 5; }
  header h1 { font-size: 16px; margin: 0; font-weight: 600; }
  .date-switch { display: flex; gap: 6px; }
  .date-switch button { background: var(--chip); border: none; color: var(--muted);
    border-radius: 14px; padding: 5px 10px; font-size: 13px; cursor: pointer; }
  .date-switch button.active { background: var(--accent); color: var(--accent-text); font-weight: 600; }
  #datepick { position: absolute; opacity: 0; width: 1px; height: 1px; }
  main { padding: 8px 10px 90px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .tile { background: var(--card); border-radius: 12px; padding: 10px;
          display: flex; flex-direction: column; gap: 6px; cursor: pointer;
          border: 1px solid transparent; user-select: none; }
  .tile.filled { background: var(--card-filled); border-color: #3d6d99; }
  .tile.error { border-color: var(--danger); }
  .tile .name { font-size: 13.5px; line-height: 1.25; }
  .tile .val { font-size: 13px; color: var(--accent); font-weight: 700; min-height: 16px; }
  .tile .val.empty { color: var(--muted); font-weight: 400; }
  .presets { grid-column: 1 / -1; background: rgba(0,0,0,.25); border-radius: 12px;
             padding: 10px; display: flex; flex-wrap: wrap; gap: 6px; }
  .presets .title { width: 100%; font-size: 13px; color: var(--muted); }
  .presets button { border: none; border-radius: 9px; background: var(--chip);
    color: var(--text); padding: 9px 0; font-size: 14.5px; font-weight: 600;
    cursor: pointer; flex: 1 0 calc(20% - 6px); min-width: 52px; }
  .presets button:active { background: var(--accent); color: var(--accent-text); }
  .presets button.clear { background: #46323a; color: var(--danger); }
  footer { position: fixed; bottom: 0; left: 0; right: 0; background: var(--card);
           padding: 10px 14px calc(10px + env(safe-area-inset-bottom));
           display: flex; align-items: center; justify-content: space-between; z-index: 5; }
  footer .total b { color: var(--accent); }
  footer .queue { font-size: 12.5px; color: var(--muted); }
  footer .queue.busy { color: #e2b93b; }
  .toast { position: fixed; top: 12px; left: 50%; transform: translateX(-50%);
           background: var(--danger); color: #fff; padding: 8px 16px; border-radius: 10px;
           font-size: 13.5px; z-index: 20; opacity: 0; transition: opacity .2s; pointer-events: none; }
  .toast.show { opacity: 1; }
</style>
</head>
<body>
<header>
  <h1 id="title">…</h1>
  <div class="date-switch">
    <button id="btn-today">Сегодня</button>
    <button id="btn-yest">Вчера</button>
    <button id="btn-cal">📅</button>
    <input type="date" id="datepick">
  </div>
</header>
<main><div class="grid" id="grid"></div></main>
<footer>
  <div class="total" id="total"></div>
  <div class="queue" id="queue"></div>
</footer>
<div class="toast" id="toast"></div>

<script>
const tg = window.Telegram.WebApp;
tg.ready(); tg.expand();

// 0.5–3.5 шагом 0.5, дальше по часу до 15 (вердикт прототипа)
const PRESETS = [0.5,1,1.5,2,2.5,3,3.5,4,5,6,7,8,9,10,11,12,13,14,15];

let hobbies = [];        // [{key, display}]
let values = {};         // {key: hours} текущего дня (>0 = заполнено)
let date = null;         // выбранная дата YYYY-MM-DD
let defaultDate = null;  // «сегодня» с учётом правила 6 утра (с бэка)
let expanded = null;
let queuePending = 0;

async function api(path, opts = {}) {
  const r = await fetch(path, { ...opts, headers: {
    "Telegram-Init-Data": tg.initData,
    "Content-Type": "application/json", ...(opts.headers || {}) } });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

const fmt = v => String(v);
const addDays = (iso, n) => {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
};

async function loadDay(newDate) {
  date = newDate;
  const resp = await api(`/api/day/${date}`);
  values = {};
  for (const [k, v] of Object.entries(resp.values)) if (v > 0) values[k] = v;
  queuePending = resp.queue_pending;
  expanded = null;
  render();
}

async function pick(key, v) {
  expanded = null;
  const prev = values[key];
  if (v > 0) values[key] = v; else delete values[key];
  render();  // optimistic
  try {
    const resp = await api("/api/entry", { method: "POST",
      body: JSON.stringify({ date, hobby: key, hours: v }) });
    queuePending = resp.queue_pending;
  } catch (e) {
    if (prev != null) values[key] = prev; else delete values[key];  // откат
    toast("Не записалось — проверь сеть");
  }
  render();
}

function customInput(key) {
  const raw = prompt("Часы (0–24, можно 1.5 или 1,5):");
  if (raw == null) return;
  const v = parseFloat(raw.replace(",", "."));
  if (isNaN(v) || v < 0 || v > 24) { toast("Число 0–24"); return; }
  pick(key, Math.round(v * 2) / 2);
}

function render() {
  document.getElementById("title").textContent =
    date === defaultDate ? "Сегодня" :
    date === addDays(defaultDate, -1) ? "Вчера" : date;
  document.getElementById("btn-today").classList.toggle("active", date === defaultDate);
  document.getElementById("btn-yest").classList.toggle("active", date === addDays(defaultDate, -1));

  let html = "";
  for (const { key, display } of hobbies) {
    const v = values[key];
    const filled = v != null;
    html += `<div class="tile ${filled ? "filled" : ""}" data-key="${key}">
      <div class="name">${display}</div>
      <div class="val ${filled ? "" : "empty"}">${filled ? "✓ " + fmt(v) + " ч" : "тап — выбрать"}</div>
    </div>`;
    if (expanded === key) {
      const chips = PRESETS.map(p => `<button data-pick="${p}">${fmt(p)}</button>`).join("");
      html += `<div class="presets" data-key="${key}">
        <div class="title">${display} — сколько часов?</div>${chips}
        <button data-custom="1">✏️</button>
        <button class="clear" data-pick="0">✕</button>
      </div>`;
    }
  }
  document.getElementById("grid").innerHTML = html;

  const total = Object.values(values).reduce((a, b) => a + b, 0);
  document.getElementById("total").innerHTML =
    `<b>${fmt(Math.round(total * 2) / 2)} ч</b> · ${Object.keys(values).length} актив.`;
  const q = document.getElementById("queue");
  q.textContent = queuePending > 0 ? `⏳ ${queuePending} в очереди` : "✓ синк";
  q.classList.toggle("busy", queuePending > 0);
}

document.getElementById("grid").addEventListener("click", e => {
  const presetBtn = e.target.closest("[data-pick]");
  if (presetBtn) {
    pick(presetBtn.closest(".presets").dataset.key, parseFloat(presetBtn.dataset.pick));
    return;
  }
  if (e.target.closest("[data-custom]")) {
    customInput(e.target.closest(".presets").dataset.key);
    return;
  }
  const tile = e.target.closest(".tile");
  if (tile) {
    expanded = expanded === tile.dataset.key ? null : tile.dataset.key;
    render();
  }
});

document.getElementById("btn-today").onclick = () => loadDay(defaultDate);
document.getElementById("btn-yest").onclick = () => loadDay(addDays(defaultDate, -1));
document.getElementById("btn-cal").onclick = () => {
  const p = document.getElementById("datepick");
  p.showPicker ? p.showPicker() : p.click();
};
document.getElementById("datepick").onchange = e => e.target.value && loadDay(e.target.value);

let toastTimer;
function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2500);
}

(async function init() {
  try {
    const cfg = await api("/api/hobbies");
    hobbies = cfg.hobbies;
    defaultDate = cfg.default_date;
    queuePending = cfg.queue_pending;
    await loadDay(defaultDate);
  } catch (e) {
    document.getElementById("grid").innerHTML =
      `<div style="grid-column:1/-1;color:var(--danger);padding:20px">Ошибка загрузки: ${e.message}</div>`;
  }
})();
</script>
</body>
</html>
```

Примечание: `telegram-web-app.js` грузится с telegram.org — это официальный обязательный способ подключения SDK, вне Telegram-клиента страница покажет ошибку авторизации (ожидаемо).

- [ ] **Step 2: Локальная проверка (smoke)**

```bash
AUTH_DISABLED=1 TELEGRAM_BOT_TOKEN=x SPREADSHEET_ID=x \
  python -c "
import sys; sys.path.insert(0,'.')
import asyncio, uvicorn
import src.runtime as rt
rt.init_runtime()
from src.api.server import create_app
uvicorn.run(create_app(), host='127.0.0.1', port=8000)
"
```

Открыть `http://127.0.0.1:8000` в браузере. Ожидаемо: сетка категорий из `data/hobbies_history.txt`, тап раскрывает 19 пресетов, выбор помечает плитку, футер показывает итог. (`tg.initData` пустой — auth отключён флагом; Sheets недоступен — cache miss на старую дату упадёт, сегодняшний день после первого POST живёт из кэша.) Ctrl+C после проверки.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat: добавлен фронт Mini App (сетка, тап-пресеты, optimistic UI)"
```

---

### Task 10: main.py — сборка процесса

**Files:**
- Modify: `main.py` (полная замена `main()`)
- Modify: `src/utils/scheduler.py`

**Interfaces:**
- Consumes: `init_runtime`, `SyncWorker`, `create_app`, `validate_config`, существующие хендлеры
- Produces: один процесс: бот (polling) + uvicorn (:API_PORT) + sync-воркер + APScheduler; menu button Mini App

- [ ] **Step 1: Новый main.py**

Заменить содержимое `main.py` целиком:

```python
#!/usr/bin/env python3
"""Hobby Tracker Bot — бот + API Mini App + sync-воркер в одном процессе"""

import asyncio
import logging
import sys

import uvicorn
from telegram import MenuButtonWebApp, Update, WebAppInfo
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from src import runtime
from src.api.server import create_app
from src.bot.handlers import (
    start, help_cmd, quick_cmd, stats_cmd, list_all_cmd, reminders_cmd,
    button_callback, text_message_handler,
)
from src.data.files import create_sample_aliases
from src.data.sheets import get_sheets_manager
from src.data.sync_worker import SyncWorker
from src.utils.config import API_PORT, BOT_TOKEN, WEBAPP_URL, validate_config
from src.utils.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


def build_bot() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("quick", quick_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("list", list_all_cmd))
    app.add_handler(CommandHandler("reminders", reminders_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    return app


async def amain() -> None:
    runtime.init_runtime()

    bot_app = build_bot()
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("✅ Бот запущен (polling)")

    if WEBAPP_URL:
        await bot_app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="📝 Записать", web_app=WebAppInfo(url=WEBAPP_URL))
        )
        logger.info("✅ Menu button → %s", WEBAPP_URL)

    worker = SyncWorker(
        runtime.journal, runtime.wake,
        write_day=lambda values, date: get_sheets_manager().write_values(values, date),
        sheets_lock=runtime.sheets_lock,
    )
    worker_task = asyncio.create_task(worker.run())
    runtime.wake.set()  # доиграть несинканный хвост после рестарта
    logger.info("✅ Sync-воркер запущен")

    start_scheduler(BOT_TOKEN)
    logger.info("✅ Планировщик напоминаний запущен")

    server = uvicorn.Server(uvicorn.Config(
        create_app(), host="0.0.0.0", port=API_PORT, log_level="info"))
    logger.info("🎯 Всё запущено, API на :%d", API_PORT)
    await server.serve()  # блокируется до SIGTERM/SIGINT (uvicorn ловит сигналы)

    logger.info("🛑 Остановка...")
    worker_task.cancel()
    stop_scheduler()
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()
    logger.info("👋 Бот остановлен")


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler()],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger.info("🚀 Запуск Hobby Tracker...")
    try:
        validate_config()
        create_sample_aliases()
    except SystemExit:
        raise
    except Exception as e:
        logger.error("❌ Ошибка конфигурации: %s", e)
        sys.exit(1)
    asyncio.run(amain())


if __name__ == "__main__":
    main()
```

Старый `sys.path.insert` больше не нужен (импорты идут от `src.` из корня, как и раньше — Docker WORKDIR /app).

- [ ] **Step 2: scheduler через runtime**

В `src/utils/scheduler.py`:

1. Удалить `from ..data.sheets import SheetsManager` и `self.sheets = SheetsManager()` из `__init__` (строка 19).
2. В `_send_reminder` заменить чтение (строки 55–57):

```python
            from .. import runtime
            today = date_for_time()
            today_data = await runtime.get_day_values(today)
            today_total = sum(today_data.values()) if today_data else 0
```

- [ ] **Step 3: Smoke-run**

Run (с реальным .env и service_account.json локально): `python main.py`
Expected: в логах `✅ Бот запущен`, `✅ Sync-воркер запущен`, `Uvicorn running on http://0.0.0.0:8000`; Ctrl+C — чистое завершение без traceback. Если реального .env нет — отложить smoke до Task 12 (деплой), отметить это в отчёте.

Run: `pytest tests/ -v`
Expected: всё зелёное

- [ ] **Step 4: Commit**

```bash
git add main.py src/utils/scheduler.py
git commit -m "feat: собран единый процесс — бот, API, sync-воркер и планировщик"
```

---

### Task 11: Бот — запись через буфер, без задержек, batch-аналитика

**Files:**
- Modify: `src/bot/handlers.py`
- Modify: `src/bot/keyboards.py`

**Interfaces:**
- Consumes: `runtime.record_entry`, `runtime.get_day_values`, `get_sheets_manager().get_days_bulk`, `WEBAPP_URL`

- [ ] **Step 1: handlers.py — запись**

1. Удалить строку 32 `sheets = SheetsManager()` и импорт `SheetsManager` (строка 24). Добавить импорты:

```python
from .. import runtime
from ..data.sheets import get_sheets_manager
```

2. `handle_stars_selection` (строки 187–222) — заменить тело после парсинга `parts` на:

```python
        hobby_key = parts[1]
        stars = float(parts[2])
        target_date = parts[3]

        runtime.record_entry(target_date, hobby_key, stars, source="bot")

        hobby_display = get_hobby_display_name(hobby_key)
        result_text = format_hobby_stars_result(hobby_display, stars)

        current_date = date_for_time()
        show_today = target_date != current_date
        keyboard = create_hobby_keyboard(show_today_button=show_today)
        date_display = get_date_display_name(target_date)
        await query.edit_message_text(
            f"{result_text}\n\n🚀 Заполнение на {date_display}\nВыберите следующее увлечение:",
            reply_markup=keyboard,
        )
```

Уходят: `save_hobby_to_history` (теперь внутри `record_entry`), `asyncio.sleep(0.5)`, двойной `edit_message_text`, прямой `sheets.write_values` с `except: pass`.

3. В `text_message_handler`, ветка custom stars (строки 797–830): заменить блок от `save_hobby_to_history(hobby_name)` до конца `try` (кроме `except ValueError`) на:

```python
            runtime.record_entry(target_date, hobby_name, stars_value, source="bot")

            hobby_display = get_hobby_display_name(hobby_name)
            await update.message.reply_text(format_hobby_stars_result(hobby_display, stars_value))

            user_states.pop(user_id, None)
            keyboard = create_hobby_keyboard()
            date_display = get_date_display_name(date_for_time())
            await update.message.reply_text(
                f"🚀 Заполнение на {date_display}\n\nВыберите увлечение:",
                reply_markup=keyboard,
            )
            return
```

- [ ] **Step 2: handlers.py — чтение статистики через runtime**

`show_stats_for_date` (строки 277–304), заменить первые две строки `try`:

```python
        data = await runtime.get_day_values(target_date)
        total = sum(data.values())
```

- [ ] **Step 3: handlers.py — batch-аналитика**

Заменить `get_week_data` (строки 584–600) на async с одним запросом:

```python
async def get_week_data() -> dict:
    """Данные за последние 7 дней ОДНИМ запросом к Sheets"""
    from datetime import datetime, timedelta
    dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    async with runtime.sheets_lock:
        return await asyncio.to_thread(lambda: get_sheets_manager().get_days_bulk(dates))
```

В `show_weekly_analytics` (строка 606): `week_data = await get_week_data()`.

В `show_top3_analytics` (строки 679–698): `week_data = await get_week_data()`, а месячный цикл из 30 `get_day_data` заменить на:

```python
        month_dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
        async with runtime.sheets_lock:
            month_data = await asyncio.to_thread(
                lambda: get_sheets_manager().get_days_bulk(month_dates))
        month_totals = {}
        for day_data in month_data.values():
            for hobby, hours in day_data.items():
                if hours > 0:
                    month_totals[hobby] = month_totals.get(hobby, 0) + hours
```

(`today = datetime.now()` уже есть выше в функции.)

Примечание: в неделях/топах суммирование по `day_data.items()` должно пропускать нули — в `show_weekly_analytics` в цикле суммирования добавить `if hours > 0` аналогично.

- [ ] **Step 4: keyboards.py — кнопка Mini App**

В начало `create_hobby_keyboard` (после `buttons = []`, строка 12):

```python
    from ..utils.config import WEBAPP_URL
    from telegram import WebAppInfo
    if WEBAPP_URL:
        buttons.append([InlineKeyboardButton("⚡ Открыть Mini App", web_app=WebAppInfo(url=WEBAPP_URL))])
```

- [ ] **Step 5: Проверка**

Run: `pytest tests/ -v` — зелёное.
Run: `python -c "import sys; sys.path.insert(0,'.'); import os; os.environ.update(TELEGRAM_BOT_TOKEN='x', SPREADSHEET_ID='x'); from src.bot import handlers; print('ok')"`
Expected: `ok` (импорт-цикл не сломан)

Grep-проверка, что прямой записи не осталось: `grep -n "write_values\|sleep(0.5)" src/bot/handlers.py`
Expected: пусто

- [ ] **Step 6: Commit**

```bash
git add src/bot/handlers.py src/bot/keyboards.py
git commit -m "feat: бот пишет через журнал-буфер, убраны задержки и 30 запросов аналитики"
```

---

### Task 12: Деплой на orion (hobby.artfaal.ru)

**Files:**
- Modify: `Dockerfile`, `docker-compose.yml`, `.env.example`
- Server: `/var/docker/compose/hobby-tracker` на `orion.artfaal.ru`

- [ ] **Step 1: Dockerfile**

После `COPY main.py .` добавить:

```dockerfile
COPY frontend/ ./frontend/
```

- [ ] **Step 2: docker-compose.yml**

Привести к виду (паттерн budget-bot — caddy-docker-proxy):

```yaml
services:
  hobby-tracker:
    build: .
    container_name: hobby-tracker-bot
    restart: unless-stopped
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - SPREADSHEET_ID=${SPREADSHEET_ID}
      - SHEET_NAME=${SHEET_NAME:-Данные}
      - TIMEZONE=${TIMEZONE:-Europe/Moscow}
      - TZ=${TIMEZONE:-Europe/Moscow}
      - WEBAPP_URL=${WEBAPP_URL:-https://hobby.artfaal.ru}
      - ALLOWED_USER_IDS=${ALLOWED_USER_IDS}
    volumes:
      - ./data:/app/data
      - ./service_account.json:/app/service_account.json:ro
    labels:
      caddy: hobby.artfaal.ru
      caddy.reverse_proxy: "{{upstreams 8000}}"
    networks:
      - caddy
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "3"
        compress: "true"

networks:
  caddy:
    external: true
```

(`version:` и внутренняя `hobby-network` убраны — сеть caddy достаточна, наружу порт не пробрасывается.)

- [ ] **Step 3: .env.example**

Добавить:

```
# Mini App
WEBAPP_URL=https://hobby.artfaal.ru
# Твой telegram user_id (узнать: @userinfobot)
ALLOWED_USER_IDS=
```

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml .env.example
git commit -m "feat: добавлен деплой Mini App через caddy-docker-proxy"
```

- [ ] **Step 5: Выкат на orion**

DNS A-запись `hobby.artfaal.ru → 206.245.129.248` уже существует (проверено). Определить способ доставки кода: `ssh orion.artfaal.ru "git -C /var/docker/compose/hobby-tracker remote -v"` — если git-чекаут, пушим и пуллим; иначе rsync:

```bash
rsync -av --exclude venv --exclude .git --exclude data --exclude .env \
  --exclude service_account.json ./ orion.artfaal.ru:/var/docker/compose/hobby-tracker/
```

На сервере: дописать в `.env` `ALLOWED_USER_IDS=<user_id Макса>` (уточнить у него), затем:

```bash
ssh orion.artfaal.ru "cd /var/docker/compose/hobby-tracker && docker compose build && docker compose up -d && docker compose logs --tail 30"
```

Expected в логах: `✅ Бот запущен`, `✅ Menu button → https://hobby.artfaal.ru`, `Uvicorn running`.

- [ ] **Step 6: Проверка цепочки**

```bash
curl -si https://hobby.artfaal.ru/api/hobbies | head -3
```

Expected: `HTTP/2 401` + `Missing Telegram-Init-Data header` — TLS работает, caddy проксирует, auth закрыт.

```bash
curl -s https://hobby.artfaal.ru/ | grep -o "<title>[^<]*"
```

Expected: `<title>Hobby Tracker`

- [ ] **Step 7: E2E через Telegram (руками Макса или ui-tester)**

1. Открыть бота → menu button «📝 Записать» → Mini App открывается, сетка категорий
2. Тап по категории → 19 пресетов → выбрать значение → плитка помечена, футер «✓ синк»
3. Проверить, что значение появилось в Google Sheets (строка сегодняшней даты)
4. Переключить «Вчера», внести значение, проверить в Sheets
5. Старый флоу: /quick → выбрать хобби → звезда → ответ мгновенный, без секундной паузы
6. Тест живучести: `docker compose stop`, `docker compose start` — несинканное (если было) доехало в Sheets

- [ ] **Step 8: Commit финальных правок (если были) и отчёт**

---

### Task 13: Документация

**Files:**
- Modify: `README.md`, `CLAUDE.md`

- [ ] **Step 1:** Позвать сабагента doc-keeper (режим ПОЧИНКА): обновить README (Mini App, архитектура записи через журнал, новые env `WEBAPP_URL`/`ALLOWED_USER_IDS`/`API_PORT`, `hobby.artfaal.ru`, запуск тестов `pytest tests/`) и CLAUDE.md (устаревшие «два несогласованных пути записи», «sleep(0.5)», «тестов нет» — теперь есть; новая карта модулей: runtime, journal, daycache, sync_worker, api).

- [ ] **Step 2: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: обновлена документация под Mini App и буферную запись"
```

---

## Self-Review (выполнен)

- **Spec coverage:** механика B + 19 пресетов (T9), журнал/offset/компактация/битые строки (T2), воркер retry+backoff+компактация батча (T5), DayCache 7 дней + оверлей + `default_date` + `queue_pending` (T4, T6, T8), auth HMAC+allowlist (T7), бот-fallback без sleep + batch-аналитика + статистика из кэша (T11), напоминания через кэш (T10), деплой caddy + DNS (T12), критерий приёмки покрыт E2E-шагами (T12.7). Гэпов нет.
- **Placeholders:** нет TBD/«добавить валидацию» — код в каждом шаге.
- **Type consistency:** `record_entry(date, hobby, hours, source) -> int`, `get_day_values(date) -> dict`, `pending_with_raw_count() -> (list, int)`, `write_day(values, date)` — сверено между T2/T5/T6/T8/T10/T11.
