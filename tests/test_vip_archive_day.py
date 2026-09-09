"""Лічильники/архів: день за check_date, не за датою дзвінка."""

from vip_archive import _row_belongs_to_day, _row_day_iso, iso_check_date


def test_iso_check_date_formats():
    assert iso_check_date("09.09.2026") == "2026-09-09"
    assert iso_check_date("2026-09-09") == "2026-09-09"
    assert iso_check_date("2026-09-09T12:00:00+03:00") == "2026-09-09"


def test_row_day_prefers_check_date_column():
    row = {
        "call_date": "2026-08-31",
        "check_date": "2026-09-09",
        "created_at": "2026-09-09T10:00:00+03:00",
    }
    assert _row_day_iso(row) == "2026-09-09"
    assert _row_belongs_to_day(row, "2026-09-09")
    assert not _row_belongs_to_day(row, "2026-08-31")


def test_row_day_from_debug_check_date():
    row = {
        "call_date": "2026-08-31",
        "debug_data": {"call": {"check_date": "09.09.2026"}},
    }
    assert _row_day_iso(row) == "2026-09-09"
    assert _row_belongs_to_day(row, "2026-09-09")


def test_row_day_falls_back_to_call_date():
    row = {"call_date": "2026-08-31", "verdict": "green"}
    assert _row_day_iso(row) == "2026-08-31"
    assert _row_belongs_to_day(row, "2026-08-31")
