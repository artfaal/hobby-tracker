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
