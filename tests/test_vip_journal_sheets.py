"""16 сценаріїв запису журналу без мережі. Фікстури — рядки зі ТЗ 18.11.2026.

Повні клітинки 4493604 і 4642127 у цій машині не було. Відомі факти:
3093024 — у коментарі контакт 2.5/5, у F стоїть 5; 7490399 — френдлі з N/M.
"""

from __future__ import annotations

from datetime import date

import pytest

from vip_journal_sheets import (
    JOURNAL_LAYOUT,
    VipJournalError,
    audit_block,
    column_letter,
    column_number,
    date_to_serial,
    plan_safe_fixes,
    write_journal_call,
)

CALL_DATE = date(2026, 11, 5)
CHECK_DATE = date(2026, 11, 18)
MANAGERS = [
    ["Проєкт", "TL", "Менеджер", "Логін"],
    ["Betking", "Окороков Iван", "Головацький Назар", "nazar"],
    ["777", "Крисак Іван", "Клименко Артем", "artem"],
    ["Vegas", "Олег", "Вегас Менеджер", "vegas"],
    ["Betking", "Перший TL", "Подвійний", "duo"],
    ["Betking", "Другий TL", "Подвійний", "duo"],
]
SHORT_SCORES = {"contact": 5, "slip_handling": 10, "prep": 7.5, "closing": 2.5}
FRIENDLY_SCORES = {
    "contact": 5,
    "friendly_development": 7.5,
    "personal_approach": 5,
    "call_to_action": 10,
    "bonus_offer": 2.5,
    "prep": 7.5,
    "closing": 5,
    "ease": 2.5,
}


def _headers() -> dict[str, str]:
    headers = {}
    for block in JOURNAL_LAYOUT["blocks"].values():
        for column in block["columns"]:
            headers[column["letter"]] = column["header"]
    headers["G"] = "Робота менеджера зі «зливом»"
    headers["H"] = "Робота з негативом/заперечення P.R.E.P"
    headers["Y"] = "Робота з негативом/заперечення P.R.E.P"
    return headers


class _Worksheet:
    def __init__(self, book):
        self.title = book.route["title"]
        self.id = book.route["sheet_id"]
        self.row_count = book.row_count


class FakeBook:
    def __init__(self, project: str, row_count: int = 12):
        self.route = dict(JOURNAL_LAYOUT["projects"][project])
        self.row_count = row_count
        self.headers = _headers()
        self.cells: dict[tuple[int, str], object] = {}
        self.formulas: dict[tuple[int, str], str] = {}
        self.updates: list[dict] = []
        self.attempts: list[dict] = []
        self.reads: list[str] = []
        self.fail_writes = 0
        self.applied = False
        self.corrupt_comment = False
        self.id = "spreadsheet"

    def get_worksheet_by_id(self, sheet_id: int):
        assert int(sheet_id) == int(self.route["sheet_id"])
        return _Worksheet(self)

    def values_batch_get(self, ranges, params=None):
        render = (params or {}).get("valueRenderOption", "FORMATTED_VALUE")
        blocks = []
        for ref in ranges:
            self.reads.append(ref)
            blocks.append({"range": ref, "values": self._values(ref, render)})
        return {"valueRanges": blocks}

    def batch_update(self, body):
        self.attempts.append(body)
        if self.fail_writes:
            self.fail_writes -= 1
            raise RuntimeError("429 rate limit")
        for request in body.get("requests") or []:
            update = request["updateCells"]
            assert update["fields"] == "userEnteredValue"
            grid = update["range"]
            row = grid["startRowIndex"] + 1
            column = grid["startColumnIndex"]
            for cell in update["rows"][0]["values"]:
                letter = column_letter(column + 1)
                entered = cell["userEnteredValue"]
                if "formulaValue" in entered:
                    self.formulas[(row, letter)] = entered["formulaValue"]
                elif "stringValue" in entered:
                    self.cells[(row, letter)] = entered["stringValue"]
                elif "numberValue" in entered:
                    self.cells[(row, letter)] = entered["numberValue"]
                column += 1
        self.applied = True
        self.updates.append(body)

    def _values(self, ref: str, render: str) -> list[list]:
        _sheet, start, end = _parse_ref(ref)
        rows = []
        for row in range(start[1], end[1] + 1):
            line = []
            for number in range(column_number(start[0]), column_number(end[0]) + 1):
                letter = column_letter(number)
                if row == self.route["header_row"] and letter in self.headers and start[1] == self.route["header_row"]:
                    line.append(self.headers.get(letter, ""))
                    continue
                if render == "FORMULA" and (row, letter) in self.formulas:
                    line.append(self.formulas[(row, letter)])
                    continue
                value = self.cells.get((row, letter), "")
                if (
                    self.corrupt_comment
                    and self.applied
                    and letter in {"L", "AD"}
                    and value != ""
                ):
                    value = 10
                line.append(value)
            rows.append(line)
        return rows


