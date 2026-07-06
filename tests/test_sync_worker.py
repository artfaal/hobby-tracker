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
