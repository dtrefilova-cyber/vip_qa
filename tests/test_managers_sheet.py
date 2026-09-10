"""Парсинг аркуша MANAGERS і фільтр селекта за проєктом."""

from google_sheets import clean_sheet_cell, parse_managers_sheet_values
from upload_cards import _managers_for_project


def test_parse_keeps_shmyrov_from_managers_sheet():
    values = [
        ["PROJECT", "TL", "MANAGER"],
        ["betking", "Мальцева Єлизавета", "Мазур Христина"],
        ["betking", "Мальцева Єлизавета", "Звенигородська Наталія"],
        ["betking", "Мальцева Єлизавета", "Шмирьов Олексій"],
        ["betking", "Мальцева Єлизавета", "Шмалько Дмитро"],
        ["vegas", "Шваб Валерій", "Кизима Микола"],
        ["", "", ""],
    ]
    rows = parse_managers_sheet_values(values)
    names = [r["manager"] for r in rows]
    assert "Шмирьов Олексій" in names
    shmyrov = next(r for r in rows if r["manager"] == "Шмирьов Олексій")
    assert shmyrov["project"] == "betking"
    assert shmyrov["tl"] == "Мальцева Єлизавета"


def test_parse_strips_invisible_chars_in_manager_name():
    values = [
        ["PROJECT", "TL", "MANAGER"],
        ["betking", "Мальцева Єлизавета", "\u200bШмирьов Олексій"],
    ]
    rows = parse_managers_sheet_values(values)
    assert rows[0]["manager"] == "Шмирьов Олексій"


def test_clean_sheet_cell_nfkc():
    assert clean_sheet_cell("  Шмирьов Олексій\ufeff ") == "Шмирьов Олексій"


def test_managers_for_project_is_case_insensitive():
    config = [
        {"project": "betking", "tl": "Мальцева Єлизавета", "manager": "Шмирьов Олексій"},
        {"project": "Betking", "tl": "Сорока Анастасія", "manager": "Кваша Олег"},
        {"project": "vegas", "tl": "Шваб Валерій", "manager": "Кизима Микола"},
    ]
    names = _managers_for_project(config, "betking")
    assert "Шмирьов Олексій" in names
    assert "Кваша Олег" in names
    assert "Кизима Микола" not in names
