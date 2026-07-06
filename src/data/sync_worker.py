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
