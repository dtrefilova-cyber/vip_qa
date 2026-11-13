"""Unit tests for VIP project journal routing / payloads (без Google API)."""

import pytest

from constants import VIP_JOURNAL_PROJECTS
from vip_journal_sheets import (
    VipJournalError,
    build_friendly_row_payload,
    build_short_row_payload,
    discover_journal_columns,
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
    assert resolve_journal_call_type("Короткий 120 сек") == "short"
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
    assert payload["O"].startswith("'")
    assert "S" not in payload  # Статус від TL
    assert "AB" not in payload  # формула балу
    assert payload["AC"] == "АІ"
    assert payload["T"] == 5.0  # контакт
    assert payload["AA"] == 7.5  # невимушеність
    assert payload["Z"] == 5.0  # завершення
    assert sum(v for v in scores.values()) == 57.5


def test_journal_comment_uses_score_results_not_manual_card_note():
    from vip_journal_sheets import build_journal_qa_comment

    verdict = {
        "criteria": [
            {
                "key": "contact",
                "label": "Встановлення контакту",
                "points": 2.5,
                "max_points": 5,
                "reasons": ["Відсутній елемент привітання: ім'я клієнта"],
            }
        ]
    }
    comment = build_journal_qa_comment({"qa_comment": "ручний текст з картки"}, verdict)
    assert "ручний текст з картки" not in comment
    assert "ім'я клієнта" in comment
    assert "Встановлення контакту" in comment


def test_short_payload_skips_formula_writes_result_comment():
    from datetime import date

    scores = {"contact": 5.0, "slip_handling": 10.0, "prep": 10.0, "closing": 5.0}
    payload = build_short_row_payload(
        client_id="99",
        call_date=date(2026, 9, 1),
        manager="Менеджер",
        tl="TL",
        scores=scores,
        check_date=date(2026, 9, 2),
        qa_comment="— Встановлення контакту: 2.5/5 (Відсутній елемент привітання: ім'я клієнта)",
    )
    assert "E" not in payload  # нова колонка після TL
    assert "J" not in payload  # формула балу
    assert payload["F"] == 5.0
    assert "ім'я клієнта" in payload["L"]
    assert payload["K"] == "АІ"
    assert sum(v for v in scores.values()) == 30.0


def test_friendly_payload_writes_result_comment_to_ac():
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
        qa_comment="— Завершення: 2.5/5 (Відсутній елемент завершення: прощання)",
    )
    assert "AB" not in payload  # формула
    assert "прощання" in payload["AD"]
    assert payload["AC"] == "АІ"


def test_discover_real_betking_headers_maps_slip_not_manager():
    """Реальні заголовки журналу: «Робота менеджера зі зливом» ≠ manager."""
    headers = [[
        "ID клієнта",
        "Дата дзвінка",
        "Менеджер VIP",
        "TL",
        "Статус від TL",
        "Встановлення контакту",
        'Робота менеджера зі "зливом" клієнта',
        "Робота з негативом/заперення P.R.E.P",
        "Завершення",
        "Бал за дзвінок",
        "Перевіряючий",
        "Коментар QA",
        "Дата перевірки",
        "",
        "ID клієнта",
        "Дата дзвінка",
        "Менеджер VIP",
        "TL",
        "Статус від TL",
        "Встановлення контакту",
        "Розвиток френдлі",
        "Індивідуальний підхід",
        "Заклик до гри",
        "Пропозиція бонусів",
        "Робота з негативом/заперення P.R.E.P",
        "Завершення",
        "Невимушеність",
        "Бал за дзвінок",
        "Перевіряючий",
        "Коментар QA",
        "Дата перевірки",
    ]]
    mapping = discover_journal_columns(headers)
    short = mapping["short"]
    friendly = mapping["friendly"]
    assert short["manager"] == "C"
    assert short["tl"] == "D"
    assert short.get("tl_status") == "E"
    assert short["contact"] == "F"
    assert short["slip_handling"] == "G"
    assert short["total_score"] == "J"
    assert short["reviewer"] == "K"
    assert friendly["contact"] == "T"
    assert friendly["ease"] == "AA"
    assert friendly["total_score"] == "AB"
    assert friendly["reviewer"] == "AC"
    assert mapping["skip"] == {"J", "AB"}


