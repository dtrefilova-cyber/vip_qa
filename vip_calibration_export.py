"""Калібрувальний експорт: початкові бали АІ з vip_short_call_logs.

Бали й транскрипт беруться з одного й того самого лога. Колонки журналу,
які TL може перезаписати, джерелом початкової оцінки не є.
Живий запис у таблицю цей модуль не робить.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from io import BytesIO
from typing import Any

MISSING_AI_SCORE = "Немає початкової оцінки АІ"

_NAME_RE = re.compile(
    r"(?:клієнт|клиент)\s*[:\-—]?\s*([А-ЯІЇЄҐA-Z][а-яіїєґ'’\-]{2,})",
    re.IGNORECASE,
)


def _norm_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    return digits or text


def _norm_manager(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("ё", "е").split())


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
        except ValueError:
            continue
    return None


def _as_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, 12, 0, tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        day = _as_date(value)
        if day is None:
            return None
        return datetime(day.year, day.month, day.day, 12, 0, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _criteria_list(log: dict) -> list:
    raw = _parse_json(log.get("criteria_scores"))
    if isinstance(raw, list) and raw:
        return raw
    debug = _parse_json(log.get("debug_data"))
    if not isinstance(debug, dict):
        return []
    score = debug.get("score") if isinstance(debug.get("score"), dict) else {}
    nested = score.get("criteria") if isinstance(score, dict) else None
    if isinstance(nested, list) and nested:
        return nested
    debug_criteria = debug.get("criteria")
    return debug_criteria if isinstance(debug_criteria, list) else []


def scores_from_log(log: dict | None) -> dict[str, float] | None:
    """Початкові бали АІ з лога. Порожній список — оцінки немає."""
    if not log:
        return None
    found: dict[str, float] = {}
    for item in _criteria_list(log):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        points = item.get("points")
        if not key or points is None or points == "":
            continue
        try:
            found[key] = float(points)
        except (TypeError, ValueError):
            continue
    return found or None


def transcript_from_log(log: dict | None) -> str:
    if not log:
        return ""
    for key in ("transcript", "gpt_transcript", "deepgram_transcript"):
        text = log.get(key)
        if isinstance(text, str) and text.strip():
            return text
    debug = _parse_json(log.get("debug_data"))
    if isinstance(debug, dict):
        for key in ("transcript", "gpt_transcript", "deepgram_transcript"):
            text = debug.get(key)
            if isinstance(text, str) and text.strip():
                return text
    return ""


def _log_id(log: dict) -> str:
    return str(log.get("id") or "").strip()


def _id_matches(wanted: str, log: dict) -> bool:
    have = _log_id(log)
    if not wanted or not have:
        return False
    return have == wanted or have.startswith(wanted) or wanted.startswith(have)


def _same_call(journal: dict, log: dict) -> bool:
    if _norm_id(journal.get("client_id")) != _norm_id(log.get("client_id")):
        return False
    journal_date = _as_date(journal.get("call_date"))
    log_date = _as_date(log.get("call_date"))
    if journal_date and log_date and journal_date != log_date:
        return False
    journal_manager = _norm_manager(journal.get("manager") or journal.get("ret_manager"))
    log_manager = _norm_manager(log.get("ret_manager") or log.get("manager"))
    if journal_manager and log_manager and journal_manager != log_manager:
        return False
    journal_type = str(journal.get("call_type") or "").strip()
    log_type = str(log.get("call_type") or "").strip()
    if journal_type and log_type and {journal_type, log_type} <= {"short", "friendly"} and journal_type != log_type:
        return False
    return True


def _analysis_time(log: dict) -> datetime | None:
    for key in ("created_at", "analyzed_at", "analysis_time", "check_date"):
        moment = _as_dt(log.get(key))
        if moment is not None:
            return moment
    return None


def select_log_for_journal_row(journal: dict, logs: list[dict] | None) -> dict | None:
    """Один лог на рядок журналу: client_id + дата + менеджер, потім найближчий час аналізу.

    Якщо після цього лишається кілька логів, береться той, чий row_ref дорівнює номеру рядка.
    log_id на рядку використовується лише коли цей лог належить тому самому дзвінку.
    Бал і транскрипт далі читаються тільки з повернутого лога.
    """
    rows = [log for log in (logs or []) if isinstance(log, dict)]
    candidates = [log for log in rows if _same_call(journal, log)]
    wanted = str(journal.get("log_id") or "").strip()
    by_id = [log for log in rows if wanted and _id_matches(wanted, log)]
    pool = list(candidates)
    if not pool and len(by_id) == 1 and _norm_id(by_id[0].get("client_id")) == _norm_id(journal.get("client_id")):
        return by_id[0]
    if not pool:
        return None
    target = _as_dt(journal.get("analysis_time") or journal.get("check_date"))
    if target is not None and len(pool) > 1:
        known = []
        for log in pool:
            moment = _analysis_time(log)
            if moment is None:
                continue
            known.append((abs((moment - target).total_seconds()), log))
        if known:
            best = min(item[0] for item in known)
            pool = [log for delta, log in known if delta == best]
    if len(pool) > 1:
        row = journal.get("row")
        if row is not None and str(row).strip():
            exact = [log for log in pool if str(log.get("row_ref") or "") == str(row)]
            if exact:
                pool = exact
    if wanted:
        preferred = [log for log in pool if _id_matches(wanted, log)]
        if len(preferred) == 1:
            return preferred[0]
    return pool[0]


def calibration_record(journal: dict, logs: list[dict] | None) -> dict[str, Any]:
    """Один рядок калібрування. Колонки балів журналу не читаються."""
    log = select_log_for_journal_row(journal, logs)
    scores = scores_from_log(log)
    return {
        "client_id": _norm_id(journal.get("client_id")) or str(journal.get("client_id") or ""),
        "row": journal.get("row"),
        "log_id": _log_id(log) if log else "",
        "scores": scores,
        "transcript": transcript_from_log(log),
        "ai_score_status": "" if scores else MISSING_AI_SCORE,
    }


def build_calibration_rows(journal_rows: list[dict], logs: list[dict] | None) -> list[dict[str, Any]]:
    return [calibration_record(row, logs) for row in journal_rows]


_WORKBOOK_FIELDS = (
    "contact",
    "slip_handling",
    "prep",
    "closing",
    "friendly_development",
    "personal_approach",
    "call_to_action",
    "bonus_offer",
    "ease",
)


def build_calibration_workbook(journal_rows: list[dict], logs: list[dict] | None) -> bytes:
    """xlsx у пам'яті. У файл не пише і в Google Sheets не ходить."""
    from openpyxl import Workbook

    records = build_calibration_rows(journal_rows, logs)
    book = Workbook()
    sheet = book.active
    sheet.title = "Калібрування"
    headers = ["client_id", "row", "log_id", "ai_score_status", *_WORKBOOK_FIELDS, "transcript"]
    sheet.append(headers)
    for record in records:
        scores = record["scores"] or {}
        sheet.append(
            [
                record["client_id"],
                record["row"] if record["row"] is not None else "",
                record["log_id"],
                record["ai_score_status"],
                *[scores.get(field, "") for field in _WORKBOOK_FIELDS],
                record["transcript"],
            ]
        )
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _client_names(log: dict) -> set[str]:
    names = set()
    explicit = str(log.get("client_name") or "").strip()
    if explicit:
        names.add(explicit.casefold())
    for match in _NAME_RE.finditer(transcript_from_log(log)):
        names.add(match.group(1).casefold())
    return names


def client_id_storage_evidence(log: dict, logs: list[dict] | None) -> dict[str, Any]:
    """Чи лежить лог під client_id іншої розмови. Рядки не змінює."""
    snapshot = {
        "id": log.get("id"),
        "client_id": log.get("client_id"),
        "client_name": log.get("client_name"),
    }
    own_names = _client_names(log)
    client_id = _norm_id(log.get("client_id"))
    siblings = []
    for other in logs or []:
        if not isinstance(other, dict) or other is log:
            continue
        if _log_id(other) == _log_id(log):
            continue
        if _norm_id(other.get("client_id")) != client_id:
            continue
        other_names = _client_names(other)
        if own_names and other_names and own_names.isdisjoint(other_names):
            siblings.append({"log_id": _log_id(other), "names": sorted(other_names)})
    if log.get("id") != snapshot["id"] or log.get("client_id") != snapshot["client_id"]:
        raise RuntimeError("evidence changed the log")
    return {
        "log_id": _log_id(log),
        "client_id": client_id,
        "names_in_transcript": sorted(own_names),
        "stored_under_other_clients_id": bool(siblings),
        "siblings": siblings,
        "changed": False,
    }
