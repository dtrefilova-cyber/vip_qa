"""Тести форматування RESULT / Коментар для RESULTS FRIENDLY."""

from core.vip_scoring_common import CriterionScore
from google_sheets import format_comment_cell, format_result_cell


def test_format_result_cell():
    assert format_result_cell(46, 57.5, 80.0) == "46/57.5 (80%)"


def test_format_result_cell_whole_numbers():
    assert format_result_cell(57.5, 57.5, 100.0) == "57.5/57.5 (100%)"


def test_format_result_cell_friendly_max_60():
    assert format_result_cell(48, 60, 80.0) == "48/60 (80%)"


def test_format_comment_cell_includes_reasons_only_when_present():
    criteria = [
        CriterionScore("contact", 5.0, 5.0, []),
        CriterionScore("ease", 5.0, 7.5, ["помітні недоліки у комунікації"]),
    ]
    result = format_comment_cell(criteria)
    assert "Встановлення контакту: 5/5" in result
    assert "Невимушеність: 5/7.5 — помітні недоліки у комунікації" in result


def test_format_comment_cell_from_dicts():
    criteria = [
        {"key": "prep", "label": "Робота з запереченням (P.R.E.P.)", "points": 7.5, "max_points": 10, "reasons": ["без уточнення"]},
    ]
    result = format_comment_cell(criteria)
    assert "Робота з запереченням (P.R.E.P.): 7.5/10 — без уточнення" in result
