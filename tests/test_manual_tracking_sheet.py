"""Тести ручного колонкового RESULTS для vip_short_90s."""

from google_sheets import (
    MANUAL_TRACKING_CRITICAL_MARK,
    MANUAL_TRACKING_CRITICAL_SUMMARY,
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


def test_find_next_comment_row():
    col_a = [""] * 12 + ["111", "222"]  # rows 1–12 empty placeholders, 13–14 filled
    # indices 0..11 empty, 12="111", 13="222" → next empty is row 15
    assert find_next_comment_row(col_a) == 15


def test_find_next_comment_row_when_empty_from_start():
    col_a = [""] * 12  # nothing from row 13
    assert find_next_comment_row(col_a) == 13


def _sample_criteria(contact=5, slip=10, prep=10, closing=5):
    return [
        {"key": "contact", "points": contact, "max_points": 5, "reasons": []},
        {"key": "slip_handling", "points": slip, "max_points": 10, "reasons": []},
        {"key": "prep", "points": prep, "max_points": 10, "reasons": []},
        {"key": "closing", "points": closing, "max_points": 5, "reasons": []},
    ]


def test_build_manual_tracking_column_values_normal():
    call = {
        "call_date": "31.08.2026",
        "client_id": "12345",
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
        "Дар'я",
        "09.09.2026",
        "5",
        "7.5",
        "",
        "10",
        "2.5",
    ]


def test_build_manual_tracking_column_values_critical_slip():
    call = {
        "call_date": "31.08.2026",
        "client_id": "999",
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
    assert values[2] == "Дар'я"
    assert values[3] == "09.09.2026"
    # бальні рядки порожні (не нулі), гейт позначений
    assert values[4] == ""
    assert values[5] == ""
    assert values[6] == MANUAL_TRACKING_CRITICAL_MARK
    assert values[7] == ""
    assert values[8] == ""

    comment = build_manual_tracking_comment_text(call, verdict)
    assert MANUAL_TRACKING_CRITICAL_SUMMARY in comment
    assert "Штучно затягував дзвінок" in comment
    assert "тест" in comment