def test_parse_protected_data_index():
    from vip_journal_sheets import _parse_protected_data_index

    err = Exception(
        "APIError: [400]: Invalid data[12]: You are trying to edit a protected cell"
    )
    assert _parse_protected_data_index(err) == 12


def test_find_next_row_ignores_prefilled_below_gap():
    # рядок 1-2 заголовки, start=3; A3 зайнятий, A4 порожній
    col = ["", "", "id1", "", "ghost"]
    assert find_next_journal_row(col, start_row=3) == 4


def test_find_next_row_skips_row_with_manager_but_empty_id():
    # ID порожній, але менеджер уже є — рядок зайнятий (захист від перезапису)
    ids = ["", "", "", ""]
    managers = ["", "", "Іваненко", ""]
    assert find_next_journal_row(ids, start_row=3, extra_cols=[managers]) == 4


def test_reread_rejects_date_and_comment_drift():
    from vip_journal_sheets import _payload_matches, _strict_cols_for_fields

    fields = {
        "client_id": "'100",
        "call_date": "10.11.2026",
        "manager": "Менеджер",
        "contact": 5.0,
        "comment": "довгий коментар\nз переносом",
        "reviewer": "АІ",
        "check_date": "11.11.2026",
    }
    colmap = {
        "client_id": "A",
        "call_date": "B",
        "manager": "C",
        "contact": "F",
        "comment": "L",
        "reviewer": "K",
        "check_date": "M",
    }
    expected = {
        "A": "'100",
        "B": "10.11.2026",
        "C": "Менеджер",
        "F": 5.0,
        "L": "довгий коментар\nз переносом",
        "K": "АІ",
        "M": "11.11.2026",
    }
    actual = {
        "A": "100",
        "B": "2026-11-10",
        "C": "Менеджер",
        "F": "5",
        "L": "інший текст",
        "K": "АІ",
        "M": "2026-11-11",
    }
    strict = _strict_cols_for_fields(fields, colmap)
    assert strict == {"A", "B", "C", "F", "K", "L", "M"}
    assert _payload_matches(expected, actual, strict_cols=strict) is False


def test_discover_columns_after_tl_insert_for_both_blocks():
    headers = [[
        "ID клієнта",
        "Дата дзвінка",
        "Менеджер VIP",
        "TL",
        "Статус від TL",
        "Встановлення контакту",
        'Робота менеджера зі "зливом" клієнта',
        "P.R.E.P",
        "Завершення",
        "Бал за дзвінок",
        "Перевіряючий",
        "Коментар QA",
        "Дата перевірки",
        "",
        "ID клієнта",
        "Дата дзвінка",
        "Менеджер VIP",
        "TL",
        "Статус від TL",
        "Встановлення контакту",
        "Розвиток френдлі",
        "Індивідуальний підхід",
        "Заклик до гри",
        "Пропозиція бонусів",
        "P.R.E.P",
        "Завершення",
        "Невимушеність",
        "Бал за дзвінок",
        "Перевіряючий",
        "Коментар QA",
        "Дата перевірки",
    ]]
    mapping = discover_journal_columns(headers)
    short = mapping["short"]
    friendly = mapping["friendly"]
    assert short["client_id"] == "A"
    assert short["tl"] == "D"
    assert short["contact"] == "F"
    assert short["slip_handling"] == "G"
    assert short["closing"] == "I"
    assert short["total_score"] == "J"
    assert short["reviewer"] == "K"
    assert short["comment"] == "L"
    assert short["check_date"] == "M"
    assert short.get("tl_status") == "E"
    assert friendly["client_id"] == "O"
    assert friendly["tl"] == "R"
    assert friendly["contact"] == "T"
    assert friendly["closing"] == "Z"
    assert friendly["ease"] == "AA"
    assert friendly["total_score"] == "AB"
    assert friendly["reviewer"] == "AC"
    assert friendly["comment"] == "AD"
    assert friendly["check_date"] == "AE"


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
        "card_id": 1,
    }
    a = make_analysis_id(call, "short")
    b = make_analysis_id(dict(call), "short")
    assert a == b
    assert make_analysis_id(call, "friendly") != a


