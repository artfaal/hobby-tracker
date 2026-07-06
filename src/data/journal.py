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

    def _ends_with_newline(self) -> bool:
        try:
            with open(self.journal_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                if f.tell() == 0:
                    return True
                f.seek(-1, os.SEEK_END)
                return f.read(1) == b"\n"
        except FileNotFoundError:
            return True

    def append(self, date: str, hobby: str, hours: float, source: str) -> None:
        entry = {
            "ts": datetime.now(tz=get_tz()).isoformat(),
            "date": date,
            "hobby": hobby,
            "hours": hours,
            "source": source,
        }
        os.makedirs(os.path.dirname(self.journal_path) or ".", exist_ok=True)
        # Защита от оборванного хвоста: не приклеиваемся к недописанной строке
        prefix = "" if self._ends_with_newline() else "\n"
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(prefix + json.dumps(entry, ensure_ascii=False) + "\n")
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

    def pending_with_raw_count(self) -> tuple[list[dict], int]:
        """Несинканные записи + число сырых строк (включая битые) для advance()"""
        raw = self._read_lines()[self._read_offset():]
        entries = []
        for line in raw:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Пропущена битая строка журнала: %r", line[:80])
        return entries, len(raw)

    def pending(self) -> list[dict]:
        return self.pending_with_raw_count()[0]

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
