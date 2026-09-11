"""Тести ручного колонкового RESULTS / RESULTS FRIENDLY."""

from google_sheets import (
    FRIENDLY_MANUAL_TRACKING_FIRST_COL,
    FRIENDLY_MANUAL_TRACKING_COMMENT_START_ROW,
    MANUAL_TRACKING_CRITICAL_MARK,
    MANUAL_TRACKING_CRITICAL_SUMMARY,
    build_friendly_manual_tracking_column_values,
    build_friendly_manual_tracking_comment_text,
    build_manual_tracking_column_values,
    build_manual_tracking_comment_text,
    col_index_to_letter,
    find_next_comment_row,
    find_next_tracking_column,
)


def test_col_index_to_letter():
    assert col_index_to_letter(1) == "A"
    assert col_index_to_letter(2) == "B"
    assert col_index_to_letter(3) == "C"
    assert col_index_to_letter(27) == "AA"


def test_find_next_tracking_column_starts_at_c():
    # A=labels, B=occupied → next is C (3)
    row1 = ["Дата дзвінка", "01.09.2026"]
    assert find_next_tracking_column(row1) == 3


def test_find_next_tracking_column_skips_filled():
    row1 = ["Дата дзвінка", "01.09.2026", "02.09.2026", "03.09.2026"]
    assert find_next_tracking_column(row1) == 5  # E


def test_find_next_tracking_column_friendly_starts_at_b():
    row2 = ["Дата дзвінка"]  # тільки мітка в A
    assert find_next_tracking_column(row2, FRIENDLY_MANUAL_TRACKING_FIRST_COL) == 2


def test_find_next_comment_row():
    col_a = [""] * 12 + ["комент1", "комент2"]  # rows 13–14 filled
    assert find_next_comment_row(col_a) == 15


def test_find_next_comment_row_when_empty_from_start():
    col_a = [""] * 12  # nothing from row 13
    assert find_next_comment_row(col_a) == 13


def test_find_next_comment_row_skips_legacy_id_in_a_or_b():
    # Старий формат: A=ID; новий: B=ID — обидва вважаємо зайнятими
    col_a = [""] * 12 + ["111"]
    col_b = [""] * 12 + [""]
    assert find_next_comment_row(col_a, col_b_values=col_b) == 14
    col_a2 = [""] * 12 + [""]
    col_b2 = [""] * 12 + ["222"]
    assert find_next_comment_row(col_a2, col_b_values=col_b2) == 14


def test_find_next_comment_row_friendly_starts_at_15():
    col_a = [""] * 14
    assert find_next_comment_row(col_a, FRIENDLY_MANUAL_TRACKING_COMMENT_START_ROW) == 15


def _sample_criteria(contact=5, slip=10, prep=10, closing=5):
    return [
        {"key": "contact", "points": contact, "max_points": 5, "reasons": []},
        {"key": "slip_handling", "points": slip, "max_points": 10, "reasons": []},
        {"key": "prep", "points": prep, "max_points": 10, "reasons": []},
        {"key": "closing", "points": closing, "max_points": 5, "reasons": []},
    ]


def _sample_friendly_criteria():
    return [
        {"key": "contact", "points": 5, "max_points": 5, "reasons": []},
        {"key": "friendly_development", "points": 7.5, "max_points": 7.5, "reasons": []},
        {"key": "personal_approach", "points": 5, "max_points": 7.5, "reasons": []},
        {"key": "call_to_action", "points": 10, "max_points": 10, "reasons": []},
        {"key": "bonus_offer", "points": 5, "max_points": 5, "reasons": []},
        {"key": "prep", "points": 10, "max_points": 10, "reasons": []},
        {"key": "closing", "points": 5, "max_points": 5, "reasons": []},
        {"key": "ease", "points": 10, "max_points": 10, "reasons": []},
    ]


def test_build_manual_tracking_column_values_normal():
    call = {
        "call_date": "31.08.2026",
        "client_id": "12345",
        "ret_manager": "Сорока Анастасія",
        "qa_manager": "Дар'я",
        "check_date": "09.09.2026",
    }
    verdict = {
        "is_critical_fail": False,
        "criteria": _sample_criteria(5, 7.5, 10, 2.5),
    }
    values = build_manual_tracking_column_values(call, verdict)
    assert values == [
        "31.08.2026",
        "12345",
        "Сорока Анастасія",
        "09.09.2026",
        "5",
        "7.5",
        "",
        "10",
        "2.5",
    ]


def test_build_manual_tracking_column_values_critical_zeros_scores():
    call = {
        "call_date": "31.08.2026",
        "client_id": "999",
        "ret_manager": "Крисак Іван",
        "qa_manager": "Дар'я",
        "check_date": "09.09.2026",
        "qa_comment": "тест",
    }
    verdict = {
        "is_critical_fail": True,
        "critical_reasons": ["Штучно затягував дзвінок"],
        "total_score": 0.0,
        "max_score": 30.0,
        "criteria": _sample_criteria(5, 10, 10, 5),
    }
    values = build_manual_tracking_column_values(call, verdict)
    assert values[0] == "31.08.2026"
    assert values[1] == "999"
    assert values[2] == "Крисак Іван"
    assert values[3] == "09.09.2026"
    # бальні рядки = 0, гейт позначений
    assert values[4] == "0"
    assert values[5] == "0"
    assert values[6] == MANUAL_TRACKING_CRITICAL_MARK
    assert values[7] == "0"
    assert values[8] == "0"

    comment = build_manual_tracking_comment_text(call, verdict)
    assert MANUAL_TRACKING_CRITICAL_SUMMARY in comment
    assert "Критична помилка: Штучно затягував дзвінок" in comment
    assert "тест" in comment


def test_build_friendly_manual_tracking_column_values():
    call = {
        "call_date": "01.09.2026",
        "client_id": "555",
        "ret_manager": "Сорока Анастасія",
        "check_date": "11.09.2026",
    }
    verdict = {"criteria": _sample_friendly_criteria()}
    values = build_friendly_manual_tracking_column_values(call, verdict)
    assert values == [
        "01.09.2026",
        "555",
        "Сорока Анастасія",
        "11.09.2026",
        "5",
        "7.5",
        "5",
        "10",
        "5",
        "10",
        "5",
        "10",
    ]
    assert len(values) == 12  # rows 2–13


def test_build_friendly_manual_tracking_comment_text_uses_qa_note():
    call = {"client_id": "1", "qa_comment": "дружелюбний тон"}
    verdict = {"criteria": _sample_friendly_criteria()}
    assert build_friendly_manual_tracking_comment_text(call, verdict) == "дружелюбний тон"
