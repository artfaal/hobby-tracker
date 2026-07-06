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


async def get_day_values(date: str) -> dict[str, float]:
    base = cache.get(date)
    if base is None:
        async with sheets_lock:
            base = await asyncio.to_thread(lambda: get_sheets_manager().get_day_data(date))
        if _in_window(date):
            cache.set(date, base)
    return merged(base, journal.pending(), date)
