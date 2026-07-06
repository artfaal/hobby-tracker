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
    monkeypatch.setattr(runtime, "_in_window", lambda date, window=7: True)
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
