"""Unit tests for VIP deterministic scoring (synced with portal 79064ed)."""

from core.vip_friendly_scoring import (
    CallToActionFacts,
    EaseFacts,
    EaseLevel,
    FriendlyDevelopmentFacts,
    build_perfect_friendly_facts,
    score_call_to_action,
    score_ease,
    score_friendly_development,
    score_vip_friendly,
)
from core.vip_scoring_common import (
    ClosingFacts,
    ContactFacts,
    Objection,
    ObjectionHandling,
    PrepFacts,
    SharedCallContext,
    score_closing,
    score_contact,
    score_prep,
)
from core.vip_short_scoring import (
    SlipHandlingFacts,
    build_perfect_short90s_facts,
    score_slip_handling,
    score_vip_short_90s,
)


def test_contact_all_four_elements():
    f = ContactFacts(
        greeted=True,
        used_client_name=True,
        named_project=True,
        availability_check_relevant=True,
        availability_check_done=True,
    )
    assert score_contact(f).points == 5.0


def test_contact_missing_one():
    f = ContactFacts(
        greeted=True,
        used_client_name=False,
        named_project=True,
        availability_check_relevant=True,
        availability_check_done=True,
    )
    result = score_contact(f)
    assert result.points == 2.5
    assert any("ім'я клієнта" in r for r in result.reasons)


def test_messenger_without_manager_name_still_cuts_2_5():
    f = ContactFacts(
        greeted=False,
        used_client_name=False,
        named_project=False,
        availability_check_done=False,
        exception_prior_messenger_contact=True,
        manager_introduced_self=False,
    )
    result = score_contact(f)
    assert result.points == 2.5
    assert any("не назвав своє ім'я" in r for r in result.reasons)


def test_client_addresses_manager_by_name_keeps_contact_points():
    """Клієнт звернувся на ім'я — не зрізати 2.5, які інакше знімає месенджер без представлення."""
    from core.vip_scoring_common import _contact_messenger

    named = ContactFacts(
        greeted=False,
        used_client_name=False,
        named_project=False,
        availability_check_done=False,
        exception_prior_messenger_contact=True,
        manager_introduced_self=False,
        exception_client_recognized_manager=True,
    )
    assert score_contact(named).points == 5.0
    awarded = _contact_messenger(named)
    assert awarded is not None
    assert awarded[0] == 5.0

    still_cut = _contact_messenger(
        ContactFacts(
            exception_prior_messenger_contact=True,
            manager_introduced_self=False,
        )
    )
    assert still_cut is not None
    assert still_cut[0] == 2.5


def test_prompts_client_address_fulfills_contact():
    from prompts_vip_friendly import get_vip_friendly_analysis_prompt
    from prompts_vip_short import get_vip_contact_prompt, get_vip_short_90s_analysis_prompt

    sentence = (
        "Якщо клієнт звертається до менеджера на ім'я, «Встановлення контакту» виконано: "
        "не знижуй бал на 2,5 і постав exception_client_recognized_manager=true."
    )
    assert sentence in get_vip_short_90s_analysis_prompt()
    assert sentence in get_vip_contact_prompt()
    assert sentence in get_vip_friendly_analysis_prompt()


def test_contact_missing_names_all_elements():
    f = ContactFacts(
        greeted=False,
        used_client_name=False,
        named_project=False,
        availability_check_done=False,
    )
    result = score_contact(f)
    assert result.points == 0.0
    blob = " ".join(result.reasons)
    assert "привітання" in blob
    assert "ім'я клієнта" in blob
    assert "назва проєкту" in blob
    assert "перевірка зручності" in blob


def test_prep_no_objections_auto_max():
    f = PrepFacts(objections_present=False, objections=[])
    assert score_prep(f).points == 10.0


def test_prep_worst_of_multiple_objections():
    f = PrepFacts(
        objections_present=True,
        objections=[
            Objection(type="no_time", handling=ObjectionHandling.RESOLVED_WITH_CHECK),
            Objection(type="no_payout", handling=ObjectionHandling.FORMAL),
        ],
    )
    assert score_prep(f).points == 2.5


def test_slip_handling_all_done():
    f = SlipHandlingFacts(
        client_attempted_to_end_call=True,
        reason_stated_by_client=True,
        reason_clarified_by_manager=False,
        manager_reacted_appropriately=True,
        proposed_callback=True,
        specified_concrete_time=True,
        confirmed_agreement_or_clear_refusal=True,
        client_flatly_refused_any_callback=False,
    )
    assert score_slip_handling(f, SharedCallContext()).points == 10.0


def test_vip_friendly_max_score_is_57_5():
    result = score_vip_friendly(build_perfect_friendly_facts(), SharedCallContext())
    assert result.max_score == 57.5
    assert result.total_score == 57.5
    assert result.rubric_version == "v1_friendly_ease75"


def test_ease_high_is_7_5():
    assert score_ease(EaseFacts(level=EaseLevel.HIGH, signals=[])).points == 7.5
    assert score_ease(EaseFacts(level=EaseLevel.HIGH, signals=[])).max_points == 7.5


def test_vip_short_90s_max_score_is_30():
    result = score_vip_short_90s(build_perfect_short90s_facts(), SharedCallContext())
    assert result.max_score == 30.0
    assert result.total_score == 30.0


def test_friendly_development_full_signals():
    f = FriendlyDevelopmentFacts(
        asked_relevant_personal_questions=True,
        followed_up_on_client_answer=True,
        supported_client_initiated_topic=True,
        returned_to_personal_info_later=True,
        evidence=["Менеджер: як пройшли вихідні?", "Менеджер: а що плануєте?"],
    )
    assert score_friendly_development(f, "Менеджер: як пройшли вихідні?\nМенеджер: а що плануєте?").points == 7.5


def test_closing_missing_names_specific_element():
    f = ClosingFacts(
        asked_if_more_questions=True,
        said_goodbye=False,
        thanked_and_left_contact_open=True,
    )
    result = score_closing(f, SharedCallContext())
    assert result.points == 2.5
    assert any("прощання" in r for r in result.reasons)


def test_ai_models_registers_portal_tasks():
    from ai_models import VIP_FACT_TASKS, get_task_config

    assert "facts_vip_short_contact" in VIP_FACT_TASKS
    assert "facts_vip_friendly_cta" in VIP_FACT_TASKS
    cfg = get_task_config("facts_vip_friendly_bonus")
    assert cfg["registered"] is True
    assert cfg["model"]
