"""Google Sheets: підключення, VIP MANAGERS/RESULTS, presence heartbeat."""

from __future__ import annotations

import socket
import time

import gspread
import requests.exceptions
import streamlit as st
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, WorksheetNotFound

PRESENCE_SHEET_NAME = "ACTIVE_USERS"
PRESENCE_HEADERS = [
    "session_id",
    "qa_manager",
    "dept",
    "call_type",
    "last_seen",
    "status",
]


def sheets_retry(func, *args, **kwargs):
    """Повторює запит до Sheets при 429 і мережевих помилках."""
    delay = 2
    last_error = None
    retryable_codes = (
        "429",
        "500",
        "502",
        "503",
        "504",
        "UNAVAILABLE",
        "CONNECTION",
    )
    for attempt in range(5):
        try:
            return func(*args, **kwargs)
        except APIError as exc:
            last_error = exc
            error_str = str(exc)
            is_retryable = any(code in error_str for code in retryable_codes)
            if not is_retryable or attempt >= 4:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60)
        except (
            socket.timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as exc:
            last_error = exc
            if attempt >= 4:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 30)
    if last_error:
        raise last_error


def is_google_sheets_rate_limit_error(exc) -> bool:
    message = str(exc or "").lower()
    return (
        "429" in message
        or "quota exceeded" in message
        or "rate limit" in message
        or "read requests per minute" in message
    )


def describe_google_sheets_error(exc) -> str:
    if is_google_sheets_rate_limit_error(exc):
        return (
            "Перевищено ліміт Google Sheets API (429 — занадто багато read-запитів). "
            "Зачекайте 1–2 хвилини й повторіть."
        )
    message = str(exc or "").strip()
    lowered = message.lower()
    if "403" in message or "permission" in lowered or "forbidden" in lowered:
        return (
            f"{message}. Перевірте, що service account має права редактора "
            "на таблицю."
        )
    return message or "Невідома помилка Google Sheets"


@st.cache_resource(show_spinner=False)
def connect_google():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope,
    )
    return gspread.authorize(creds)


def find_next_row(sheet, start_row=1, key_column=1):
    """Знаходить перший вільний рядок, починаючи зі start_row."""
    try:
        column_values = sheets_retry(sheet.col_values, key_column)
        row = start_row
        while row <= len(column_values):
            value = column_values[row - 1] if row - 1 < len(column_values) else ""
            if not str(value).strip():
                return row
            row += 1
        return max(start_row, len(column_values) + 1)
    except Exception:
        return start_row


def get_or_create_presence_sheet(workbook):
    try:
        return workbook.worksheet(PRESENCE_SHEET_NAME)
    except WorksheetNotFound:
        sheet = workbook.add_worksheet(
            PRESENCE_SHEET_NAME,
            rows=200,
            cols=len(PRESENCE_HEADERS),
        )
        sheets_retry(
            sheet.update,
            "A1:F1",
            [PRESENCE_HEADERS],
            value_input_option="RAW",
        )
        return sheet