def test_short_journal_comment_includes_note_manual_and_scores():
    """Короткий коментар тримає розбір балів і VIP-інфо картки, без обрізання."""
    from vip_journal_sheets import build_journal_qa_comment

    note = "Клієнт не бере бонуси до депозиту. " + ("ліміти " * 40).strip()
    manual = "Месенджер до дзвінка, Viber."
    verdict = {
        "call_type": "vip_short_90s",
        "criteria": [
            {
                "key": "slip_handling",
                "label": "Робота зі «зливом» / утримання контакту",
                "points": 10,
                "max_points": 10,
                "reasons": [
                    "Клієнт не намагався завершити дзвінок достроково — критерій не застосовний"
                ],
            }
        ],
    }
    comment = build_journal_qa_comment(
        {
            "journal_call_type": "short",
            "important_note": note,
            "qa_comment": manual,
        },
        verdict,
    )
    assert "критерій не застосовний" in comment
    assert "Робота зі «зливом»" in comment
    assert comment.index("критерій не застосовний") < comment.index("Важливе:")
    assert "Важливе: " + note in comment
    assert "Коментар до дзвінка: " + manual in comment
    assert len(comment) > len(note)


def test_friendly_journal_comment_does_not_copy_card_note():
    from vip_journal_sheets import build_journal_qa_comment

    verdict = {
        "call_type": "vip_friendly",
        "criteria": [
            {
                "key": "contact",
                "label": "Встановлення контакту",
                "points": 5,
                "max_points": 5,
                "reasons": [],
            }
        ],
    }
    comment = build_journal_qa_comment(
        {
            "journal_call_type": "friendly",
            "important_note": "секретне важливе",
            "qa_comment": "ручний friendly",
        },
        verdict,
    )
    assert "секретне важливе" not in comment
    assert "ручний friendly" not in comment
    assert "Встановлення контакту" in comment


def test_short_slip_headers_keep_computed_score_including_zero():
    from datetime import date

    titles = (
        'Робота зі "зливом" клієнта',
        "Утримання контакту",
        "Удержание контакта",
        "Робота менеджера зі сливом",
    )
    for title in titles:
        headers = [[
            "ID клієнта",
            "Дата дзвінка",
            "Менеджер VIP",
            "TL",
            "Статус від TL",
            "Встановлення контакту",
            title,
            "P.R.E.P",
            "Завершення",
            "Бал за дзвінок",
            "Перевіряючий",
            "Коментар QA",
            "Дата перевірки",
            "",
            "ID клієнта",
            "Дата дзвінка",
            "Менеджер VIP",
            "TL",
            "Статус від TL",
            "Встановлення контакту",
            "Розвиток френдлі",
            "Невимушеність",
            "Бал за дзвінок",
            "Коментар QA",
        ]]
        short = discover_journal_columns(headers)["short"]
        assert short["slip_handling"] == "G", title
        payload = build_short_row_payload(
            client_id="42",
            call_date=date(2026, 11, 12),
            manager="Менеджер",
            tl="TL",
            scores={"contact": 5.0, "slip_handling": 0.0, "prep": 10.0, "closing": 2.5},
            check_date=date(2026, 11, 13),
            qa_comment="— Злив: 0/10",
            colmap=short,
        )
        assert payload["G"] == 0.0
        assert "J" not in payload
        assert "Злив" in payload["L"]


