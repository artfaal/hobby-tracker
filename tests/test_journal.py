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


def test_pending_with_raw_count(j, tmp_path):
    j.append("2026-07-06", "игры", 2.0, "bot")
    with open(tmp_path / "journal.jsonl", "a", encoding="utf-8") as f:
        f.write('{"обрыв\n')
    entries, raw = j.pending_with_raw_count()
    assert len(entries) == 1 and raw == 2


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
