"""Автозапис результатів VIP-аналізу в журнал за проєктом (Betking / 777 / Vegas).

Короткі → A:L (без I — формула, без K — ручний QA).
Френдлі → N:AC (без Z — формула, без AB — ручний QA).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import date, datetime
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
    VIP_JOURNAL_PROJECTS,
    VIP_JOURNAL_REVIEWER,
    VIP_JOURNAL_SHEET_ID,
    VIP_JOURNAL_TZ,
    resolve_call_type_key,
)
from google_sheets import clean_sheet_cell, sheets_retry

logger = logging.getLogger(__name__)

_WRITE_LOCK = threading.Lock()
_DEDUP_DIR = Path(__file__).resolve().parent / ".cache"
_DEDUP_PATH = _DEDUP_DIR / "vip_journal_writes.json"

# Допустимі бали за ТЗ (роздільник у Sheets — числовий float).
_ALLOWED_SHORT = {
    "contact": {0.0, 2.5, 5.0},
    "slip_handling": {0.0, 2.5, 5.0, 7.5, 10.0},
    "prep": {0.0, 2.5, 5.0, 7.5, 10.0},
    "closing": {0.0, 2.5, 5.0},
}
_ALLOWED_FRIENDLY = {
    "contact": {0.0, 2.5, 5.0},
    "friendly_development": {0.0, 2.5, 5.0, 7.5},
    "personal_approach": {0.0, 2.5, 5.0, 7.5},
    # 7.5 для «Заклик до гри» не передбачене
    "call_to_action": {0.0, 2.5, 5.0, 10.0},
    "bonus_offer": {0.0, 2.5, 5.0},
    "prep": {0.0, 2.5, 5.0, 7.5, 10.0},
    "closing": {0.0, 2.5, 5.0},
    "ease": {0.0, 2.5, 5.0, 7.5},
}

_SHORT_KEYS = ("contact", "slip_handling", "prep", "closing")
_FRIENDLY_KEYS = (
    "contact",
    "friendly_development",
    "personal_approach",
    "call_to_action",
    "bonus_offer",
    "prep",
    "closing",
    "ease",
)


class VipJournalError(ValueError):
    """Помилка валідації / маршрутизації журналу (без запису)."""


def normalize_project_key(project: str | None) -> str | None:
    text = clean_sheet_cell(project).casefold().replace(" ", "")
    if not text:
        return None
    aliases = {
        "betking": "betking",
        "беткінг": "betking",
        "беткинг": "betking",
        "777": "777",
        "vegas": "vegas",
        "вегас": "vegas",
    }
    return aliases.get(text)


def resolve_journal_call_type(value: str | None) -> str | None:
    """Повертає short|friendly з вибору аналізатора (не з тривалості)."""
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
        return (
            VIP_JOURNAL_CALL_TYPE_FRIENDLY
            if value == CALL_TYPE_FRIENDLY
            else VIP_JOURNAL_CALL_TYPE_SHORT
        )
    return None


def resolve_project_route(project: str | None) -> dict:
    key = normalize_project_key(project)
    if not key or key not in VIP_JOURNAL_PROJECTS:
        raise VipJournalError(
            f"Невідомий проєкт для журналу: {project!r}. Очікується betking / 777 / vegas."
        )
    route = dict(VIP_JOURNAL_PROJECTS[key])
    route["key"] = key
    return route


def make_analysis_id(call: dict, call_type: str) -> str:
    """Стабільний id для дедупу повторної доставки (не client_id)."""
    payload = "|".join(
        [
            str(call.get("url") or "").strip(),
            str(call.get("client_id") or "").strip(),
            str(call.get("call_date") or "").strip(),
            str(call_type or "").strip(),
            str(call.get("check_date") or call.get("listen_date") or "").strip(),
            str(call.get("ret_manager") or call.get("manager") or "").strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _criterion_points_value(criteria: list, key: str) -> float | None:
    for item in criteria or []:
        if not isinstance(item, dict) or item.get("key") != key:
            continue
        pts = item.get("points")
        if pts is None:
            return None
        try:
            return float(pts)
        except (TypeError, ValueError) as exc:
            raise VipJournalError(f"Некоректний бал критерію {key}: {pts!r}") from exc
    return None


def _validate_score(key: str, value: float | None, allowed: set[float]) -> float | None:
    if value is None:
        return None
    for candidate in allowed:
        if abs(value - candidate) < 1e-9:
            return candidate
    raise VipJournalError(
        f"Недопустимий бал {key}={value:g}. Дозволено: {sorted(allowed)}"
    )


def extract_short_scores(verdict_data: dict) -> dict[str, float | None]:
    criteria = verdict_data.get("criteria") or []
    out: dict[str, float | None] = {}
    for key in _SHORT_KEYS:
        out[key] = _validate_score(key, _criterion_points_value(criteria, key), _ALLOWED_SHORT[key])
    return out


def extract_friendly_scores(verdict_data: dict) -> dict[str, float | None]:
    criteria = verdict_data.get("criteria") or []
    out: dict[str, float | None] = {}
    for key in _FRIENDLY_KEYS:
        out[key] = _validate_score(
            key, _criterion_points_value(criteria, key), _ALLOWED_FRIENDLY[key]
        )
    return out


def _parse_ua_date(value: str | date | datetime | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise VipJournalError(f"Некоректна дата: {value!r}")


def journal_today() -> date:
    return datetime.now(ZoneInfo(VIP_JOURNAL_TZ)).date()


def _as_sheet_date(value: date | None) -> str:
    """Дата для USER_ENTERED у форматі, який Sheets парсить у Europe/Kiev."""
    if value is None:
        return ""
    return value.strftime("%d.%m.%Y")


def _as_text_id(client_id: str) -> str:
    """Зберігає початкові нулі (текст у Sheets)."""
    text = str(client_id or "")
    if not text:
        return ""
    return f"'{text}" if text[:1].isdigit() else text


def _score_cell(value: float | None):
    """Порожній критерій → порожня комірка; 0 лишається 0."""
    if value is None:
        return ""
    return value


def parse_journal_managers(values: list[list]) -> list[dict]:
    """A=проєкт, B=TL, C=менеджер, D=логін."""
    rows = []
    started = False
    for raw in values or []:
        row = list(raw or [])
        cells = [clean_sheet_cell(c) for c in row[:4]]
        if not any(cells):
            continue
        low = [c.casefold() for c in cells]
        if not started and (
            "проєкт" in low[0]
            or "проект" in low[0]
            or low[0] in {"project", "a"}
            or (low[2] in {"менеджер", "manager"} and low[1] in {"tl", "тімлід", "тимлид", ""})
        ):
            started = True
            continue
        started = True
        project, tl, manager, login = (cells + ["", "", "", ""])[:4]
        if not manager:
            continue
        rows.append(
            {
                "project": project,
                "tl": tl,
                "manager": manager,
                "login": login,
            }
        )
    return rows


def load_journal_managers(google_client, spreadsheet_id: str | None = None) -> list[dict]:
    sheet_id = spreadsheet_id or VIP_JOURNAL_SHEET_ID
    worksheet = google_client.open_by_key(sheet_id).worksheet(VIP_JOURNAL_MANAGERS_WORKSHEET)
    values = sheets_retry(worksheet.get_all_values)
    return parse_journal_managers(values)


def resolve_manager_from_directory(
    managers: list[dict],
    *,
    project_key: str,
    manager_name: str = "",
    login: str = "",
) -> dict:
    """Один однозначний запис за проєктом + логіном (або ПІБ)."""
    want_project = project_key.casefold()
    pool = []
    for row in managers or []:
        row_key = normalize_project_key(row.get("project"))
        if row_key != want_project:
            # також пряме порівняння назви аркуша / сирого проєкту
            raw = clean_sheet_cell(row.get("project")).casefold()
            if raw not in {want_project, VIP_JOURNAL_PROJECTS[project_key]["title"].casefold()}:
                continue
        pool.append(row)

    login_norm = clean_sheet_cell(login).casefold()
    name_norm = clean_sheet_cell(manager_name).casefold()
    matches = []
    if login_norm:
        matches = [r for r in pool if clean_sheet_cell(r.get("login")).casefold() == login_norm]
    if not matches and name_norm:
        matches = [r for r in pool if clean_sheet_cell(r.get("manager")).casefold() == name_norm]
    if not matches:
        raise VipJournalError(
            f"Менеджера не знайдено в «{VIP_JOURNAL_MANAGERS_WORKSHEET}» "
            f"(проєкт={project_key}, login={login!r}, name={manager_name!r})."
        )
    if len(matches) > 1:
        raise VipJournalError(
            f"Неоднозначний менеджер у довіднику (проєкт={project_key}, "
            f"login={login!r}, name={manager_name!r}): {len(matches)} збіги."
        )
    return matches[0]


def find_next_journal_row(
    col_values: list,
    *,
    start_row: int,
) -> int:
    """Вільний рядок блоку: зайнятий лише якщо є ID клієнта (ключ блоку)."""
    idx = max(start_row, 1) - 1
    values = list(col_values or [])
    while idx < len(values):
        if not str(values[idx] or "").strip():
            return idx + 1
        idx += 1
    return idx + 1


def build_short_row_payload(
    *,
    client_id: str,
    call_date: date | None,
    manager: str,
    tl: str,
    scores: dict[str, float | None],
    check_date: date | None,
    reviewer: str = VIP_JOURNAL_REVIEWER,
) -> dict[str, Any]:
    """Клітинки короткого блоку без I (формула) і K (ручний QA)."""
    return {
        "A": _as_text_id(client_id),
        "B": _as_sheet_date(call_date),
        "C": manager,
        "D": tl,
        "E": _score_cell(scores.get("contact")),
        "F": _score_cell(scores.get("slip_handling")),
        "G": _score_cell(scores.get("prep")),
        "H": _score_cell(scores.get("closing")),
        "J": reviewer,
        "L": _as_sheet_date(check_date),
    }


def build_friendly_row_payload(
    *,
    client_id: str,
    call_date: date | None,
    manager: str,
    tl: str,
    scores: dict[str, float | None],
    check_date: date | None,
    reviewer: str = VIP_JOURNAL_REVIEWER,
) -> dict[str, Any]:
    """Клітинки френдлі блоку без Z (формула) і AB (ручний QA)."""
    return {
        "N": _as_text_id(client_id),
        "O": _as_sheet_date(call_date),
        "P": manager,
        "Q": tl,
        "R": _score_cell(scores.get("contact")),
        "S": _score_cell(scores.get("friendly_development")),
        "T": _score_cell(scores.get("personal_approach")),
        "U": _score_cell(scores.get("call_to_action")),
        "V": _score_cell(scores.get("bonus_offer")),
        "W": _score_cell(scores.get("prep")),
        "X": _score_cell(scores.get("closing")),
        "Y": _score_cell(scores.get("ease")),
        "AA": reviewer,
        "AC": _as_sheet_date(check_date),
    }


def _load_dedup_store() -> dict:
    try:
        if _DEDUP_PATH.exists():
            return json.loads(_DEDUP_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to read journal dedup store")
    return {}


def _save_dedup_store(data: dict) -> None:
    try:
        _DEDUP_DIR.mkdir(parents=True, exist_ok=True)
        _DEDUP_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        logger.exception("Failed to write journal dedup store")


def _supabase_get_mapping(analysis_id: str) -> dict | None:
    try:
        from supabase_logger import get_supabase_client

        client, _err = get_supabase_client()
        if client is None:
            return None
        res = (
            client.table("vip_journal_writes")
            .select("*")
            .eq("analysis_id", analysis_id)
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        return dict(rows[0]) if rows else None
    except Exception:
        return None


def _supabase_upsert_mapping(record: dict) -> None:
    try:
        from supabase_logger import get_supabase_client

        client, _err = get_supabase_client()
        if client is None:
            return
        client.table("vip_journal_writes").upsert(record).execute()
    except Exception:
        logger.debug("vip_journal_writes upsert skipped", exc_info=True)


def get_existing_write(analysis_id: str) -> dict | None:
    remote = _supabase_get_mapping(analysis_id)
    if remote:
        return remote
    local = _load_dedup_store()
    item = local.get(analysis_id)
    return dict(item) if isinstance(item, dict) else None


def remember_write(analysis_id: str, record: dict) -> None:
    payload = {"analysis_id": analysis_id, **record}
    store = _load_dedup_store()
    store[analysis_id] = payload
    _save_dedup_store(store)
    _supabase_upsert_mapping(payload)


def _open_project_worksheet(google_client, route: dict):
    workbook = google_client.open_by_key(VIP_JOURNAL_SHEET_ID)
    try:
        return workbook.get_worksheet_by_id(int(route["sheet_id"]))
    except Exception:
        return workbook.worksheet(str(route["title"]))


def _a1(col: str, row: int) -> str:
    return f"{col}{row}"


def _write_cells(worksheet, row: int, payload: dict[str, Any]) -> None:
    # Пишемо окремими діапазонами, щоб не чіпати формули I/Z і ручні K/AB.
    data = [{"range": _a1(col, row), "values": [[value]]} for col, value in payload.items()]
    sheets_retry(
        worksheet.batch_update,
        data,
        value_input_option="USER_ENTERED",
    )


def _read_cells(worksheet, row: int, cols: list[str]) -> dict[str, str]:
    ranges = [_a1(c, row) for c in cols]
    result = sheets_retry(worksheet.batch_get, ranges)
    out: dict[str, str] = {}
    for col, block in zip(cols, result):
        cell = ""
        if block and block[0]:
            cell = str(block[0][0] if block[0] else "")
        out[col] = cell.strip()
    return out


def _normalize_verify(value) -> str:
    text = str(value or "").strip()
    if text.startswith("'"):
        text = text[1:]
    # числа з коми/крапки
    try:
        num = float(text.replace(",", "."))
        return f"{num:g}"
    except ValueError:
        return text.casefold()


def _payload_matches(expected: dict[str, Any], actual: dict[str, str]) -> bool:
    for col, want in expected.items():
        if want == "" or want is None:
            continue
        got = actual.get(col, "")
        if _normalize_verify(want) != _normalize_verify(got):
            return False
    return True


def write_vip_journal_result(
    google_client,
    call: dict,
    verdict_data: dict,
    *,
    spreadsheet_id: str | None = None,
    managers: list[dict] | None = None,
) -> dict:
    """Запис одного дзвінка в журнал. Повертає статус-словник.

    Успіх: {"ok": True, "status": "Записано", "row": N, "analysis_id": ..., ...}
    Дедуп: {"ok": True, "status": "Записано", "duplicate": True, ...}
    Помилка: {"ok": False, "error": "..."}.
    """
    _ = spreadsheet_id  # завжди VIP_JOURNAL_SHEET_ID за ТЗ
    try:
        call_type = resolve_journal_call_type(
            call.get("journal_call_type")
            or call.get("vip_call_type")
            or verdict_data.get("call_type")
        )
        if not call_type:
            raise VipJournalError(
                "Невідомий тип дзвінка (очікується short або friendly з вибору аналізатора)."
            )
        route = resolve_project_route(call.get("project"))
        client_id = str(call.get("client_id") or "").strip()
        if not client_id:
            raise VipJournalError("Обов'язкове поле client_id порожнє.")
        call_date = _parse_ua_date(call.get("call_date"))
        if call_date is None:
            raise VipJournalError("Обов'язкове поле call_date порожнє.")
        check_date = _parse_ua_date(
            call.get("check_date") or call.get("listen_date")
        ) or journal_today()

        analysis_id = str(call.get("analysis_id") or "").strip() or make_analysis_id(
            call, call_type
        )
        existing = get_existing_write(analysis_id)
        if existing and existing.get("row"):
            return {
                "ok": True,
                "status": "Записано",
                "duplicate": True,
                "analysis_id": analysis_id,
                "row": int(existing["row"]),
                "sheet_title": existing.get("sheet_title") or route["title"],
                "sheet_id": existing.get("sheet_id") or route["sheet_id"],
                "call_type": call_type,
                "is_critical_fail": bool(verdict_data.get("is_critical_fail")),
                "critical_reasons": list(verdict_data.get("critical_reasons") or []),
            }

        if managers is None:
            managers = load_journal_managers(google_client)
        manager_row = resolve_manager_from_directory(
            managers,
            project_key=route["key"],
            manager_name=str(call.get("ret_manager") or call.get("manager") or ""),
            login=str(call.get("manager_login") or call.get("login") or ""),
        )
        manager_name = clean_sheet_cell(manager_row.get("manager"))
        tl_name = clean_sheet_cell(manager_row.get("tl"))

        if call_type == VIP_JOURNAL_CALL_TYPE_SHORT:
            scores = extract_short_scores(verdict_data)
            payload = build_short_row_payload(
                client_id=client_id,
                call_date=call_date,
                manager=manager_name,
                tl=tl_name,
                scores=scores,
                check_date=check_date,
            )
            id_col = "A"
            verify_cols = list(payload.keys())
        else:
            scores = extract_friendly_scores(verdict_data)
            payload = build_friendly_row_payload(
                client_id=client_id,
                call_date=call_date,
                manager=manager_name,
                tl=tl_name,
                scores=scores,
                check_date=check_date,
            )
            id_col = "N"
            verify_cols = list(payload.keys())

        with _WRITE_LOCK:
            worksheet = _open_project_worksheet(google_client, route)
            # Колонка ID клієнта: A=1, N=14
            id_col_index = 1 if id_col == "A" else 14
            col_values = sheets_retry(worksheet.col_values, id_col_index)
            row = find_next_journal_row(col_values, start_row=int(route["start_row"]))

            # Резерв рядка: спочатку ID, щоб паралельний запуск не взяв той самий.
            sheets_retry(
                worksheet.update,
                range_name=_a1(id_col, row),
                values=[[payload[id_col]]],
                value_input_option="USER_ENTERED",
            )
            # Перевірка резерву
            reserved = sheets_retry(worksheet.acell, _a1(id_col, row)).value
            if _normalize_verify(reserved) != _normalize_verify(payload[id_col]):
                # Хтось перехопив — шукаємо далі
                col_values = sheets_retry(worksheet.col_values, id_col_index)
                row = find_next_journal_row(col_values, start_row=int(route["start_row"]))
                sheets_retry(
                    worksheet.update,
                    range_name=_a1(id_col, row),
                    values=[[payload[id_col]]],
                    value_input_option="USER_ENTERED",
                )

            rest = {k: v for k, v in payload.items() if k != id_col}
            _write_cells(worksheet, row, rest)

            actual = _read_cells(worksheet, row, verify_cols)
            if not _payload_matches(payload, actual):
                raise VipJournalError(
                    f"Верифікація запису не пройшла (рядок {row}, {route['title']}/{call_type})."
                )

            mapping = {
                "spreadsheet_id": VIP_JOURNAL_SHEET_ID,
                "sheet_id": route["sheet_id"],
                "sheet_title": route["title"],
                "call_type": call_type,
                "row": row,
                "project": route["key"],
                "written_at": datetime.now(ZoneInfo(VIP_JOURNAL_TZ)).isoformat(),
                "is_critical_fail": bool(verdict_data.get("is_critical_fail")),
                "critical_reasons": list(verdict_data.get("critical_reasons") or []),
            }
            remember_write(analysis_id, mapping)

        return {
            "ok": True,
            "status": "Записано",
            "duplicate": False,
            "analysis_id": analysis_id,
            "row": row,
            "sheet_title": route["title"],
            "sheet_id": route["sheet_id"],
            "call_type": call_type,
            "is_critical_fail": bool(verdict_data.get("is_critical_fail")),
            "critical_reasons": list(verdict_data.get("critical_reasons") or []),
        }
    except VipJournalError as exc:
        logger.warning("VIP journal validation/write blocked: %s", exc)
        return {"ok": False, "error": str(exc), "status": "Помилка запису"}
    except Exception as exc:
        logger.exception("VIP journal write failed")
        return {"ok": False, "error": str(exc), "status": "Помилка запису"}
