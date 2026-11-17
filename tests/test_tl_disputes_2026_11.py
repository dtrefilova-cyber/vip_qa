"""Регресія оскаржень ТЛ 11–16.11.2026."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "tl_disputes_2026_11.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))


def _score_case(case: dict) -> dict:
    from core.vip_friendly_scoring import score_vip_friendly_call
    from core.vip_short_scoring import score_vip_short_call

    call = {**case["call"], "qa_comment": case["qa_comment"]}
    if case["call_type"] == "vip_friendly":
        return score_vip_friendly_call(case["facts"], call, case["gpt_transcript"])
    return score_vip_short_call(
        case["facts"],
        call,
        case["gpt_transcript"],
        case["deepgram_transcript"],
    )


@pytest.mark.parametrize("case", CASES, ids=[str(case["client_id"]) for case in CASES])
def test_tl_dispute_expected_scores(case):
    result = _score_case(case)
    by_key = {item["key"]: item["points"] for item in result["criteria"]}
    for key, points in case["expected_scores"].items():
        assert by_key[key] == points, (case["client_id"], key, by_key[key], points)
    if case["expected_total"] is not None:
        assert result["total_score"] == case["expected_total"]
    assert result["is_critical_fail"] == case["expected_critical"]


def test_deposit_bonus_phrase_counts():
    from core.vip_friendly_scoring import _DEPOSIT_BONUS, ground_bonus_offer

    phrase = "на Pure Extedy включити спіни. Там депозит 800 гривень, 40 обертів, ставочка по 2 гривні"
    assert _DEPOSIT_BONUS.search("депозит 800 гривень")
    grounded = ground_bonus_offer(
        {"first_deposit_bonus_quote": phrase, "terms_stated": {}},
        f"Менеджер: {phrase}",
    )
    assert grounded["deposit_bonus_offered_first"] is True
    friendly = next(case for case in CASES if case["client_id"] == "7738120")
    result = _score_case(friendly)
    bonus = next(item for item in result["criteria"] if item["key"] == "bonus_offer")
    assert bonus["points"] == 5.0


def test_client_name_is_not_time_of_day():
    from core.vip_short_scoring import repair_obvious_contact

    evening = repair_obvious_contact(
        {"contact": {}},
        "Менеджер: Вітаю вас. Доброго вечора. Це Роміло",
    )
    assert not evening["contact"].get("used_client_name")
    named = repair_obvious_contact(
        {"contact": {}},
        "Менеджер: Доброго дня, Михайло",
    )
    assert named["contact"]["used_client_name"] is True


def test_project_asr_variants_and_flags():
    from core.vip_short_scoring import repair_obvious_contact, score_vip_short_call

    bet_kings = repair_obvious_contact(
        {"contact": {}},
        "Менеджер: Ваші планети Ростайту Bet Kings",
        call={"project": "betking"},
    )
    assert bet_kings["contact"]["named_project"] is True

    mismatch = repair_obvious_contact(
        {"contact": {"named_project": True, "project_quote": "з сайту Vegas"}},
        "Менеджер: Софія, я ваш менеджер, з сайту Vegas.",
        call={"project": "betking"},
    )
    assert mismatch["contact"]["named_project"] is False
    assert "project_mismatch" in mismatch["_review_flags"]

    dialogue = "Менеджер: Доброго дня, Андрій. сет у батьківах. Маєте пару хвилин?"
    scored = score_vip_short_call(
        {"contact": {}},
        {"project": "betking"},
        dialogue,
    )
    assert "project_unclear" in scored["review_flags"]
    contact = next(item for item in scored["criteria"] if item["key"] == "contact")
    assert contact["points"] == 5.0


def test_tsey_dima_counts_as_manager_intro():
    from core.vip_short_scoring import repair_obvious_contact

    facts = repair_obvious_contact(
        {"contact": {}},
        "Менеджер: Та цей діма в мене це зручно",
        call={"ret_manager": "Шмалько Дмитро", "project": "betking"},
    )
    assert facts["contact"]["manager_introduced_self"] is True


def test_client_requested_call_skips_availability():
    from core.vip_short_scoring import score_vip_short_call

    dialogue = "Менеджер: Сергій, доброго дня. Мене звати Таня, сайту 777."
    result = score_vip_short_call(
        {
            "contact": {
                "greeted": True,
                "used_client_name": True,
                "named_project": True,
                "availability_check_done": False,
                "availability_check_relevant": True,
            }
        },
        {"project": "777", "qa_comment": "по запиту"},
        dialogue,
    )
    contact = next(item for item in result["criteria"] if item["key"] == "contact")
    assert contact["points"] == 5.0
    assert any("запитом" in reason for reason in contact["reasons"])


def test_callback_with_date_is_d14():
    from core.vip_short_scoring import score_vip_short_call

    result = score_vip_short_call(
        {
            "slip_handling": {
                "proposed_callback": True,
                "specified_concrete_time": True,
                "confirmed_agreement_or_clear_refusal": True,
            }
        },
        {"project": "betking"},
        "Менеджер: Добре, наберу у п'ятницю.\nКлієнт: Добре.",
    )
    closing = next(item for item in result["criteria"] if item["key"] == "closing")
    assert closing["points"] == 5.0
    assert any(reason.startswith("Д14:") for reason in closing["reasons"])


def test_open_contact_with_wish_without_thanks():
    from core.vip_short_scoring import repair_obvious_closing

    facts = repair_obvious_closing(
        {"closing": {}},
        "Менеджер: Будемо тоді на зв'язку. Бажаю вам тихої ночі.",
    )
    assert facts["closing"]["thanked_and_left_contact_open"] is True


def test_ignored_exit_on_2443983_is_critical_zero():
    case = next(item for item in CASES if item["client_id"] == "2443983")
    result = _score_case(case)
    assert result["is_critical_fail"] is True
    assert result["total_score"] == 0.0
    slip = next(item for item in result["criteria"] if item["key"] == "slip_handling")
    assert slip["points"] == 0.0


def test_low_quality_latin_slip_is_not_a_slip():
    from core.vip_short_scoring import score_vip_short_call

    dialogue = (
        "Менеджер: [0:04] Юрій, добрий вечір. Маєте хвилинку?\n"
        "Клієнт: [0:12] [низька якість розпізнавання] Talk to later.\n"
        "Менеджер: [0:20] Як справи?"
    )
    result = score_vip_short_call(
        {
            "slip_handling": {
                "client_attempted_to_end_call": True,
                "evidence": ["[0:12] Клієнт: Talk to later."],
            }
        },
        {"project": "betking"},
        dialogue,
    )
    slip = next(item for item in result["criteria"] if item["key"] == "slip_handling")
    assert slip["points"] == 10.0
    assert "slip_unclear_asr" in result["review_flags"]