class FakeClient:
    def __init__(self, book: FakeBook):
        self.book = book
        self.http = type("Http", (), {})()
        self.http.credentials = type("Creds", (), {"service_account_email": "writer@example.com"})()

    def open_by_key(self, _key):
        return self.book


def _parse_ref(ref: str):
    sheet, _, cells = ref.rpartition("!")
    sheet = sheet[1:-1].replace("''", "'") if sheet.startswith("'") else sheet
    start, _, end = cells.partition(":")

    def parse(token: str):
        letters = "".join(char for char in token if char.isalpha())
        row = int("".join(char for char in token if char.isdigit()))
        return letters, row

    return sheet, parse(start), parse(end or start)


def _client(project: str) -> tuple[FakeClient, FakeBook]:
    book = FakeBook(project)
    return FakeClient(book), book


def _write(project: str, call_type: str, client_id: str, scores: dict, **kwargs):
    client, book = _client(project)
    managers = kwargs.pop("managers", MANAGERS)
    result = write_journal_call(
        client,
        project=project,
        call_type=call_type,
        client_id=client_id,
        call_date=kwargs.pop("call_date", CALL_DATE),
        manager=kwargs.pop("manager", _manager_for(project)),
        scores=scores,
        check_date=kwargs.pop("check_date", CHECK_DATE),
        managers=parse_managers(managers),
        supabase=False,
        sleeper=kwargs.pop("sleeper", lambda _seconds: None),
        **kwargs,
    )
    return result, book


def parse_managers(rows):
    from vip_journal_sheets import parse_journal_managers

    return parse_journal_managers(rows)


def _manager_for(project: str) -> str:
    return {
        "betking": "Головацький Назар",
        "777": "Клименко Артем",
        "vegas": "Вегас Менеджер",
    }[project]


def _entered(book: FakeBook):
    found = []
    for body in book.updates:
        for request in body.get("requests") or []:
            grid = request["updateCells"]["range"]
            row = grid["startRowIndex"] + 1
            column = grid["startColumnIndex"]
            for cell in request["updateCells"]["rows"][0]["values"]:
                found.append((row, column_letter(column + 1), cell["userEnteredValue"]))
                column += 1
    return found


def test_01_new_short_betking_uses_row_3_and_skips_e_j_n():
    result, book = _write("betking", "short", "4493604", SHORT_SCORES)
    assert result["ok"] is True
    assert result["row"] == 3
    assert result["status"].startswith("Записано · Betking · рядок 3")
    letters = {letter for _row, letter, _value in _entered(book)}
    assert "E" not in letters
    assert "N" not in letters
    data_letters = {
        letter
        for _row, letter, value in _entered(book)
        if "formulaValue" not in value
    }
    assert "J" not in data_letters
    formula = [value for _row, letter, value in _entered(book) if letter == "J"]
    assert formula == [{"formulaValue": "=SUM(F3:I3)"}]
    tl = [value for _row, letter, value in _entered(book) if letter == "D"][0]
    assert tl == {"stringValue": "Окороков Iван"}
    assert "I" in tl["stringValue"] and "І" not in tl["stringValue"]


def test_02_new_friendly_vegas_row_5_has_tl():
    result, book = _write("vegas", "friendly", "7001001", FRIENDLY_SCORES)
    assert result["ok"] is True
    assert result["row"] == 5
    tl = [value for row, letter, value in _entered(book) if row == 5 and letter == "R"]
    assert tl == [{"stringValue": "Олег"}]