def upsert_user_presence(
    google_client,
    log_sheet_id,
    session_id,
    qa_manager,
    dept="",
    call_type="",
    status="online",
):
    from datetime import datetime

    workbook = google_client.open_by_key(log_sheet_id)
    sheet = get_or_create_presence_sheet(workbook)
    if not sheet.row_values(1):
        sheets_retry(
            sheet.update,
            "A1:F1",
            [PRESENCE_HEADERS],
            value_input_option="RAW",
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row_data = [
        session_id,
        qa_manager or "",
        dept or "",
        call_type or "",
        now,
        status,
    ]
    rows = sheet.get_all_values()
    for row_index, row in enumerate(rows[1:], start=2):
        if row and row[0] == session_id:
            sheets_retry(
                sheet.update,
                f"A{row_index}:F{row_index}",
                [row_data],
                value_input_option="RAW",
            )
            return row_index

    next_row = find_next_row(sheet, start_row=2, key_column=1)
    sheets_retry(
        sheet.update,
        f"A{next_row}:F{next_row}",
        [row_data],
        value_input_option="RAW",
    )
    return next_row


def load_active_users(google_client, log_sheet_id, ttl_seconds=180):
    from datetime import datetime

    try:
        workbook = google_client.open_by_key(log_sheet_id)
        sheet = workbook.worksheet(PRESENCE_SHEET_NAME)
    except WorksheetNotFound:
        return []
    except Exception:
        return []

    rows = sheet.get_all_values()[1:]
    now = datetime.now()
    active = []
    for row in rows:
        if not row or not row[0].strip():
            continue
        padded = row + [""] * (len(PRESENCE_HEADERS) - len(row))
        session_id, qa_manager, dept, call_type, last_seen, status = padded[:6]
        try:
            seen_at = datetime.strptime(last_seen.strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        age_seconds = (now - seen_at).total_seconds()
        if age_seconds > ttl_seconds:
            continue
        active.append(
            {
                "session_id": session_id,
                "qa_manager": qa_manager,
                "dept": dept,
                "call_type": call_type,
                "last_seen": last_seen,
                "status": status or "online",
                "age_seconds": int(age_seconds),
            }
        )
    active.sort(key=lambda item: item["last_seen"], reverse=True)
    return active


def load_vip_short_managers(google_client, spreadsheet_id, worksheet_name="MANAGERS"):
    """Зчитує PROJECT/TL/MANAGER з аркуша MANAGERS таблиці VIP короткі, з рядка 2."""
    worksheet = google_client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    values = sheets_retry(worksheet.get_all_values)

    rows = []
    for row in values[1:]:
        project = row[0].strip() if len(row) > 0 else ""
        tl = row[1].strip() if len(row) > 1 else ""
        manager = row[2].strip() if len(row) > 2 else ""
        if not manager:
            continue
        rows.append({"project": project, "tl": tl, "manager": manager})
    return rows


VIP_RESULT_CELL_COLORS = {
    "GREEN": {"red": 0.71, "green": 0.88, "blue": 0.65},
    "RED": {"red": 0.96, "green": 0.6, "blue": 0.6},
}


def format_vip_short_comment_for_sheet(verdict_data):
    """Legacy alias — supports old GREEN/RED and new score payloads."""
    return format_vip_score_comment_for_sheet(verdict_data)


def format_vip_score_comment_for_sheet(verdict_data):
    parts = []
    if verdict_data.get("is_critical_fail"):
        crit = "; ".join(verdict_data.get("critical_reasons") or []) or "критична помилка"
        parts.append(f"КРИТИЧНА ПОМИЛКА: {crit}")
    for item in verdict_data.get("criteria") or []:
        key = item.get("label") or item.get("key") or "criterion"
        pts = item.get("points")
        mx = item.get("max_points")
        line = f"— {key}: {pts:g}/{mx:g}"
        reasons = [str(r).strip() for r in (item.get("reasons") or []) if str(r).strip()]
        if reasons:
            line += f" ({'; '.join(reasons)})"
        parts.append(line)
    for reason in verdict_data.get("verdict_reasons") or []:
        text = str(reason or "").strip()
        if text and text not in "\n".join(parts):
            parts.append(f"— {text}")
    for flag in verdict_data.get("review_flags") or []:
        text = str(flag or "").strip()
        if text:
            parts.append(f"На перевірку ТЛ: {text}")
    return "\n".join(parts) if parts else "— Дзвінок без зауважень."


def format_vip_result_cell(row_data) -> str:
    """Значення для колонки RESULT — бали, без GREEN/RED заливки."""
    total = row_data.get("total_score")
    max_score = row_data.get("max_score")
    if total is None and row_data.get("result"):
        return str(row_data.get("result"))
    try:
        if total is not None and max_score is not None:
            return f"{float(total):g}/{float(max_score):g}"
        if total is not None:
            return f"{float(total):g}"
    except (TypeError, ValueError):
        pass
    return str(row_data.get("result") or "")


def append_vip_short_result(google_client, spreadsheet_id, row_data, worksheet_name="RESULTS"):
    worksheet = google_client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    next_row = find_next_row(worksheet, start_row=2, key_column=4)

    # A–G як у чинному аркуші RESULTS: F = бали (не заливка GREEN/RED)
    result_cell = format_vip_result_cell(row_data)
    values = [
        row_data.get("project", ""),
        row_data.get("tl", ""),
        row_data.get("manager", ""),
        row_data.get("client_id", ""),
        row_data.get("call_date", ""),
        result_cell,
        row_data.get("comment", ""),
    ]
    try:
        sheets_retry(worksheet.update, f"A{next_row}:G{next_row}", [values])
    except Exception as e:
        return str(e)

    # Скидаємо заливку RESULT — у комірці мають бути бали текстом/числом
    try:
        sheets_retry(
            worksheet.format,
            f"F{next_row}",
            {
                "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                "horizontalAlignment": "CENTER",
            },
        )
    except Exception:
        pass
    return True
