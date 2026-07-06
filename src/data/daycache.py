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