def test_03_friendly_uses_the_row_already_taken_by_short():
    client, book = _client("betking")
    book.cells[(3, "A")] = "4493604"
    book.cells[(3, "C")] = "Головацький Назар"
    book.cells[(3, "F")] = 5
    result = write_journal_call(
        client,
        project="betking",
        call_type="friendly",
        client_id="7001002",
        call_date=CALL_DATE,
        manager="Головацький Назар",
        scores=FRIENDLY_SCORES,
        check_date=CHECK_DATE,
        managers=parse_managers(MANAGERS),
        supabase=False,
        sleeper=lambda _seconds: None,
    )
    assert result["row"] == 3
    assert book.cells[(3, "A")] == "4493604"
    assert book.cells[(3, "F")] == 5
    assert book.cells[(3, "O")] == "7001002"
    short_letters = {
        letter
        for _row, letter, _value in _entered(book)
        if column_number(letter) < column_number("O")
    }
    assert not short_letters


def test_04_formula_and_reviewer_do_not_occupy_a_row():
    client, book = _client("betking")
    book.formulas[(3, "J")] = "=SUM(F3:I3)"
    book.cells[(3, "K")] = "АІ"
    result = write_journal_call(
        client,
        project="betking",
        call_type="short",
        client_id="4493604",
        call_date=CALL_DATE,
        manager="Головацький Назар",
        scores=SHORT_SCORES,
        check_date=CHECK_DATE,
        managers=parse_managers(MANAGERS),
        supabase=False,
        sleeper=lambda _seconds: None,
    )
    assert result["row"] == 3
    assert book.cells[(3, "A")] == "4493604"
    assert book.formulas[(3, "J")] == "=SUM(F3:I3)"


def test_05_leading_zero_id_stays_text():
    _result, book = _write("betking", "short", "048284", SHORT_SCORES)
    stored = [value for _row, letter, value in _entered(book) if letter == "A"]
    assert stored == [{"stringValue": "048284"}]
    assert book.cells[(3, "A")] == "048284"


def test_06_slash_comment_is_rejected_and_iz_stays_text():
    client, book = _client("777")
    with pytest.raises(VipJournalError, match="N/M"):
        write_journal_call(
            client,
            project="777",
            call_type="friendly",
            client_id="7490399",
            call_date=CALL_DATE,
            manager="Клименко Артем",
            scores=FRIENDLY_SCORES,
            reasons={"contact": "було 2.5/5"},
            check_date=CHECK_DATE,
            managers=parse_managers(MANAGERS),
            supabase=False,
            sleeper=lambda _seconds: None,
        )
    assert book.updates == []
    result, clean = _write("777", "short", "4642127", {"contact": 2.5, "slip_handling": 0, "prep": 5, "closing": 2.5})
    assert result["ok"] is True
    comment = [value for _row, letter, value in _entered(clean) if letter == "L"][0]
    assert "stringValue" in comment
    assert "2,5 із 5" in comment["stringValue"]
    assert "/" not in comment["stringValue"]
    assert comment["stringValue"] == clean.cells[(3, "L")]


def test_07_missing_score_is_not_written_as_zero():
    scores = dict(SHORT_SCORES)
    scores["prep"] = None
    result, book = _write("betking", "short", "4493604", scores)
    assert result["ok"] is True
    assert result["status"].startswith("Неповні бали · рядок 3")
    assert "P.R.E.P" in result["status"]
    assert all(letter != "H" for _row, letter, _value in _entered(book))
    comment = book.cells[(3, "L")]
    assert "P.R.E.P: не оцінено" in comment
    assert "P.R.E.P: 0 із" not in comment


def test_08_seven_and_half_is_not_allowed_in_call_to_action():
    client, book = _client("vegas")
    scores = dict(FRIENDLY_SCORES)
    scores["call_to_action"] = 7.5
    with pytest.raises(VipJournalError, match="call_to_action"):
        write_journal_call(
            client,
            project="vegas",
            call_type="friendly",
            client_id="7001003",
            call_date=CALL_DATE,
            manager="Вегас Менеджер",
            scores=scores,
            check_date=CHECK_DATE,
            managers=parse_managers(MANAGERS),
            supabase=False,
            sleeper=lambda _seconds: None,
        )
    assert book.updates == []