def test_short_payload_refuses_missing_slip_column():
    from datetime import date

    colmap = {
        "client_id": "A",
        "call_date": "B",
        "manager": "C",
        "tl": "D",
        "contact": "F",
        "prep": "H",
        "closing": "I",
        "reviewer": "K",
        "comment": "L",
        "check_date": "M",
    }
    with pytest.raises(VipJournalError, match="slip_handling"):
        build_short_row_payload(
            client_id="1",
            call_date=date(2026, 11, 1),
            manager="М",
            tl="Т",
            scores={"contact": 5.0, "slip_handling": 10.0, "prep": 10.0, "closing": 5.0},
            check_date=date(2026, 11, 2),
            colmap=colmap,
        )


def _a1_cells(ref: str, row_values: list) -> dict[str, object]:
    start, _, end = ref.partition(":")
    letters_row = start
    row = "".join(ch for ch in letters_row if ch.isdigit())
    start_letter = "".join(ch for ch in letters_row if ch.isalpha())
    end_letter = "".join(ch for ch in (end or start) if ch.isalpha()) or start_letter
    from vip_journal_sheets import _col_letter_to_index
    from google_sheets import col_index_to_letter

    values = list(row_values)
    out = {}
    for offset, idx in enumerate(
        range(_col_letter_to_index(start_letter), _col_letter_to_index(end_letter) + 1)
    ):
        out[f"{col_index_to_letter(idx)}{row}"] = values[offset]
    return out


class _FakeJournalSheet:
    def __init__(self, cells=None, protected=()):
        self.cells = dict(cells or {})
        self.protected = set(protected)
        self.title = "777"
        self.updates = []

    def batch_get(self, ranges, value_render_option=None):
        blocks = []
        for ref in ranges:
            value = self.cells.get(ref, "")
            blocks.append([[value]] if value != "" else [[]])
        return blocks

    def batch_update(self, data, value_input_option=None):
        pending = []
        for item in data:
            ref = item["range"]
            expanded = _a1_cells(ref, item["values"][0])
            if any(cell in self.protected for cell in expanded):
                raise Exception(
                    "APIError: [400]: You are trying to edit a protected cell"
                )
            pending.append((expanded, value_input_option))
        for expanded, mode in pending:
            self.cells.update(expanded)
            self.updates.append((mode, expanded))


def test_validation_error_quotes_sheet_range_and_account():
    from vip_journal_sheets import _write_cells_resilient

    protected = _FakeJournalSheet(protected={"G5"})
    with pytest.raises(VipJournalError, match="protected") as caught:
        _write_cells_resilient(
            protected,
            5,
            {"G": 7.5, "F": 2.5},
            must_write={"G"},
            sheet_title="777",
            account="writer@example.com",
        )
    message = str(caught.value)
    assert "777" in message
    assert "F5:G5" in message
    assert "writer@example.com" in message
    assert "захищен" not in message
    assert "F5" not in protected.cells

    ok = _FakeJournalSheet()
    written = _write_cells_resilient(
        ok,
        6,
        {"F": 5.0, "G": 10.0, "L": "повний коментар"},
        must_write={"G", "L"},
        comment_letter="L",
    )
    assert written["G"] == 10.0
    assert ok.cells["G6"] == 10.0
    assert ok.cells["L6"] == "повний коментар"
    assert ok.cells["F6"] == 5.0
    assert ok.updates[-1][0] == "RAW"


