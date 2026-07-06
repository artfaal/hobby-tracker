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