def test_09_existing_score_conflict_writes_nothing():
    result, book = _write("vegas", "short", "3093024", SHORT_SCORES)
    assert result["ok"] is True
    book.updates.clear()
    scores = dict(SHORT_SCORES)
    scores["contact"] = 2.5
    again = write_journal_call(
        FakeClient(book),
        project="vegas",
        call_type="short",
        client_id="3093024",
        call_date=CALL_DATE,
        manager="Вегас Менеджер",
        scores=scores,
        check_date=CHECK_DATE,
        managers=parse_managers(MANAGERS),
        supabase=False,
        sleeper=lambda _seconds: None,
    )
    assert again["ok"] is False
    assert again["status"].startswith("Конфлікт · рядок 5")
    assert "2.5" in again["error"] or "2,5" in again["error"]
    assert book.updates == []
    assert book.cells[(5, "F")] == 5


def test_09b_empty_scores_are_stored_when_one_score_disagrees():
    client, book = _client("vegas")
    book.cells[(5, "A")] = "3093024"
    book.cells[(5, "B")] = date_to_serial(CALL_DATE)
    book.cells[(5, "C")] = "Вегас Менеджер"
    book.cells[(5, "F")] = 5
    scores = dict(SHORT_SCORES)
    scores["contact"] = 2.5
    result = write_journal_call(
        client,
        project="vegas",
        call_type="short",
        client_id="3093024",
        call_date=CALL_DATE,
        manager="Вегас Менеджер",
        scores=scores,
        check_date=CHECK_DATE,
        managers=parse_managers(MANAGERS),
        supabase=False,
        sleeper=lambda _seconds: None,
    )
    assert result["ok"] is True
    assert result["status"].startswith("Дописано · рядок 5")
    assert "F" in result["status"]
    letters = {letter for _row, letter, _value in _entered(book)}
    assert "F" not in letters
    assert {"G", "H", "I"} <= letters
    assert "E" not in letters
    assert book.cells[(5, "F")] == 5
    assert book.cells[(5, "G")] == 10


def test_10_matching_row_makes_no_write_request():
    result, book = _write("betking", "short", "4493604", SHORT_SCORES)
    assert result["ok"] is True
    book.updates.clear()
    book.attempts.clear()
    again = write_journal_call(
        FakeClient(book),
        project="betking",
        call_type="short",
        client_id="4493604",
        call_date=CALL_DATE,
        manager="Головацький Назар",
        scores=SHORT_SCORES,
        check_date=CHECK_DATE,
        managers=parse_managers(MANAGERS),
        supabase=False,
        sleeper=lambda _seconds: None,
    )
    assert again["status"].startswith("Вже записано · рядок 3")
    assert book.updates == []
    assert book.attempts == []


def test_11_two_rows_with_the_same_key_are_ambiguous():
    client, book = _client("betking")
    for row in (3, 4):
        book.cells[(row, "A")] = "4493604"
        book.cells[(row, "B")] = date_to_serial(CALL_DATE)
        book.cells[(row, "C")] = "Головацький Назар"
    result = write_journal_call(
        client,
        project="betking",
        call_type="short",
        client_id="4493604",
        call_date=CALL_DATE,
        manager="Головацький Назар",
        scores=SHORT_SCORES,
        check_date=CHECK_DATE,
        managers=parse_managers(MANAGERS),
        supabase=False,
        sleeper=lambda _seconds: None,
    )
    assert result["ok"] is False
    assert "Неоднозначно" in result["status"]
    assert "3" in result["status"] and "4" in result["status"]
    assert book.updates == []


def test_12_failed_verification_does_not_use_the_next_row():
    client, book = _client("betking")
    book.corrupt_comment = True
    result = write_journal_call(
        client,
        project="betking",
        call_type="short",
        client_id="4493604",
        call_date=CALL_DATE,
        manager="Головацький Назар",
        scores=SHORT_SCORES,
        check_date=CHECK_DATE,
        managers=parse_managers(MANAGERS),
        supabase=False,
        sleeper=lambda _seconds: None,
    )
    assert result["status"] == "Помилка перевірки"
    rows = {grid_row for body in book.updates for grid_row in _rows(body)}
    assert rows == {3}
    assert 4 not in rows