def test_short_payload_rejects_comment_that_is_only_a_number():
    """Коментар «10» або «0,0» не може бути успішним payload: саме так 777 лишає дірки."""
    from datetime import date

    scores = {"contact": 5.0, "slip_handling": 0.0, "prep": 10.0, "closing": 2.5}
    for bare in ("10", "0,0", "0.0", "10/10"):
        with pytest.raises(VipJournalError, match="числом"):
            build_short_row_payload(
                client_id="6031394",
                call_date=date(2026, 11, 6),
                manager="Войтер Тетяна",
                tl="TL",
                scores=scores,
                check_date=date(2026, 11, 13),
                qa_comment=bare,
            )


def test_short_payload_keeps_zero_slip_and_full_comment():
    from datetime import date

    from vip_journal_sheets import build_journal_qa_comment, comment_is_bare_number

    note = "Клієнт просив не називати проєкт уголос, повний текст важливого."
    manual = "Месенджер до дзвінка, Viber. Номер підписаний — назва проєкту не обов'язкова."
    verdict = {
        "call_type": "vip_short_90s",
        "criteria": [
            {
                "key": "contact",
                "label": "Встановлення контакту",
                "points": 5,
                "max_points": 5,
                "reasons": ["Номер підписаний — назва проєкту не обов'язкова"],
            },
            {
                "key": "slip_handling",
                "label": "Робота зі «зливом» / утримання контакту",
                "points": 0,
                "max_points": 10,
                "reasons": ["Не зробив жодної дії з утримання контакту"],
            },
            {
                "key": "prep",
                "label": "Робота з запереченням (P.R.E.P.)",
                "points": 10,
                "max_points": 10,
                "reasons": [],
            },
            {
                "key": "closing",
                "label": "Завершення",
                "points": 2.5,
                "max_points": 5,
                "reasons": ["Відсутній елемент завершення: прощання"],
            },
        ],
    }
    comment = build_journal_qa_comment(
        {
            "journal_call_type": "short",
            "important_note": note,
            "qa_comment": manual,
        },
        verdict,
    )
    assert not comment_is_bare_number(comment)
    assert comment.strip() not in {"10", "0,0", "0.0", "10/10"}
    assert "Номер підписаний — назва проєкту не обов'язкова" in comment
    assert "Важливе: " + note in comment
    assert "Коментар до дзвінка: " + manual in comment
    assert "із 10" in comment
    assert "10/10" not in comment

    payload = build_short_row_payload(
        client_id="4632663",
        call_date=date(2026, 11, 5),
        manager="Войтер Тетяна",
        tl="TL",
        scores={"contact": 5.0, "slip_handling": 0.0, "prep": 10.0, "closing": 2.5},
        check_date=date(2026, 11, 13),
        qa_comment=comment,
    )
    assert payload["F"] == 5.0
    assert payload["G"] == 0.0
    assert payload["H"] == 10.0
    assert payload["I"] == 2.5
    assert "J" not in payload
    stored = str(payload["L"])
    assert not comment_is_bare_number(stored)
    assert stored.strip() not in {"10", "0,0", "0.0"}
    assert "Важливе: " + note in stored
    assert manual in stored
    assert "утримання контакту" in stored


