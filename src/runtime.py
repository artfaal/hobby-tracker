"""Синглтоны процесса (журнал, кэш, локи) и сервисные операции записи/чтения.

Единственный путь записи для бота И Mini App — record_entry().
"""

import asyncio
import datetime as dt
import logging

from .data.daycache import DayCache, merged
from .data.files import save_hobby_to_history
from .data.journal import Journal
from .data.sheets import get_sheets_manager, parse_days
from .utils.config import DAYCACHE_FILE, JOURNAL_FILE, JOURNAL_OFFSET_FILE
from .utils.dates import date_for_time

logger = logging.getLogger(__name__)

journal: Journal
cache: DayCache
wake: asyncio.Event
sheets_lock: asyncio.Lock


def init_runtime() -> None:
    """Создаёт синглтоны. Имена резолвятся из module globals в момент вызова —
    тесты подменяют runtime.JOURNAL_FILE и т.п. через monkeypatch."""
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


def _fetch_days_strict(dates: list[str]) -> dict[str, dict[str, float]]:
    """Как get_days_bulk, но БРОСАЕТ при недоступности Sheets —
    сверка не должна затирать кэш пустотой при сбое."""
    all_values = get_sheets_manager().ws.get_all_values()
    return parse_days(all_values, dates)


async def reconcile_cache() -> None:
    """Стартовая сверка последних 7 дней с Sheets (Sheets истина:
    ручные правки в таблице подтягиваются) + prune старых дат."""
    today = date_for_time()
    dates = [(dt.date.fromisoformat(today) - dt.timedelta(days=i)).isoformat()
             for i in range(7)]
    try:
        async with sheets_lock:
            days = await asyncio.to_thread(_fetch_days_strict, dates)
    except Exception as e:
        logger.warning("Стартовая сверка с Sheets не удалась, кэш оставлен как есть: %s", e)
        return
    for date, values in days.items():
        cache.set(date, values)
    cache.prune(today)
    logger.info("Кэш сверен с Sheets (%d дней)", len(dates))


async def get_day_values(date: str) -> dict[str, float]:
    base = cache.get(date)
    if base is None:
        async with sheets_lock:
            base = await asyncio.to_thread(lambda: get_sheets_manager().get_day_data(date))
        if _in_window(date):
            cache.set(date, base)
    return merged(base, journal.pending(), date)
