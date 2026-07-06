import asyncio

import pytest

import src.runtime as runtime


@pytest.fixture
def rt(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "JOURNAL_FILE", str(tmp_path / "j.jsonl"))
    monkeypatch.setattr(runtime, "JOURNAL_OFFSET_FILE", str(tmp_path / "j.offset"))
    monkeypatch.setattr(runtime, "DAYCACHE_FILE", str(tmp_path / "days.json"))
    monkeypatch.setattr(runtime, "save_hobby_to_history", lambda h: None)
    # Тестовые даты фиксированные — окно кэша не должно зависеть от реального «сегодня»
    monkeypatch.setattr(runtime, "_in_window", lambda date, window=7: True)
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


def test_reconcile_cache_pulls_sheets_and_prunes(rt, monkeypatch):
    # Устаревшее значение в кэше + очень старая дата
    rt.cache.set("2026-07-05", {"игры": 9.0})
    rt.cache.set("2020-01-01", {"мото": 1.0})
    monkeypatch.setattr(rt, "date_for_time", lambda *a: "2026-07-06")
    monkeypatch.setattr(
        rt, "_fetch_days_strict",
        lambda dates: {d: ({"игры": 2.0} if d == "2026-07-05" else {}) for d in dates})
    asyncio.run(rt.reconcile_cache())
    assert rt.cache.get("2026-07-05") == {"игры": 2.0}   # Sheets победил
    assert rt.cache.get("2020-01-01") is None             # prune сработал


def test_reconcile_cache_failure_keeps_cache(rt, monkeypatch):
    rt.cache.set("2026-07-05", {"игры": 9.0})

    def boom(dates):
        raise RuntimeError("sheets down")

    monkeypatch.setattr(rt, "_fetch_days_strict", boom)
    asyncio.run(rt.reconcile_cache())
    assert rt.cache.get("2026-07-05") == {"игры": 9.0}   # не затёрто пустотой


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
