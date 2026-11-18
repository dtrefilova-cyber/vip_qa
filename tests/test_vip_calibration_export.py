"""Калібрування бере бали й транскрипт з одного лога, не з колонок журналу."""

from __future__ import annotations

from datetime import date
from io import BytesIO

from openpyxl import load_workbook

from vip_calibration_export import (
    MISSING_AI_SCORE,
    build_calibration_workbook,
    calibration_record,
    client_id_storage_evidence,
    select_log_for_journal_row,
)

CALL_DATE = date(2026, 11, 10)
YURIY_ID = "98970b39-1111-4111-8111-111111111111"
VITALIY_ID = "71ff5601-2222-4222-8222-222222222222"


def _criteria(contact: float, **extra: float) -> list[dict]:
    scores = {"contact": contact, "slip_handling": 10, "prep": 7.5, "closing": 5, **extra}
    return [{"key": key, "points": value} for key, value in scores.items()]


def _log(**kwargs) -> dict:
    row = {
        "id": kwargs.get("id", "log-1"),
        "client_id": kwargs.get("client_id", "100"),
        "call_date": kwargs.get("call_date", CALL_DATE.isoformat()),
        "ret_manager": kwargs.get("manager", "Клименко Артем"),
        "call_type": kwargs.get("call_type", "short"),
        "created_at": kwargs.get("created_at", "2026-11-17T09:00:00+00:00"),
        "criteria_scores": kwargs.get("criteria_scores", _criteria(5)),
        "gpt_transcript": kwargs.get("transcript", "Менеджер: добрий день"),
        "row_ref": kwargs.get("row_ref", ""),
        "client_name": kwargs.get("client_name", ""),
    }
    return row


def _journal(**kwargs) -> dict:
    return {
        "client_id": kwargs.get("client_id", "100"),
        "call_date": kwargs.get("call_date", CALL_DATE),
        "manager": kwargs.get("manager", "Клименко Артем"),
        "call_type": kwargs.get("call_type", "short"),
        "analysis_time": kwargs.get("analysis_time", "2026-11-17T09:05:00+00:00"),
        "row": kwargs.get("row", 12),
        "log_id": kwargs.get("log_id", ""),
        "contact": kwargs.get("journal_contact", ""),
        "slip_handling": kwargs.get("journal_slip", ""),
    }


def test_log_id_scores_ignore_overwritten_journal_columns():
    log = _log(id="abc-6525629", client_id="6525629", criteria_scores=_criteria(2.5))
    journal = _journal(client_id="6525629", log_id="abc-6525629", journal_contact=5, journal_slip=0)
    record = calibration_record(journal, [log])
    assert record["scores"]["contact"] == 2.5
    assert record["scores"]["slip_handling"] == 10
    assert record["ai_score_status"] == ""
    assert record["transcript"] == log["gpt_transcript"]
    assert record["log_id"] == log["id"]


def test_listed_calls_with_log_id_are_not_missing():
    logs = []
    rows = []
    for client_id, contact in (
        ("6525629", 5),
        ("6679056", 2.5),
        ("7650112", 0),
        ("9286514", 5),
        ("9937145", 2.5),
    ):
        log_id = f"log-{client_id}"
        logs.append(
            _log(
                id=log_id,
                client_id=client_id,
                criteria_scores=_criteria(contact),
                transcript=f"розмова {client_id}",
            )
        )
        rows.append(
            _journal(
                client_id=client_id,
                log_id=log_id,
                journal_contact="",
                journal_slip="",
            )
        )
    book = load_workbook(BytesIO(build_calibration_workbook(rows, logs)))
    sheet = book["Калібрування"]
    header = [cell.value for cell in sheet[1]]
    status_col = header.index("ai_score_status") + 1
    contact_col = header.index("contact") + 1
    transcript_col = header.index("transcript") + 1
    seen = []
    for row in sheet.iter_rows(min_row=2, values_only=False):
        seen.append(row[0].value)
        assert row[status_col - 1].value in (None, "")
        assert row[contact_col - 1].value is not None
        assert MISSING_AI_SCORE not in str(row[transcript_col - 1].value)
    assert seen == ["6525629", "6679056", "7650112", "9286514", "9937145"]


def test_missing_phrase_only_when_the_log_has_no_scores():
    log = _log(id="log-empty", client_id="6525629", criteria_scores=[])
    journal = _journal(client_id="6525629", log_id="log-empty", journal_contact=5)
    record = calibration_record(journal, [log])
    assert record["scores"] is None
    assert record["ai_score_status"] == MISSING_AI_SCORE
    assert record["transcript"] == log["gpt_transcript"]


def test_same_log_supplies_score_and_transcript():
    yuriy = _log(
        id=YURIY_ID,
        client_id="5101635",
        manager="Клименко Артем",
        created_at="2026-11-17T09:00:00+00:00",
        row_ref="12",
        client_name="Юрій",
        criteria_scores=_criteria(5),
        transcript="Клієнт: Юрій слухає",
    )
    vitaliy = _log(
        id=VITALIY_ID,
        client_id="5101635",
        manager="Клименко Артем",
        created_at="2026-11-17T15:40:00+00:00",
        row_ref="40",
        client_name="Віталій",
        criteria_scores=_criteria(0),
        transcript="Клієнт: Віталій, інша розмова",
    )
    journal = _journal(
        client_id="5101635",
        manager="Клименко Артем",
        analysis_time="2026-11-17T09:02:00+00:00",
        row=12,
        log_id=VITALIY_ID,
        journal_contact=0,
    )
    record = calibration_record(journal, [vitaliy, yuriy])
    assert record["log_id"] == YURIY_ID
    assert record["scores"]["contact"] == 5
    assert "Юрій" in record["transcript"]
    assert "Віталій" not in record["transcript"]


def test_row_ref_breaks_a_tie():
    early = _log(id="first", created_at="2026-11-17T09:00:00+00:00", row_ref="4", criteria_scores=_criteria(5), transcript="перший")
    same = _log(id="second", created_at="2026-11-17T09:00:00+00:00", row_ref="9", criteria_scores=_criteria(0), transcript="другий")
    chosen = select_log_for_journal_row(
        _journal(analysis_time="2026-11-17T09:00:00+00:00", row=9),
        [early, same],
    )
    assert chosen["id"] == "second"
    record = calibration_record(_journal(analysis_time="2026-11-17T09:00:00+00:00", row=9), [early, same])
    assert record["scores"]["contact"] == 0
    assert record["transcript"] == "другий"


def test_71ff5601_evidence_does_not_change_the_row():
    yuriy = _log(
        id=YURIY_ID,
        client_id="5101635",
        client_name="Юрій",
        transcript="Клієнт: Юрій",
    )
    vitaliy = _log(
        id=VITALIY_ID,
        client_id="5101635",
        client_name="Віталій",
        transcript="Клієнт: Віталій, інша розмова",
    )
    before = (vitaliy["client_id"], vitaliy["id"], vitaliy["client_name"])
    evidence = client_id_storage_evidence(vitaliy, [yuriy, vitaliy])
    assert (vitaliy["client_id"], vitaliy["id"], vitaliy["client_name"]) == before
    assert evidence["changed"] is False
    assert evidence["stored_under_other_clients_id"] is True
    assert evidence["client_id"] == "5101635"
    assert evidence["names_in_transcript"] == ["віталій"]
    assert evidence["siblings"][0]["log_id"] == YURIY_ID
    assert evidence["siblings"][0]["names"] == ["юрій"]