def test_13_rate_limit_retries_the_same_row():
    client, book = _client("777")
    book.fail_writes = 1
    slept = []
    result = write_journal_call(
        client,
        project="777",
        call_type="short",
        client_id="4642127",
        call_date=CALL_DATE,
        manager="Клименко Артем",
        scores=SHORT_SCORES,
        check_date=CHECK_DATE,
        managers=parse_managers(MANAGERS),
        supabase=False,
        sleeper=slept.append,
    )
    assert result["ok"] is True
    assert result["row"] == 3
    assert slept == [1]
    assert len(book.attempts) >= 2
    assert _rows(book.attempts[0]) == _rows(book.attempts[1]) == {3}


def test_14_changed_header_writes_nothing():
    client, book = _client("betking")
    book.headers["H"] = "Змінено"
    with pytest.raises(VipJournalError, match="Структура аркуша змінилась"):
        write_journal_call(
            client,
            project="betking",
            call_type="short",
            client_id="4493604",
            call_date=CALL_DATE,
            manager="Головацький Назар",
            scores=SHORT_SCORES,
            check_date=CHECK_DATE,
            managers=parse_managers(MANAGERS),
            supabase=False,
            sleeper=lambda _seconds: None,
        )
    message = ""
    try:
        write_journal_call(
            client,
            project="betking",
            call_type="short",
            client_id="4493604",
            call_date=CALL_DATE,
            manager="Головацький Назар",
            scores=SHORT_SCORES,
            check_date=CHECK_DATE,
            managers=parse_managers(MANAGERS),
            supabase=False,
            sleeper=lambda _seconds: None,
        )
    except VipJournalError as exc:
        message = str(exc)
    assert "очікувалось P.R.E.P у колонці H" in message
    assert "Змінено" in message
    assert book.updates == []


def test_15_sheet_777_ranges_are_quoted():
    result, book = _write("777", "short", "4642127", SHORT_SCORES)
    assert result["ok"] is True
    assert book.reads
    assert all(ref.startswith("'777'!") for ref in book.reads)
    assert not any(ref.startswith("777!") for ref in book.reads)


def test_16_duplicate_or_missing_manager_writes_nothing():
    client, book = _client("betking")
    with pytest.raises(VipJournalError, match="Неоднозначний менеджер"):
        write_journal_call(
            client,
            project="betking",
            call_type="short",
            client_id="4493604",
            call_date=CALL_DATE,
            manager="Подвійний",
            scores=SHORT_SCORES,
            check_date=CHECK_DATE,
            managers=parse_managers(MANAGERS),
            supabase=False,
            sleeper=lambda _seconds: None,
        )
    with pytest.raises(VipJournalError, match="не знайдено"):
        write_journal_call(
            client,
            project="vegas",
            call_type="short",
            client_id="3093024",
            call_date=CALL_DATE,
            manager="Немає Такого",
            scores=SHORT_SCORES,
            check_date=CHECK_DATE,
            managers=parse_managers(MANAGERS),
            supabase=False,
            sleeper=lambda _seconds: None,
        )
    assert book.updates == []


def test_audit_flags_the_known_mismatch_and_plans_only_safe_fixes():
    route = JOURNAL_LAYOUT["projects"]["vegas"]
    rows = [
        {
            "A": "3093024",
            "B": date_to_serial(CALL_DATE),
            "C": "Вегас Менеджер",
            "D": "",
            "F": 5,
            "J": "",
            "L": "контакт 2.5/5",
        }
    ]
    issues = audit_block(
        sheet_title="Vegas",
        call_type="short",
        rows=rows,
        start_row=route["start_row"],
        directory=parse_managers(MANAGERS),
        project_key="vegas",
    )
    kinds = {item["issue"] for item in issues}
    assert "порожній TL" in kinds
    assert "коментар містить N/M" in kinds
    assert "бал у клітинці не збігається з коментарем" in kinds
    plans = plan_safe_fixes(
        sheet_title="Vegas",
        call_type="short",
        rows=rows,
        start_row=route["start_row"],
        directory=parse_managers(MANAGERS),
        project_key="vegas",
        sheet_id=route["sheet_id"],
    )
    assert [plan["letter"] for plan in plans] == ["D"]
    assert plans[0]["value"] == "Олег"
    matching = [dict(rows[0]), {"A": "1", "C": "Вегас Менеджер", "D": "Олег", "F": 2.5, "L": "контакт 2.5/5", "J": "=SUM(F6:I6)"}]
    safe = plan_safe_fixes(
        sheet_title="Vegas",
        call_type="short",
        rows=matching,
        start_row=6,
        directory=parse_managers(MANAGERS),
        project_key="vegas",
        sheet_id=route["sheet_id"],
    )
    comments = [plan for plan in safe if plan["letter"] == "L"]
    assert comments and comments[0]["value"] == "контакт 2,5 із 5"


