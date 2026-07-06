from src.data.sheets import parse_days

ALL_VALUES = [
    ["Дата", "игры", "мото", "спортзал"],
    ["2026-07-04", "2", "", "1,5"],
    ["2026-07-05", "0", "3.5", ""],
    ["2026-07-06", "", "", ""],
]


def test_parse_days_basic():
    out = parse_days(ALL_VALUES, ["2026-07-04", "2026-07-05"])
    assert out["2026-07-04"] == {"игры": 2.0, "спортзал": 1.5}
    assert out["2026-07-05"] == {"игры": 0.0, "мото": 3.5}


def test_parse_days_missing_date_is_empty():
    out = parse_days(ALL_VALUES, ["2026-07-06", "2026-01-01"])
    assert out["2026-07-06"] == {}
    assert out["2026-01-01"] == {}


def test_parse_days_bad_cell_ignored():
    vals = [["Дата", "игры"], ["2026-07-04", "абв"]]
    assert parse_days(vals, ["2026-07-04"]) == {"2026-07-04": {}}


def test_parse_days_empty_sheet():
    assert parse_days([], ["2026-07-04"]) == {"2026-07-04": {}}


def test_parse_days_normalizes_header_keys():
    """Регресс: колонка «книги RU» в таблице не должна плодить дубль
    ключа «книги ru» — весь код живёт в нормализованном пространстве"""
    vals = [["Дата", "книги RU", "Ёлки"], ["2026-07-04", "5", "1"]]
    assert parse_days(vals, ["2026-07-04"]) == {
        "2026-07-04": {"книги ru": 5.0, "елки": 1.0}
    }
