"""Запис оцінок VIP у журнал Betking / 777 / Vegas.

Один модуль, фіксовані колонки `JOURNAL_LAYOUT`. Заголовки лише звіряються
перед записом і не змінюють літери. Успіх лише після повторного читання.
Наступний рядок після невдалої перевірки не використовується.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from constants import (
    CALL_TYPE_FRIENDLY,
    CALL_TYPE_KEY_FRIENDLY,
    CALL_TYPE_KEY_SHORT,
    CALL_TYPE_SHORT_90S,
    VIP_JOURNAL_CALL_TYPE_FRIENDLY,
    VIP_JOURNAL_CALL_TYPE_SHORT,
    VIP_JOURNAL_MANAGERS_WORKSHEET,
    VIP_JOURNAL_REVIEWER,
    VIP_JOURNAL_SHEET_ID,
    VIP_JOURNAL_TZ,
    resolve_call_type_key,
)
from google_sheets import clean_sheet_cell

logger = logging.getLogger(__name__)

_SHEETS_EPOCH = date(1899, 12, 30)
_RATIO_RE = re.compile(r"\d\s*[/⁄∕／]\s*\d")
_BACKOFF_SECONDS = (1, 3, 9)
_LOCK_TTL = timedelta(seconds=60)
_READ_ONLY_SHEETS = frozenset({"Гайди", "Менеджери VIP", "Зведення", "Правки"})
_NEVER_WRITE = frozenset({"E", "J", "N", "S", "AB"})
_PROCESS_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_PROCESS_GUARD = threading.Lock()
_DEDUP_PATH = Path(__file__).resolve().parent / ".cache" / "vip_journal_writes.json"


def _col(letter: str, field: str, header: str, *, write: bool, kind: str, allowed: tuple[float, ...] = (), keyword: str = "") -> dict[str, Any]:
    return {
        "letter": letter,
        "field": field,
        "header": header,
        "write": write,
        "kind": kind,
        "allowed": allowed,
        "keyword": keyword,
    }


# Літери зашиті тут. Пошук колонки по тексту заголовка для запису не використовується.
JOURNAL_LAYOUT: dict[str, Any] = {
    "spreadsheet_id": VIP_JOURNAL_SHEET_ID,
    "projects": {
        "betking": {"title": "Betking", "sheet_id": 445201819, "header_row": 2, "start_row": 3},
        "777": {"title": "777", "sheet_id": 1229042759, "header_row": 2, "start_row": 3},
        "vegas": {"title": "Vegas", "sheet_id": 1070088770, "header_row": 4, "start_row": 5},
    },
    "blocks": {
        "short": {
            "start": "A",
            "end": "M",
            "formula": {"letter": "J", "template": "=SUM(F{row}:I{row})"},
            "ignore_when_free": ("J", "K"),
            "score_letters": ("F", "G", "H", "I"),
            "columns": (
                _col("A", "client_id", "ID клієнта", write=True, kind="text", keyword="клієнта"),
                _col("B", "call_date", "Дата дзвінка", write=True, kind="date", keyword="дата дзвінка"),
                _col("C", "manager", "Менеджер VIP", write=True, kind="text", keyword="менеджер"),
                _col("D", "tl", "TL", write=True, kind="text", keyword="tl"),
                _col("E", "tl_status", "Статус від TL", write=False, kind="skip", keyword="статус"),
                _col("F", "contact", "Встановлення контакту", write=True, kind="score", allowed=(0, 2.5, 5), keyword="контакту"),
                _col("G", "slip_handling", "Робота зі «зливом»", write=True, kind="score", allowed=(0, 2.5, 5, 7.5, 10), keyword="злив"),
                _col("H", "prep", "P.R.E.P", write=True, kind="score", allowed=(0, 2.5, 5, 7.5, 10), keyword="p.r.e.p"),
                _col("I", "closing", "Завершення", write=True, kind="score", allowed=(0, 2.5, 5), keyword="завершен"),
                _col("J", "total", "Бал за дзвінок", write=False, kind="formula", keyword="бал за дзвінок"),
                _col("K", "reviewer", "Перевіряючий", write=True, kind="text", keyword="перевіря"),
                _col("L", "comment", "Коментар QA", write=True, kind="text", keyword="коментар"),
                _col("M", "check_date", "Дата перевірки", write=True, kind="date", keyword="дата перевірки"),
            ),
        },
        "friendly": {
            "start": "O",
            "end": "AE",
            "formula": {"letter": "AB", "template": "=SUM(T{row}:AA{row})"},
            "ignore_when_free": ("AB", "AC"),
            "score_letters": ("T", "U", "V", "W", "X", "Y", "Z", "AA"),
            "columns": (
                _col("O", "client_id", "ID клієнта", write=True, kind="text", keyword="клієнта"),
                _col("P", "call_date", "Дата дзвінка", write=True, kind="date", keyword="дата дзвінка"),
                _col("Q", "manager", "Менеджер VIP", write=True, kind="text", keyword="менеджер"),
                _col("R", "tl", "TL", write=True, kind="text", keyword="tl"),
                _col("S", "tl_status", "Статус від TL", write=False, kind="skip", keyword="статус"),
                _col("T", "contact", "Встановлення контакту", write=True, kind="score", allowed=(0, 2.5, 5), keyword="контакту"),
                _col("U", "friendly_development", "Розвиток френдлі", write=True, kind="score", allowed=(0, 2.5, 5, 7.5), keyword="френдлі"),
                _col("V", "personal_approach", "Індивідуальний підхід", write=True, kind="score", allowed=(0, 2.5, 5, 7.5), keyword="підхід"),
                _col("W", "call_to_action", "Заклик до гри", write=True, kind="score", allowed=(0, 2.5, 5, 10), keyword="заклик"),
                _col("X", "bonus_offer", "Пропозиція бонусів", write=True, kind="score", allowed=(0, 2.5, 5), keyword="бонус"),
                _col("Y", "prep", "P.R.E.P", write=True, kind="score", allowed=(0, 2.5, 5, 7.5, 10), keyword="p.r.e.p"),
                _col("Z", "closing", "Завершення", write=True, kind="score", allowed=(0, 2.5, 5), keyword="завершен"),
                _col("AA", "ease", "Невимушеність", write=True, kind="score", allowed=(0, 2.5, 5, 7.5), keyword="невимуш"),
                _col("AB", "total", "Бал за дзвінок", write=False, kind="formula", keyword="бал за дзвінок"),
                _col("AC", "reviewer", "Перевіряючий", write=True, kind="text", keyword="перевіря"),
                _col("AD", "comment", "Коментар QA", write=True, kind="text", keyword="коментар"),
                _col("AE", "check_date", "Дата перевірки", write=True, kind="date", keyword="дата перевірки"),
            ),
        },
    },
}


class VipJournalError(ValueError):
    """Запис не робився або його перевірка не зійшлась."""


def quote_sheet_name(title: str) -> str:
    """A1-назва. 777 завжди в лапках: '777'!A3."""
    return "'" + str(title or "").replace("'", "''") + "'"


def qualified_range(title: str, ref: str) -> str:
    local = str(ref).split("!")[-1]
    return f"{quote_sheet_name(title)}!{local}"


def column_number(letter: str) -> int:
    number = 0
    for char in str(letter or "").upper():
        number = number * 26 + (ord(char) - 64)
    return number


def column_letter(number: int) -> str:
    letters = ""
    value = int(number)
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def date_to_serial(value: date) -> int:
    """Серійна дата Google Sheets: дні від 30.12.1899."""
    return (value - _SHEETS_EPOCH).days


def serial_to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _SHEETS_EPOCH + timedelta(days=int(round(float(value))))
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return _SHEETS_EPOCH + timedelta(days=int(round(float(text.replace(",", ".")))))
    except ValueError:
        return None


def normalize_header(value: Any) -> str:
    text = clean_sheet_cell(value).casefold().replace("ё", "е")
    for char in "«»“”„\"'`ʼ":
        text = text.replace(char, "")
    text = text.replace(".", "")
    return re.sub(r"\s+", " ", text).strip()


def header_matches(actual: Any, column: dict[str, Any]) -> bool:
    """Заголовок збігається з полем колонки. Інша літера через це не обирається."""
    got = normalize_header(actual)
    expected = normalize_header(column["header"])
    if got == expected:
        return True
    keyword = normalize_header(column.get("keyword") or "")
    if not keyword or not got:
        return False
    # Короткі позначки («TL») лише цілком: «Статус від TL» не є колонкою TL.
    if len(keyword) <= 3:
        return got == keyword
    return keyword in got


def block_layout(call_type: str) -> dict[str, Any]:
    block = JOURNAL_LAYOUT["blocks"].get(call_type)
    if not block:
        raise VipJournalError("Невідомий тип дзвінка. Очікується short або friendly.")
    return block


def project_layout(project: str | None) -> dict[str, Any]:
    key = normalize_project_key(project)
    route = JOURNAL_LAYOUT["projects"].get(key or "")
    if not route:
        raise VipJournalError(
            f"Невідомий проєкт для журналу: {project!r}. Очікується betking / 777 / vegas."
        )
    return {"key": key, **route}


def normalize_project_key(project: str | None) -> str | None:
    text = clean_sheet_cell(project).casefold().replace(" ", "")
    aliases = {
        "betking": "betking",
        "беткінг": "betking",
        "беткинг": "betking",
        "777": "777",
        "vegas": "vegas",
        "вегас": "vegas",
    }
    return aliases.get(text)


def resolve_project_route(project: str | None) -> dict:
    route = project_layout(project)
    return {
        "key": route["key"],
        "title": route["title"],
        "sheet_id": route["sheet_id"],
        "start_row": route["start_row"],
        "header_row": route["header_row"],
    }


def resolve_journal_call_type(value: str | None) -> str | None:
    raw = str(value or "").strip().casefold()
    if raw in {VIP_JOURNAL_CALL_TYPE_SHORT, "короткий", "vip_short_90s"}:
        return VIP_JOURNAL_CALL_TYPE_SHORT
    if raw in {VIP_JOURNAL_CALL_TYPE_FRIENDLY, "френдлі", "friendly", "vip_friendly"}:
        return VIP_JOURNAL_CALL_TYPE_FRIENDLY
    key = resolve_call_type_key(value)
    if key == CALL_TYPE_KEY_SHORT:
        return VIP_JOURNAL_CALL_TYPE_SHORT
    if key == CALL_TYPE_KEY_FRIENDLY:
        return VIP_JOURNAL_CALL_TYPE_FRIENDLY
    if value in (CALL_TYPE_SHORT_90S, CALL_TYPE_FRIENDLY):
        return VIP_JOURNAL_CALL_TYPE_FRIENDLY if value == CALL_TYPE_FRIENDLY else VIP_JOURNAL_CALL_TYPE_SHORT
    return None


def make_analysis_id(call: dict, call_type: str) -> str:
    payload = "|".join(
        [
            str(call.get("url") or "").strip(),
            str(call.get("client_id") or "").strip(),
            str(call.get("call_date") or "").strip(),
            str(call_type or "").strip(),
            str(call.get("check_date") or call.get("listen_date") or "").strip(),
            str(call.get("ret_manager") or call.get("manager") or "").strip(),
            str(call.get("card_id") or call.get("_card_id") or "").strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def parse_journal_managers(values: list[list]) -> list[dict]:
    """A=проєкт, B=TL, C=менеджер, D=логін. Аркуш лише читається."""
    rows = []
    started = False
    for raw in values or []:
        cells = [clean_sheet_cell(cell) for cell in list(raw or [])[:4]]
        if not any(cells):
            continue
        low = [cell.casefold() for cell in cells]
        if not started and (
            "проєкт" in low[0]
            or "проект" in low[0]
            or low[0] in {"project", "a"}
            or (len(low) > 2 and low[2] in {"менеджер", "manager"})
        ):
            started = True
            continue
        started = True
        project, tl, manager, login = (cells + ["", "", "", ""])[:4]
        if not manager:
            continue
        rows.append({"project": project, "tl": tl, "manager": manager, "login": login})
    return rows


def load_journal_managers(google_client, spreadsheet_id: str | None = None) -> list[dict]:
    sheet_id = spreadsheet_id or VIP_JOURNAL_SHEET_ID
    worksheet = google_client.open_by_key(sheet_id).worksheet(VIP_JOURNAL_MANAGERS_WORKSHEET)
    values = worksheet.get_all_values()
    return parse_journal_managers(values)


def resolve_manager_from_directory(
    managers: list[dict],
    *,
    project_key: str,
    manager_name: str = "",
    login: str = "",
) -> dict:
    """Один збіг за проєктом і логіном або точним ім'ям. 0 або більше одного — помилка."""
    pool = []
    title = JOURNAL_LAYOUT["projects"][project_key]["title"]
    for row in managers or []:
        row_key = normalize_project_key(row.get("project"))
        raw = clean_sheet_cell(row.get("project")).casefold()
        if row_key == project_key or raw in {project_key, title.casefold()}:
            pool.append(row)
    login_norm = clean_sheet_cell(login)
    name_exact = clean_sheet_cell(manager_name)
    matches: list[dict] = []
    if login_norm:
        matches = [row for row in pool if clean_sheet_cell(row.get("login")) == login_norm]
    if not matches and name_exact:
        matches = [row for row in pool if clean_sheet_cell(row.get("manager")) == name_exact]
    if len(matches) != 1:
        if not matches:
            raise VipJournalError(
                f"Менеджера не знайдено в «{VIP_JOURNAL_MANAGERS_WORKSHEET}» "
                f"(проєкт={project_key}, login={login!r}, name={manager_name!r})."
            )
        raise VipJournalError(
            f"Неоднозначний менеджер у довіднику (проєкт={project_key}, "
            f"login={login!r}, name={manager_name!r}): {len(matches)} збіги."
        )
    found = matches[0]
    if not clean_sheet_cell(found.get("tl")):
        raise VipJournalError(
            f"У «{VIP_JOURNAL_MANAGERS_WORKSHEET}» немає TL для {found.get('manager')!r}."
        )
    return {
        "project": found.get("project") or "",
        "tl": clean_sheet_cell(found.get("tl")),
        "manager": clean_sheet_cell(found.get("manager")),
        "login": clean_sheet_cell(found.get("login")),
    }