def test_rectangles_never_include_status_or_formula():
    from vip_journal_sheets import plan_journal_rectangles

    short_payload = {
        "A": "'4632663",
        "B": "05.11.2026",
        "C": "Voiter I.",
        "D": "Ivan I.",
        "E": "Закрито",
        "F": 5,
        "G": 0.0,
        "H": 10,
        "I": 2.5,
        "J": "",
        "K": "АІ",
        "L": "— Злив: 0 із 10",
        "M": "13.11.2026",
    }
    spans = plan_journal_rectangles(
        short_payload, "short", existing=False, comment_letter="L"
    )
    letters = [col for span in spans for col in span["cols"]]
    assert letters == list("ABCD") + list("FGHI") + ["K", "L", "M"]
    assert {span["mode"] for span in spans if "L" in span["cols"]} == {"RAW"}
    existing = plan_journal_rectangles(
        short_payload, "short", existing=True, comment_letter="L"
    )
    assert [col for span in existing for col in span["cols"]] == list("FGHI") + ["K", "L", "M"]

    friendly = {
        "O": "'1",
        "P": "13.11.2026",
        "Q": "Voiter I.",
        "R": "Ivan I.",
        "S": "В роботі",
        "T": 5,
        "U": 2.5,
        "AA": 5,
        "AB": "",
        "AC": "АІ",
        "AD": "коментар",
        "AE": "13.11.2026",
    }
    new_friendly = plan_journal_rectangles(
        friendly, "friendly", existing=False, comment_letter="AD"
    )
    friendly_letters = [col for span in new_friendly for col in span["cols"]]
    assert friendly_letters[0:4] == list("OPQR")
    assert "S" not in friendly_letters
    assert "AB" not in friendly_letters
    assert friendly_letters[-3:] == ["AC", "AD", "AE"]
    scored = plan_journal_rectangles(
        friendly, "friendly", existing=True, comment_letter="AD"
    )
    scored_letters = [col for span in scored for col in span["cols"]]
    assert scored_letters[0] == "T"
    assert "O" not in scored_letters
    assert "AB" not in scored_letters


def test_missing_friendly_score_is_not_invented_as_zero():
    from datetime import date

    payload = build_friendly_row_payload(
        client_id="1",
        call_date=date(2026, 11, 13),
        manager="Voiter I.",
        tl="Ivan I.",
        scores={"contact": 5.0},
        check_date=date(2026, 11, 13),
        qa_comment="критерій без балу не стає нулем",
    )
    assert 0 not in payload.values()
    assert 0.0 not in payload.values()
    assert payload["T"] == 5.0
    assert "U" not in payload
    assert "AB" not in payload
    assert "S" not in payload


def test_manager_and_tl_keep_directory_spelling():
    row = resolve_manager_from_directory(
        [
            {
                "project": "777",
                "tl": "Ivan I.",
                "manager": "Voiter I.",
                "login": "voiter",
            }
        ],
        project_key="777",
        login="voiter",
    )
    assert row["manager"] == "Voiter I."
    assert row["tl"] == "Ivan I."


def test_same_client_on_two_rows_is_ambiguous():
    from datetime import date

    from vip_journal_sheets import match_journal_rows

    rows = match_journal_rows(
        ["", "", "4632663", "4632663"],
        ["", "", "05.11.2026", "05.11.2026"],
        ["", "", "Войтер Тетяна", "Войтер Тетяна"],
        client_id="'4632663",
        call_date=date(2026, 11, 5),
        manager="Войтер Тетяна",
        start_row=3,
    )
    assert rows == [3, 4]


def test_prefilled_formula_row_stays_free_until_call_data_exists():
    ids = ["", "", ""]
    assert find_next_journal_row(ids, start_row=3) == 3


def test_missing_total_formula_is_restored_alone():
    from vip_journal_sheets import ensure_total_formula

    sheet = _FakeJournalSheet()
    formula = ensure_total_formula(
        sheet, "short", 103, sheet_title="Vegas", account="writer@example.com"
    )
    assert formula == "=SUM(F103:I103)"
    assert sheet.cells["J103"] == "=SUM(F103:I103)"
    assert list(sheet.cells) == ["J103"]

    friendly = _FakeJournalSheet({"AB8": "=SUM(T8:AA8)"})
    kept = ensure_total_formula(
        friendly, "friendly", 8, sheet_title="Betking", account="writer@example.com"
    )
    assert kept == "=SUM(T8:AA8)"
    assert friendly.updates == []


def test_analysis_id_differs_for_different_cards():
    base = {
        "url": "https://same",
        "client_id": "1",
        "call_date": "01.09.2026",
        "check_date": "10.11.2026",
        "ret_manager": "A",
    }
    a = make_analysis_id({**base, "card_id": 1}, "short")
    b = make_analysis_id({**base, "card_id": 2}, "short")
    assert a != b