def _rows(body: dict) -> set[int]:
    return {request["updateCells"]["range"]["startRowIndex"] + 1 for request in body.get("requests") or []}


def test_friendly_scores_land_in_o_ae_and_skip_s_ab():
    for project, row in (("777", 3), ("betking", 3), ("vegas", 5)):
        result, book = _write(project, "friendly", "7340116", FRIENDLY_SCORES)
        assert result["ok"] is True
        assert result["row"] == row
        letters = {letter for _row, letter, _value in _entered(book)}
        assert {"O", "T", "U", "V", "W", "X", "Y", "Z", "AA", "AE"} <= letters
        assert "S" not in letters
        ab = [value for _row, letter, value in _entered(book) if letter == "AB"]
        assert ab == [{"formulaValue": f"=SUM(T{row}:AA{row})"}]
        assert book.cells[(row, "T")] == 5
        assert book.cells[(row, "W")] == 10
        assert book.cells[(row, "AA")] == 2.5


def test_friendly_keeps_a_disagreeing_score_and_fills_the_rest():
    client, book = _client("777")
    book.cells[(3, "O")] = "7340116"
    book.cells[(3, "P")] = date_to_serial(CALL_DATE)
    book.cells[(3, "Q")] = "Клименко Артем"
    book.cells[(3, "U")] = 5
    result = write_journal_call(
        client,
        project="777",
        call_type="friendly",
        client_id="7340116",
        call_date=CALL_DATE,
        manager="Клименко Артем",
        scores=FRIENDLY_SCORES,
        check_date=CHECK_DATE,
        managers=parse_managers(MANAGERS),
        supabase=False,
        sleeper=lambda _seconds: None,
    )
    assert result["ok"] is True
    letters = {letter for _row, letter, _value in _entered(book)}
    assert "U" not in letters
    assert "S" not in letters
    assert {"T", "V", "W", "X", "Y", "Z", "AA"} <= letters
    assert book.cells[(3, "U")] == 5
    assert book.cells[(3, "T")] == 5
    ab = [value for _row, letter, value in _entered(book) if letter == "AB"]
    assert all("formulaValue" in value for value in ab)


def test_other_conversation_for_same_client_does_not_block_the_write():
    same = {
        "id": "98970b39-1111-4111-8111-111111111111",
        "client_id": "4493604",
        "call_date": CALL_DATE.isoformat(),
        "ret_manager": "Головацький Назар",
        "call_type": "short",
        "created_at": "2026-11-18T12:00:00+00:00",
        "row_ref": "3",
        "criteria_scores": [
            {"key": key, "points": value} for key, value in SHORT_SCORES.items()
        ],
        "gpt_transcript": "Клієнт: Юрій",
    }
    other = {
        "id": "71ff5601-2222-4222-8222-222222222222",
        "client_id": "4493604",
        "call_date": CALL_DATE.isoformat(),
        "ret_manager": "Головацький Назар",
        "call_type": "short",
        "created_at": "2026-11-18T08:00:00+00:00",
        "row_ref": "40",
        "criteria_scores": [
            {"key": "contact", "points": 0},
            {"key": "slip_handling", "points": 0},
            {"key": "prep", "points": 0},
            {"key": "closing", "points": 0},
        ],
        "gpt_transcript": "Клієнт: Віталій",
    }
    result, book = _write(
        "betking",
        "short",
        "4493604",
        SHORT_SCORES,
        prior_analyses=[other, same],
    )
    assert result["ok"] is True
    assert result["status"] != "Два аналізи розходяться"
    assert book.cells[(3, "F")] == 5
