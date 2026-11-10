"""Unit tests for VIP project journal routing / payloads (без Google API)."""

import pytest

from constants import VIP_JOURNAL_PROJECTS
from vip_journal_sheets import (
    VipJournalError,
    build_friendly_row_payload,
    build_short_row_payload,
    extract_friendly_scores,
    extract_short_scores,
    find_next_journal_row,
    make_analysis_id,
    normalize_project_key,
    parse_journal_managers,
    resolve_journal_call_type,
    resolve_manager_from_directory,
    resolve_project_route,
)


def test_project_routing_start_rows():
    assert resolve_project_route("Betking")["start_row"] == 3
    assert resolve_project_route("777")["start_row"] == 3
    assert resolve_project_route("Vegas")["start_row"] == 5
    assert resolve_project_route("vegas")["sheet_id"] == VIP_JOURNAL_PROJECTS["vegas"]["sheet_id"]
    with pytest.raises(VipJournalError):
        resolve_project_route("unknown")


def test_call_type_from_analyzer_choice_not_duration():
    assert resolve_journal_call_type("short") == "short"
    assert resolve_journal_call_type("friendly") == "friendly"
    assert resolve_journal_call_type("Короткий 90 сек") == "short"
    assert resolve_journal_call_type("VIP Friendly (2-й дзвінок)") == "friendly"
    assert resolve_journal_call_type("vip_friendly") == "friendly"
    assert resolve_journal_call_type("") is None


def test_normalize_project_aliases():
    assert normalize_project_key("BETKING") == "betking"
    assert normalize_project_key("Вегас") == "vegas"
    assert normalize_project_key("777") == "777"


def test_short_scores_allow_zero_keep_empty_missing():
    verdict = {
        "criteria": [
            {"key": "contact", "points": 0},
            {"key": "slip_handling", "points": 7.5},
            {"key": "prep", "points": 10},
            # closing відсутній → None (не 0)
        ]
    }
    scores = extract_short_scores(verdict)
    assert scores["contact"] == 0.0
    assert scores["slip_handling"] == 7.5
    assert scores["prep"] == 10.0
    assert scores["closing"] is None


def test_friendly_cta_rejects_7_5():
    verdict = {
        "criteria": [
            {"key": "contact", "points": 5},
            {"key": "friendly_development", "points": 7.5},
            {"key": "personal_approach", "points": 7.5},
            {"key": "call_to_action", "points": 7.5},
            {"key": "bonus_offer", "points": 5},
            {"key": "prep", "points": 10},
            {"key": "closing", "points": 5},
            {"key": "ease", "points": 7.5},
        ]
    }
    with pytest.raises(VipJournalError):
        extract_friendly_scores(verdict)


def test_friendly_max_scores_payload_skips_formula_and_qa_cols():
    from datetime import date

    scores = {
        "contact": 5.0,
        "friendly_development": 7.5,
        "personal_approach": 7.5,
        "call_to_action": 10.0,
        "bonus_offer": 5.0,
        "prep": 10.0,
        "closing": 5.0,
        "ease": 7.5,
    }
    payload = build_friendly_row_payload(
        client_id="01234",
        call_date=date(2026, 11, 10),
        manager="Тест Менеджер",
        tl="ТЛ",
        scores=scores,
        check_date=date(2026, 11, 10),
    )
    assert payload["N"].startswith("'")
    assert "Z" not in payload
    assert "AB" not in payload
    assert payload["AA"] == "АІ"
    assert payload["Y"] == 7.5
    assert sum(v for v in scores.values()) == 57.5


def test_short_payload_skips_formula_writes_card_comment():
    from datetime import date

    scores = {"contact": 5.0, "slip_handling": 10.0, "prep": 10.0, "closing": 5.0}
    payload = build_short_row_payload(
        client_id="99",
        call_date=date(2026, 9, 1),
        manager="Менеджер",
        tl="TL",
        scores=scores,
        check_date=date(2026, 9, 2),
        qa_comment="клієнт просив передзвін",
    )
    assert "I" not in payload
    assert payload["K"] == "клієнт просив передзвін"
    assert payload["J"] == "АІ"
    assert sum(v for v in scores.values()) == 30.0


def test_friendly_payload_writes_comment_to_ab():
    from datetime import date

    scores = {
        "contact": 5.0,
        "friendly_development": 7.5,
        "personal_approach": 7.5,
        "call_to_action": 10.0,
        "bonus_offer": 5.0,
        "prep": 10.0,
        "closing": 5.0,
        "ease": 7.5,
    }
    payload = build_friendly_row_payload(
        client_id="1",
        call_date=date(2026, 9, 1),
        manager="М",
        tl="Т",
        scores=scores,
        check_date=date(2026, 9, 2),
        qa_comment="тон ок",
    )
    assert "Z" not in payload
    assert payload["AB"] == "тон ок"


def test_find_next_row_ignores_prefilled_below_gap():
    # рядок 1-2 заголовки, start=3; A3 зайнятий, A4 порожній
    col = ["", "", "id1", "", "ghost"]
    assert find_next_journal_row(col, start_row=3) == 4


def test_manager_lookup_by_project_and_login():
    managers = parse_journal_managers(
        [
            ["Проєкт", "TL", "Менеджер", "Логін"],
            ["Betking", "Анна", "Іваненко Іван", "ivan"],
            ["Betking", "Анна", "Петренко Петро", "petro"],
            ["Vegas", "Олег", "Іваненко Іван", "ivan_vegas"],
        ]
    )
    row = resolve_manager_from_directory(
        managers, project_key="betking", login="ivan", manager_name=""
    )
    assert row["manager"] == "Іваненко Іван"
    assert row["tl"] == "Анна"
    with pytest.raises(VipJournalError):
        resolve_manager_from_directory(managers, project_key="betking", login="missing")


def test_analysis_id_stable_for_retry():
    call = {
        "url": "https://x",
        "client_id": "1",
        "call_date": "01.09.2026",
        "check_date": "10.11.2026",
        "ret_manager": "A",
    }
    a = make_analysis_id(call, "short")
    b = make_analysis_id(dict(call), "short")
    assert a == b
    assert make_analysis_id(call, "friendly") != a