def _parse_ua_date(value: str | date | datetime | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = serial_to_date(value)
    if parsed is None:
        raise VipJournalError(f"Некоректна дата: {value!r}")
    return parsed


def journal_today() -> date:
    return datetime.now(ZoneInfo(VIP_JOURNAL_TZ)).date()


def _canonical_score(field: str, value: Any, allowed: tuple[float, ...]) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise VipJournalError(f"Недопустимий бал {field}={value!r}.") from exc
    for candidate in allowed:
        if abs(number - candidate) < 1e-9:
            return float(candidate)
    allowed_text = ", ".join(str(item).replace(".", ",") for item in allowed)
    raise VipJournalError(f"Недопустимий бал {field}={number:g}. Дозволено: {allowed_text}.")


def validate_scores(call_type: str, scores: dict[str, Any] | None) -> dict[str, float | None]:
    block = block_layout(call_type)
    incoming = dict(scores or {})
    checked: dict[str, float | None] = {}
    for column in block["columns"]:
        if column["kind"] != "score":
            continue
        checked[column["field"]] = _canonical_score(
            column["field"], incoming.get(column["field"]), column["allowed"]
        )
    return checked


def format_points(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.1f}".replace(".", ",")


def build_comment_from_scores(
    call_type: str,
    scores: dict[str, float | None],
    reasons: dict[str, str] | None = None,
) -> str:
    """Той самий словник балів, що йде в клітинки. None — «не оцінено», не «0 із N»."""
    lines = []
    notes = reasons or {}
    for column in block_layout(call_type)["columns"]:
        if column["kind"] != "score":
            continue
        label = column["header"]
        value = scores.get(column["field"])
        if value is None:
            lines.append(f"— {label}: не оцінено")
            continue
        maximum = max(column["allowed"])
        line = f"— {label}: {format_points(value)} із {format_points(maximum)}"
        reason = clean_sheet_cell(notes.get(column["field"]))
        if reason:
            line += f" ({reason})"
        lines.append(line)
    text = "\n".join(lines).strip()
    if _RATIO_RE.search(text):
        raise VipJournalError("Коментар містить дріб N/M. Запис не робимо.")
    return text


def comment_has_ratio(value: Any) -> bool:
    return bool(_RATIO_RE.search(str(value if value is not None else "")))


def _cell_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _same_number(left: Any, right: float) -> bool:
    if isinstance(left, bool) or left is None or isinstance(left, str):
        return False
    try:
        return abs(float(left) - float(right)) < 1e-9
    except (TypeError, ValueError):
        return False


def _id_text(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    if text.startswith("'"):
        text = text[1:]
    if isinstance(value, float) and abs(value - round(value)) < 1e-9:
        text = str(int(round(value)))
    return text.strip()


def _row_map(values: list, start_letter: str) -> dict[str, Any]:
    start = column_number(start_letter)
    mapped: dict[str, Any] = {}
    for offset, value in enumerate(values or []):
        mapped[column_letter(start + offset)] = value
    return mapped


def _writer_account(google_client) -> str:
    holders = [google_client, getattr(google_client, "http", None), getattr(google_client, "auth", None)]
    for holder in holders:
        creds = getattr(holder, "credentials", None) if holder is not None else None
        email = getattr(creds, "service_account_email", None) or getattr(creds, "signer_email", None)
        if email:
            return str(email)
    return "невідомий обліковий запис"


def _public_error(exc: BaseException) -> str:
    text = str(exc)
    text = re.sub(r"ya29\.[A-Za-z0-9_\-]+", "[token]", text)
    text = re.sub(r"Bearer\s+\S+", "Bearer [token]", text, flags=re.IGNORECASE)
    text = re.sub(r"private_key['\"]?\s*[:=].*", "private_key [hidden]", text)
    return text


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, VipJournalError):
        return False
    code = getattr(getattr(exc, "response", None), "status_code", None)
    if code in {429, 500, 502, 503, 504}:
        return True
    text = str(exc).lower()
    return any(token in text for token in ("429", "500", "502", "503", "504", "timeout", "unavailable"))


def _values_batch(book, ranges: list[str], render: str) -> list[list[list]]:
    response = book.values_batch_get(
        ranges,
        params={"valueRenderOption": render, "majorDimension": "ROWS"},
    )
    blocks = response.get("valueRanges", response) if isinstance(response, dict) else response
    rows = []
    for block in blocks or []:
        if isinstance(block, dict):
            rows.append(block.get("values") or [])
        else:
            rows.append(block or [])
    return rows


def _open_book(google_client):
    return google_client.open_by_key(VIP_JOURNAL_SHEET_ID)


def _worksheet(book, route: dict):
    worksheet = book.get_worksheet_by_id(int(route["sheet_id"]))
    title = str(getattr(worksheet, "title", "") or route["title"])
    if title in _READ_ONLY_SHEETS:
        raise VipJournalError(f"Аркуш {title} не записується.")
    return worksheet


def _read_headers_and_block(book, route: dict, call_type: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    block = block_layout(call_type)
    title = route["title"]
    header_ref = qualified_range(title, f"A{route['header_row']}:AE{route['header_row']}")
    data_ref = qualified_range(
        title,
        f"{block['start']}{route['start_row']}:{block['end']}{int(route['row_count'])}",
    )
    header_rows, data_rows = _values_batch(book, [header_ref, data_ref], "UNFORMATTED_VALUE")
    headers = _row_map(header_rows[0] if header_rows else [], "A")
    mapped = [_row_map(row, block["start"]) for row in data_rows]
    return headers, mapped


def _check_headers(headers: dict[str, Any], call_type: str) -> None:
    for column in block_layout(call_type)["columns"]:
        actual = headers.get(column["letter"], "")
        if header_matches(actual, column):
            continue
        shown = clean_sheet_cell(actual) or "порожньо"
        raise VipJournalError(
            "Структура аркуша змінилась: "
            f"очікувалось {column['header']} у колонці {column['letter']}, а там {shown}."
        )


def _desired_cells(
    call_type: str,
    *,
    client_id: str,
    call_date: date,
    manager: str,
    tl: str,
    scores: dict[str, float | None],
    check_date: date,
    comment: str,
) -> dict[str, dict[str, Any]]:
    """Клітинки до запису. None-бал у словник не входить і нулем не замінюється."""
    cells: dict[str, dict[str, Any]] = {}
    for column in block_layout(call_type)["columns"]:
        if not column["write"] or column["letter"] in _NEVER_WRITE:
            continue
        kind = column["kind"]
        if kind == "score":
            value = scores.get(column["field"])
            if value is None:
                continue
            cells[column["letter"]] = {"kind": "number", "value": float(value), "field": column["field"]}
        elif column["field"] == "client_id":
            cells[column["letter"]] = {"kind": "string", "value": client_id, "field": "client_id"}
        elif column["field"] == "call_date":
            cells[column["letter"]] = {"kind": "date", "value": date_to_serial(call_date), "field": "call_date"}
        elif column["field"] == "check_date":
            cells[column["letter"]] = {"kind": "date", "value": date_to_serial(check_date), "field": "check_date"}
        elif column["field"] == "manager":
            cells[column["letter"]] = {"kind": "string", "value": manager, "field": "manager"}
        elif column["field"] == "tl":
            cells[column["letter"]] = {"kind": "string", "value": tl, "field": "tl"}
        elif column["field"] == "reviewer":
            cells[column["letter"]] = {"kind": "string", "value": VIP_JOURNAL_REVIEWER, "field": "reviewer"}
        elif column["field"] == "comment":
            cells[column["letter"]] = {"kind": "string", "value": comment, "field": "comment"}
    return cells


def _entered_value(cell: dict[str, Any]) -> dict[str, Any]:
    if cell["kind"] == "string":
        return {"stringValue": str(cell["value"])}
    return {"numberValue": float(cell["value"])}


def build_update_requests(sheet_id: int, row: int, cells: dict[str, dict[str, Any]]) -> list[dict]:
    letters = sorted(cells, key=column_number)
    for letter in letters:
        if letter in _NEVER_WRITE:
            raise VipJournalError(f"Прямокутник запису містить {letter}.")
        if cells[letter]["value"] is None or cells[letter]["value"] == "":
            raise VipJournalError("Прямокутник запису містить порожнє значення.")
    groups: list[list[str]] = []
    for letter in letters:
        if groups and column_number(letter) == column_number(groups[-1][-1]) + 1:
            groups[-1].append(letter)
        else:
            groups.append([letter])
    requests = []
    for group in groups:
        start = column_number(group[0]) - 1
        end = start + len(group)
        if any(column_letter(index + 1) in _NEVER_WRITE for index in range(start, end)):
            raise VipJournalError("Прямокутник запису зачіпає E, J, N, S або AB.")
        requests.append(
            {
                "updateCells": {
                    "range": {
                        "sheetId": int(sheet_id),
                        "startRowIndex": row - 1,
                        "endRowIndex": row,
                        "startColumnIndex": start,
                        "endColumnIndex": end,
                    },
                    "rows": [{"values": [{"userEnteredValue": _entered_value(cells[letter])} for letter in group]}],
                    "fields": "userEnteredValue",
                }
            }
        )
    return requests


def _formula_request(sheet_id: int, call_type: str, row: int) -> dict:
    formula = block_layout(call_type)["formula"]
    letter = formula["letter"]
    index = column_number(letter) - 1
    return {
        "updateCells": {
            "range": {
                "sheetId": int(sheet_id),
                "startRowIndex": row - 1,
                "endRowIndex": row,
                "startColumnIndex": index,
                "endColumnIndex": index + 1,
            },
            "rows": [{"values": [{"userEnteredValue": {"formulaValue": formula["template"].format(row=row)}}]}],
            "fields": "userEnteredValue",
        }
    }


def _occupied(row: dict[str, Any], call_type: str) -> bool:
    ignored = set(block_layout(call_type)["ignore_when_free"])
    for column in block_layout(call_type)["columns"]:
        if column["letter"] in ignored or column["letter"] in _NEVER_WRITE:
            continue
        if column["kind"] == "skip":
            continue
        if not _cell_empty(row.get(column["letter"])):
            return True
    return False


def _key_matches(row: dict[str, Any], call_type: str, client_id: str, call_date: date, manager: str) -> bool:
    columns = {column["field"]: column["letter"] for column in block_layout(call_type)["columns"]}
    if _id_text(row.get(columns["client_id"])) != client_id:
        return False
    if serial_to_date(row.get(columns["call_date"])) != call_date:
        return False
    return clean_sheet_cell(row.get(columns["manager"])) == manager


def _find_rows(block_rows: list[dict[str, Any]], route: dict, call_type: str, client_id: str, call_date: date, manager: str) -> list[int]:
    found = []
    for offset, row in enumerate(block_rows):
        number = route["start_row"] + offset
        if number > route["row_count"]:
            break
        if _key_matches(row, call_type, client_id, call_date, manager):
            found.append(number)
    return found


def _free_row(block_rows: list[dict[str, Any]], route: dict, call_type: str) -> int:
    last = int(route["row_count"])
    for number in range(int(route["start_row"]), last + 1):
        offset = number - int(route["start_row"])
        row = block_rows[offset] if offset < len(block_rows) else {}
        if not _occupied(row, call_type):
            return number
    raise VipJournalError("Журнал заповнений, треба розширити сітку.")


def _values_equal(cell: dict[str, Any], actual: Any) -> bool:
    if cell["kind"] == "string":
        return _id_text(actual) == str(cell["value"]) if cell["field"] == "client_id" else clean_sheet_cell(actual) == str(cell["value"])
    if cell["kind"] == "date":
        return serial_to_date(actual) == serial_to_date(cell["value"])
    return _same_number(actual, float(cell["value"]))


def _score_conflict(call_type: str, letter: str) -> bool:
    return letter in set(block_layout(call_type)["score_letters"])


def _plan_existing(row: dict[str, Any], call_type: str, desired: dict[str, dict[str, Any]], row_number: int) -> tuple[str, dict[str, dict[str, Any]], str]:
    conflicts = []
    pending: dict[str, dict[str, Any]] = {}
    for letter, cell in desired.items():
        actual = row.get(letter)
        if _cell_empty(actual):
            pending[letter] = cell
            continue
        if _values_equal(cell, actual):
            continue
        if _score_conflict(call_type, letter):
            conflicts.append((letter, actual, cell["value"]))
        # Заповнену не-балову клітинку не перезаписуємо: це може бути ручна правка.
    if conflicts:
        letter, actual, wanted = conflicts[0]
        return (
            "conflict",
            {},
            f"Конфлікт: у рядку {row_number} вже стоїть {actual}, аналіз дав {wanted}.",
        )
    if not pending:
        return "same", {}, ""
    return "fill", pending, ""


def _missing_score_names(call_type: str, scores: dict[str, float | None]) -> list[str]:
    names = []
    for column in block_layout(call_type)["columns"]:
        if column["kind"] == "score" and scores.get(column["field"]) is None:
            names.append(column["header"])
    return names


def _status_text(kind: str, route: dict, row: int, missing: list[str], detail: str = "") -> str:
    if kind == "created":
        base = f"Записано · {route['title']} · рядок {row}"
    elif kind == "filled":
        base = f"Дописано · рядок {row}"
    elif kind == "same":
        return f"Вже записано · рядок {row}"
    elif kind == "conflict":
        return f"Конфлікт · рядок {row}"
    elif kind == "ambiguous":
        return detail
    elif kind == "divergent":
        return "Два аналізи розходяться"
    else:
        base = f"Помилка перевірки · рядок {row}"
    if missing and kind in {"created", "filled"}:
        return f"Неповні бали · рядок {row}: {', '.join(missing)}"
    return base


def _read_written_row(book, route: dict, call_type: str, row: int) -> tuple[dict[str, Any], str]:
    block = block_layout(call_type)
    title = route["title"]
    row_ref = qualified_range(title, f"{block['start']}{row}:{block['end']}{row}")
    formula_letter = block["formula"]["letter"]
    formula_ref = qualified_range(title, f"{formula_letter}{row}")
    data_rows = _values_batch(book, [row_ref], "UNFORMATTED_VALUE")
    formula_rows = _values_batch(book, [formula_ref], "FORMULA")
    matrix = data_rows[0] if data_rows else []
    mapped = _row_map(matrix[0] if matrix else [], block["start"])
    formula = ""
    formula_matrix = formula_rows[0] if formula_rows else []
    if formula_matrix and formula_matrix[0]:
        formula = str(formula_matrix[0][0] or "")
    return mapped, formula


def _verify(actual: dict[str, Any], formula: str, call_type: str, desired: dict[str, dict[str, Any]], row: int) -> list[str]:
    problems = []
    for letter, cell in desired.items():
        got = actual.get(letter)
        if cell["field"] == "comment":
            if isinstance(got, (int, float)) and not isinstance(got, bool):
                problems.append(f"{letter}{row}: очікувалось {cell['value']!r} / є число {got}")
                continue
            if comment_has_ratio(got):
                problems.append(f"{letter}{row}: очікувалось текст без N/M / є {got!r}")
                continue
        if not _values_equal(cell, got):
            problems.append(f"{letter}{row}: очікувалось {cell['value']!r} / є {got!r}")
    expected = block_layout(call_type)["formula"]["template"].format(row=row)
    if formula.replace(" ", "").upper() != expected.replace(" ", "").upper():
        problems.append(f"{block_layout(call_type)['formula']['letter']}{row}: очікувалось {expected} / є {formula or 'порожньо'}")
    return problems


def _commit(book, requests: list[dict]) -> None:
    if not requests:
        return
    for request in requests:
        fields = request.get("updateCells", {}).get("fields")
        if fields != "userEnteredValue":
            raise VipJournalError("Запис дозволяє лише fields=userEnteredValue.")
    book.batch_update({"requests": requests})


def _ensure_formula(book, route: dict, call_type: str, row: int, formula: str, *, dry_run: bool) -> str:
    expected = block_layout(call_type)["formula"]["template"].format(row=row)
    if formula.replace(" ", "").upper() == expected.replace(" ", "").upper():
        return formula
    request = _formula_request(route["sheet_id"], call_type, row)
    if dry_run:
        return expected
    _commit(book, [request])
    _, stored = _read_written_row(book, route, call_type, row)
    return stored


def _process_lock(sheet_id: int, call_type: str):
    key = (str(sheet_id), call_type)
    with _PROCESS_GUARD:
        return _PROCESS_LOCKS.setdefault(key, threading.Lock())


def _remote_lock(supabase, sheet_id: int, call_type: str, owner: str) -> None:
    if supabase is None:
        return
    key = f"{sheet_id}:{call_type}"
    now = datetime.now(ZoneInfo(VIP_JOURNAL_TZ))
    try:
        existing = supabase.table("vip_journal_locks").select("owner,expires_at").eq("lock_key", key).limit(1).execute()
        rows = getattr(existing, "data", None) or []
        if rows:
            expires = rows[0].get("expires_at") or ""
            try:
                expires_at = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
            except ValueError:
                expires_at = now
            if expires_at > now and rows[0].get("owner") != owner:
                raise VipJournalError("Журнал зайнятий іншим записом. Повторіть за хвилину.")
        supabase.table("vip_journal_locks").upsert(
            {
                "lock_key": key,
                "owner": owner,
                "expires_at": (now + _LOCK_TTL).isoformat(),
            }
        ).execute()
    except VipJournalError:
        raise
    except Exception:
        logger.warning("Журнальний лок Supabase недоступний", exc_info=True)


def _release_remote_lock(supabase, sheet_id: int, call_type: str, owner: str) -> None:
    if supabase is None:
        return
    try:
        supabase.table("vip_journal_locks").delete().eq("lock_key", f"{sheet_id}:{call_type}").eq("owner", owner).execute()
    except Exception:
        logger.debug("Не вдалося зняти лок журналу", exc_info=True)


def _remember(record: dict, supabase=None) -> None:
    try:
        _DEDUP_PATH.parent.mkdir(parents=True, exist_ok=True)
        store = {}
        if _DEDUP_PATH.exists():
            store = json.loads(_DEDUP_PATH.read_text(encoding="utf-8") or "{}")
        store[str(record.get("analysis_id") or record.get("call_key"))] = record
        _DEDUP_PATH.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.debug("Локальний журнал запису не збережено", exc_info=True)
    if supabase is None:
        return
    try:
        supabase.table("vip_journal_writes").upsert(record).execute()
    except Exception:
        logger.warning("Запис результату в Supabase не вдався", exc_info=True)


def _load_prior_scores(supabase, *, project: str, call_type: str, client_id: str, call_date: date, manager: str) -> list[dict]:
    if supabase is None:
        return []
    try:
        response = (
            supabase.table("vip_short_call_logs")
            .select("client_id,call_date,ret_manager,project,call_type,criteria_scores,verdict")
            .eq("client_id", client_id)
            .limit(30)
            .execute()
        )
    except Exception:
        logger.warning("Перевірка інших аналізів у Supabase не вдалась", exc_info=True)
        return []
    found = []
    for row in getattr(response, "data", None) or []:
        row_type = resolve_journal_call_type(row.get("call_type"))
        row_project = normalize_project_key(row.get("project"))
        row_date = _parse_ua_date(row.get("call_date"))
        row_manager = clean_sheet_cell(row.get("ret_manager"))
        if row_type != call_type or row_project != project or row_date != call_date or row_manager != manager:
            continue
        if str(row.get("verdict") or "scored") in {"failed", "error"}:
            continue
        found.append(row)
    return found


def _scores_from_criteria(call_type: str, criteria: list) -> dict[str, float | None]:
    by_key = {}
    for item in criteria or []:
        if isinstance(item, dict) and item.get("key"):
            by_key[str(item["key"])] = item.get("points")
    raw = {column["field"]: by_key.get(column["field"]) for column in block_layout(call_type)["columns"] if column["kind"] == "score"}
    return validate_scores(call_type, raw)


def _scores_conflict(left: dict[str, float | None], right: dict[str, float | None]) -> bool:
    keys = set(left) | set(right)
    for key in keys:
        if left.get(key) != right.get(key):
            return True
    return False


def _result(ok: bool, status: str, *, route: dict | None = None, row: int | None = None, error: str = "", extra: dict | None = None) -> dict:
    payload = {
        "ok": ok,
        "status": status,
        "error": error,
        "row": row,
        "sheet_title": (route or {}).get("title", ""),
        "sheet_id": (route or {}).get("sheet_id"),
        "call_type": (route or {}).get("call_type", ""),
    }
    if extra:
        payload.update(extra)
    return payload


def write_journal_call(
    google_client,
    *,
    project: str,
    call_type: str,
    client_id: str,
    call_date: date | str,
    manager: str,
    scores: dict[str, Any] | None,
    check_date: date | str | None = None,
    reasons: dict[str, str] | None = None,
    managers: list[dict] | None = None,
    login: str = "",
    dry_run: bool = False,
    supabase=None,
    prior_analyses: list[dict] | None = None,
    analysis_id: str = "",
    sleeper=None,
) -> dict:
    """Алгоритм розділів 2–3. Повертає статус і нічого не пише в режимі dry_run."""
    sleep = sleeper or time.sleep
    if supabase is False:
        supabase = None
    route = project_layout(project)
    route["call_type"] = call_type
    client = str(client_id or "").strip()
    if not client:
        raise VipJournalError("Обов'язкове поле client_id порожнє.")
    parsed_call = _parse_ua_date(call_date)
    if parsed_call is None:
        raise VipJournalError("Обов'язкове поле call_date порожнє.")
    parsed_check = _parse_ua_date(check_date) or journal_today()
    if managers is None:
        managers = load_journal_managers(google_client)
    directory = resolve_manager_from_directory(
        managers,
        project_key=route["key"],
        manager_name=manager,
        login=login,
    )
    checked = validate_scores(call_type, scores)
    comment = build_comment_from_scores(call_type, checked, reasons)
    desired = _desired_cells(
        call_type,
        client_id=client,
        call_date=parsed_call,
        manager=directory["manager"],
        tl=directory["tl"],
        scores=checked,
        check_date=parsed_check,
        comment=comment,
    )
    missing = _missing_score_names(call_type, checked)
    owner = analysis_id or f"{route['key']}:{call_type}:{client}:{parsed_call.isoformat()}:{directory['manager']}"
    account = _writer_account(google_client)
    book = _open_book(google_client)
    worksheet = _worksheet(book, route)
    route["row_count"] = int(getattr(worksheet, "row_count", 0) or 0)
    if route["row_count"] < route["start_row"]:
        raise VipJournalError("Журнал заповнений, треба розширити сітку.")
    if str(getattr(worksheet, "title", "")) in _READ_ONLY_SHEETS:
        raise VipJournalError("Цей аркуш записувати не можна.")

    prior = list(prior_analyses or [])
    if prior_analyses is None:
        prior = _load_prior_scores(
            supabase,
            project=route["key"],
            call_type=call_type,
            client_id=client,
            call_date=parsed_call,
            manager=directory["manager"],
        )
    for earlier in prior:
        earlier_scores = _scores_from_criteria(call_type, earlier.get("criteria_scores") or earlier.get("criteria") or [])
        if _scores_conflict(checked, earlier_scores):
            return _result(
                False,
                "Два аналізи розходяться",
                route=route,
                error="Два аналізи дають різні бали",
                extra={"scores": checked, "other_scores": earlier_scores},
            )

    lock = _process_lock(route["sheet_id"], call_type)
    with lock:
        _remote_lock(supabase, route["sheet_id"], call_type, owner)
        try:
            return _write_locked(
                book,
                route,
                call_type,
                client,
                parsed_call,
                directory,
                checked,
                desired,
                missing,
                comment,
                account,
                dry_run,
                sleep,
                supabase,
                owner,
            )
        finally:
            _release_remote_lock(supabase, route["sheet_id"], call_type, owner)


def _write_locked(book, route, call_type, client, call_date, directory, scores, desired, missing, comment, account, dry_run, sleep, supabase, owner) -> dict:
    headers, block_rows = _read_headers_and_block(book, route, call_type)
    _check_headers(headers, call_type)
    matches = _find_rows(block_rows, route, call_type, client, call_date, directory["manager"])
    if len(matches) > 1:
        listed = ", ".join(str(number) for number in matches)
        status = f"Неоднозначно · рядки {listed}"
        _remember(_log_record(route, call_type, client, call_date, directory, status, None, desired, {}, owner), supabase)
        return _result(False, status, route=route, error=f"Неоднозначно: рядки {listed}")
    if len(matches) == 1:
        row_number = matches[0]
        current = block_rows[row_number - route["start_row"]]
        action, pending, detail = _plan_existing(current, call_type, desired, row_number)
        if action == "conflict":
            _remember(_log_record(route, call_type, client, call_date, directory, "Конфлікт", row_number, desired, current, owner), supabase)
            return _result(False, f"Конфлікт · рядок {row_number}", route=route, row=row_number, error=detail)
        if action == "same":
            status = _status_text("same", route, row_number, [])
            _remember(_log_record(route, call_type, client, call_date, directory, status, row_number, desired, current, owner), supabase)
            return _result(True, status, route=route, row=row_number, extra={"duplicate": True})
        to_write = pending
        kind = "filled"
    else:
        row_number = _free_row(block_rows, route, call_type)
        to_write = desired
        kind = "created"

    plan = [{"letter": letter, "value": cell["value"], "kind": cell["kind"]} for letter, cell in to_write.items()]
    if dry_run:
        return _result(
            True,
            f"План · {route['title']} · рядок {row_number}",
            route=route,
            row=row_number,
            extra={"dry_run": True, "cells": plan},
        )
    requests = build_update_requests(route["sheet_id"], row_number, to_write)
    _send_with_retry(
        book,
        route,
        call_type,
        requests,
        row_number,
        client,
        call_date,
        directory["manager"],
        desired,
        sleep,
        account,
    )
    actual, formula = _read_written_row(book, route, call_type, row_number)
    formula = _ensure_formula(book, route, call_type, row_number, formula, dry_run=False)
    actual, formula = _read_written_row(book, route, call_type, row_number)
    problems = _verify(actual, formula, call_type, desired, row_number)
    if problems:
        message = "Помилка перевірки: " + "; ".join(problems)
        _remember(_log_record(route, call_type, client, call_date, directory, message, row_number, desired, actual, owner), supabase)
        return _result(False, "Помилка перевірки", route=route, row=row_number, error=message)
    status = _status_text(kind, route, row_number, missing)
    _remember(_log_record(route, call_type, client, call_date, directory, status, row_number, desired, actual, owner), supabase)
    return _result(True, status, route=route, row=row_number, extra={"written": plan, "comment": comment})


def _send_with_retry(book, route, call_type, requests, row_number, client, call_date, manager, desired, sleep, account: str) -> None:
    delays = list(_BACKOFF_SECONDS)
    while True:
        try:
            _commit(book, requests)
            return
        except Exception as exc:
            if not _retryable(exc) or not delays:
                ref = qualified_range(route["title"], f"A{row_number}")
                raise VipJournalError(
                    f"Помилка. {route['title']} {ref}: {_public_error(exc)}. Обліковий запис: {account}."
                ) from exc
            sleep(delays.pop(0))
            _, rows = _read_headers_and_block(book, route, call_type)
            current = rows[row_number - route["start_row"]] if row_number - route["start_row"] < len(rows) else {}
            if _key_matches(current, call_type, client, call_date, manager):
                action, _pending, _detail = _plan_existing(current, call_type, desired, row_number)
                if action == "same":
                    return


def _log_record(route, call_type, client, call_date, directory, status, row, payload, actual, owner) -> dict:
    return {
        "analysis_id": owner,
        "spreadsheet_id": VIP_JOURNAL_SHEET_ID,
        "sheet_id": route["sheet_id"],
        "sheet_title": route["title"],
        "project": route["key"],
        "call_type": call_type,
        "client_id": client,
        "call_date": call_date.isoformat(),
        "manager": directory["manager"],
        "row": row,
        "status": status,
        "payload": {letter: cell["value"] for letter, cell in payload.items()},
        "actual": {letter: value for letter, value in (actual or {}).items() if not _cell_empty(value)},
        "written_at": datetime.now(ZoneInfo(VIP_JOURNAL_TZ)).isoformat(),
    }


def _reasons_from_verdict(verdict_data: dict) -> dict[str, str]:
    reasons = {}
    for item in verdict_data.get("criteria") or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        parts = item.get("reasons") or []
        if isinstance(parts, str):
            parts = [parts]
        text = "; ".join(clean_sheet_cell(part) for part in parts if clean_sheet_cell(part))
        if not text and item.get("reason"):
            text = clean_sheet_cell(item.get("reason"))
        if text:
            reasons[str(item["key"])] = text
    return reasons


def _scores_input(call_type: str, verdict_data: dict) -> dict[str, Any]:
    by_key = {}
    for item in verdict_data.get("criteria") or []:
        if isinstance(item, dict) and item.get("key"):
            by_key[str(item["key"])] = item.get("points")
    return {
        column["field"]: by_key.get(column["field"])
        for column in block_layout(call_type)["columns"]
        if column["kind"] == "score"
    }


def _optional_supabase():
    try:
        from supabase_logger import get_supabase_client

        client, _error = get_supabase_client()
        return client
    except Exception:
        logger.debug("Supabase для журналу недоступний", exc_info=True)
        return None


def write_vip_journal_result(
    google_client,
    call: dict,
    verdict_data: dict,
    *,
    spreadsheet_id: str | None = None,
    managers: list[dict] | None = None,
    dry_run: bool = False,
    supabase=None,
    sleeper=None,
) -> dict:
    """Вхід застосунку. Той самий алгоритм, що й write_journal_call."""
    _ = spreadsheet_id
    try:
        call_type = resolve_journal_call_type(
            call.get("journal_call_type") or call.get("vip_call_type") or verdict_data.get("call_type")
        )
        if not call_type:
            raise VipJournalError("Невідомий тип дзвінка (очікується short або friendly).")
        if supabase is False:
            remote = None
        elif supabase is None:
            remote = _optional_supabase()
        else:
            remote = supabase
        analysis_id = str(call.get("analysis_id") or "").strip() or make_analysis_id(call, call_type)
        result = write_journal_call(
            google_client,
            project=str(call.get("project") or ""),
            call_type=call_type,
            client_id=str(call.get("client_id") or ""),
            call_date=call.get("call_date"),
            manager=str(call.get("ret_manager") or call.get("manager") or ""),
            login=str(call.get("manager_login") or call.get("login") or ""),
            scores=_scores_input(call_type, verdict_data),
            check_date=call.get("check_date") or call.get("listen_date"),
            reasons=_reasons_from_verdict(verdict_data),
            managers=managers,
            dry_run=dry_run,
            supabase=remote,
            analysis_id=analysis_id,
            sleeper=sleeper,
        )
        result["analysis_id"] = analysis_id
        result["call_type"] = call_type
        return result
    except VipJournalError as exc:
        logger.warning("VIP journal write blocked: %s", exc)
        return {"ok": False, "status": "Помилка", "error": str(exc)}
    except Exception as exc:
        logger.exception("VIP journal write failed")
        return {
            "ok": False,
            "status": "Помилка",
            "error": _public_error(exc),
        }


def _comment_score_for(text: str, keyword: str) -> float | None:
    if not text or not keyword:
        return None
    token = normalize_header(keyword)
    stem = token[:6] if len(token) > 6 else token
    for line in str(text).splitlines() or [str(text)]:
        folded = normalize_header(line)
        if stem not in folded:
            continue
        ratio = re.search(r"(\d+(?:[.,]\d+)?)\s*[/⁄∕／]\s*(\d+(?:[.,]\d+)?)", line)
        words = re.search(r"(\d+(?:[.,]\d+)?)\s*із\s*(\d+(?:[.,]\d+)?)", line)
        match = ratio or words
        if match:
            return float(match.group(1).replace(",", "."))
    return None


def audit_block(
    *,
    sheet_title: str,
    call_type: str,
    rows: list[dict[str, Any]],
    start_row: int,
    directory: list[dict],
    project_key: str,
) -> list[dict[str, str]]:
    """Лише звіт. Рядки не змінює."""
    issues = []
    seen: dict[tuple, list[int]] = {}
    block = block_layout(call_type)
    letters = {column["field"]: column for column in block["columns"]}
    for offset, row in enumerate(rows):
        number = start_row + offset
        client = _id_text(row.get(letters["client_id"]["letter"]))
        if not client:
            continue
        manager = clean_sheet_cell(row.get(letters["manager"]["letter"]))
        tl = clean_sheet_cell(row.get(letters["tl"]["letter"]))
        comment = row.get(letters["comment"]["letter"])
        call_date = serial_to_date(row.get(letters["call_date"]["letter"]))
        key = (client, call_date.isoformat() if call_date else "", manager)
        seen.setdefault(key, []).append(number)
        if not tl:
            issues.append(_issue(sheet_title, call_type, number, client, "порожній TL", manager))
        matches = [
            item
            for item in directory
            if normalize_project_key(item.get("project")) == project_key
            and clean_sheet_cell(item.get("manager")) == manager
        ]
        if len(matches) != 1:
            issues.append(_issue(sheet_title, call_type, number, client, "менеджер не з довідника", manager))
        elif clean_sheet_cell(matches[0].get("tl")) != tl and tl:
            issues.append(
                _issue(
                    sheet_title,
                    call_type,
                    number,
                    client,
                    "TL не відповідає довіднику",
                    f"{tl} / {matches[0].get('tl')}",
                )
            )
        if isinstance(comment, (int, float)) and not isinstance(comment, bool):
            issues.append(_issue(sheet_title, call_type, number, client, "коментар збережено числом", comment))
        elif comment_has_ratio(comment):
            issues.append(_issue(sheet_title, call_type, number, client, "коментар містить N/M", comment))
        formula = str(row.get(block["formula"]["letter"]) or "")
        expected = block["formula"]["template"].format(row=number)
        if not formula.startswith("="):
            issues.append(_issue(sheet_title, call_type, number, client, "немає формули", block["formula"]["letter"]))
        elif formula.replace(" ", "").upper() != expected.replace(" ", "").upper():
            issues.append(_issue(sheet_title, call_type, number, client, "формулу змінено", formula))
        for column in block["columns"]:
            if column["kind"] != "score":
                continue
            value = row.get(column["letter"])
            if _cell_empty(value):
                continue
            try:
                _canonical_score(column["field"], value, column["allowed"])
            except VipJournalError:
                issues.append(_issue(sheet_title, call_type, number, client, "бал поза дозволеними", f"{column['letter']}={value}"))
            mentioned = _comment_score_for(str(comment or ""), column["keyword"])
            if mentioned is not None and not _same_number(value, mentioned):
                issues.append(
                    _issue(
                        sheet_title,
                        call_type,
                        number,
                        client,
                        "бал у клітинці не збігається з коментарем",
                        f"{column['letter']}={value}, коментар={mentioned}",
                    )
                )
    for key, numbers in seen.items():
        if len(numbers) > 1 and key[0]:
            issues.append(
                _issue(
                    sheet_title,
                    call_type,
                    numbers[0],
                    key[0],
                    "дубль ключа дзвінка",
                    ", ".join(str(number) for number in numbers),
                )
            )
    return issues


def _issue(sheet, call_type, row, client, kind, detail) -> dict[str, str]:
    return {
        "sheet": sheet,
        "block": call_type,
        "row": str(row),
        "client_id": str(client),
        "issue": kind,
        "detail": str(detail),
    }


def plan_safe_fixes(
    *,
    sheet_title: str,
    call_type: str,
    rows: list[dict[str, Any]],
    start_row: int,
    directory: list[dict],
    project_key: str,
    sheet_id: int,
) -> list[dict[str, Any]]:
    """Лише порожній TL з довідника і N/M, якщо бал у тексті дорівнює клітинці."""
    plans = []
    letters = {column["field"]: column for column in block_layout(call_type)["columns"]}
    for offset, row in enumerate(rows):
        number = start_row + offset
        client = _id_text(row.get(letters["client_id"]["letter"]))
        if not client:
            continue
        manager = clean_sheet_cell(row.get(letters["manager"]["letter"]))
        tl = clean_sheet_cell(row.get(letters["tl"]["letter"]))
        if not tl:
            matches = [
                item
                for item in directory
                if normalize_project_key(item.get("project")) == project_key
                and clean_sheet_cell(item.get("manager")) == manager
                and clean_sheet_cell(item.get("tl"))
            ]
            if len(matches) == 1:
                plans.append(
                    {
                        "sheet": sheet_title,
                        "sheet_id": sheet_id,
                        "row": number,
                        "letter": letters["tl"]["letter"],
                        "value": clean_sheet_cell(matches[0].get("tl")),
                        "reason": "порожній TL",
                    }
                )
        comment = row.get(letters["comment"]["letter"])
        if not isinstance(comment, str) or not comment_has_ratio(comment):
            continue
        safe = True
        for column in block_layout(call_type)["columns"]:
            if column["kind"] != "score":
                continue
            mentioned = _comment_score_for(comment, column["keyword"])
            if mentioned is None:
                continue
            actual = row.get(column["letter"])
            if _cell_empty(actual) or not _same_number(actual, mentioned):
                safe = False
        if not safe:
            continue
        replaced = re.sub(
            r"(\d+(?:[.,]\d+)?)\s*[/⁄∕／]\s*(\d+(?:[.,]\d+)?)",
            lambda match: f"{match.group(1).replace('.', ',')} із {match.group(2).replace('.', ',')}",
            comment,
        )
        if replaced != comment and not comment_has_ratio(replaced):
            plans.append(
                {
                    "sheet": sheet_title,
                    "sheet_id": sheet_id,
                    "row": number,
                    "letter": letters["comment"]["letter"],
                    "value": replaced,
                    "reason": "N/M збігається з балом",
                }
            )
    return plans


def apply_safe_fixes(book, plans: list[dict[str, Any]]) -> None:
    requests = []
    for plan in plans:
        if plan["sheet"] in _READ_ONLY_SHEETS:
            raise VipJournalError(f"Аркуш {plan['sheet']} не записується.")
        letter = plan["letter"]
        if letter in _NEVER_WRITE or letter == "N":
            raise VipJournalError(f"Безпечне виправлення не пише колонку {letter}.")
        index = column_number(letter) - 1
        requests.append(
            {
                "updateCells": {
                    "range": {
                        "sheetId": int(plan["sheet_id"]),
                        "startRowIndex": int(plan["row"]) - 1,
                        "endRowIndex": int(plan["row"]),
                        "startColumnIndex": index,
                        "endColumnIndex": index + 1,
                    },
                    "rows": [{"values": [{"userEnteredValue": {"stringValue": str(plan["value"])}}]}],
                    "fields": "userEnteredValue",
                }
            }
        )
    _commit(book, requests)
