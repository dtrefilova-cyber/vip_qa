"""Unit tests for VIP deterministic scoring (Короткий 90 сек + Friendly)."""

from core.vip_friendly_scoring import (
    CallToActionFacts,
    FriendlyDevelopmentFacts,
    build_perfect_friendly_facts,
    score_call_to_action,
    score_friendly_development,
    score_vip_friendly,
)
from core.vip_scoring_common import (
    ContactFacts,
    Objection,
    ObjectionHandling,
    PrepFacts,
    SharedCallContext,
    score_contact,
    score_prep,
)
from core.vip_short_scoring import (
    SlipCriticalFacts,
    SlipHandlingFacts,
    VipShort90sFactsBundle,
    build_perfect_short90s_facts,
    score_slip_handling,
    score_vip_short_90s,
)


def test_contact_all_present():
    f = ContactFacts(
        greeted=True,
        used_client_name=True,
        named_project=True,
        availability_check_relevant=False,
        availability_check_done=False,
    )
    assert score_contact(f).points == 5.0


def test_contact_missing_one():
    f = ContactFacts(
        greeted=True,
        used_client_name=False,
        named_project=True,
        availability_check_relevant=False,
    )
    assert score_contact(f).points == 2.5


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


def test_slip_critical_violation_zeroes_whole_call():
    facts = build_perfect_short90s_facts()
    facts.slip_critical = SlipCriticalFacts(
        continued_pitch_after_client_said_cannot_talk=True
    )
    result = score_vip_short_90s(facts, SharedCallContext())
    assert result.is_critical_fail is True
    assert result.total_score == 0.0


def test_call_to_action_military_skips_reason_question():
    f = CallToActionFacts(
        asked_deposit_today=True,
        started_with_bonus_before_deposit_intent=False,
        first_answer_positive=False,
        asked_deposit_tomorrow=True,
        second_answer_positive=False,
        client_is_military=True,
        asked_open_reason_if_declined=False,
    )
    assert score_call_to_action(f).points == 10.0


def test_friendly_development_full_signals():
    f = FriendlyDevelopmentFacts(
        asked_relevant_personal_questions=True,
        followed_up_on_client_answer=True,
        supported_client_initiated_topic=True,
        returned_to_personal_info_later=True,
    )
    assert score_friendly_development(f).points == 7.5


def test_vip_friendly_max_score_is_60():
    result = score_vip_friendly(build_perfect_friendly_facts(), SharedCallContext())
    assert result.max_score == 60.0
    assert result.total_score == 60.0


def test_ease_high_is_10():
    from core.vip_friendly_scoring import EaseFacts, EaseLevel, score_ease

    assert score_ease(EaseFacts(level=EaseLevel.HIGH, signals=[])).points == 10.0
    assert score_ease(EaseFacts(level=EaseLevel.HIGH, signals=[])).max_points == 10.0


def test_vip_short_90s_max_score_is_30():
    result = score_vip_short_90s(build_perfect_short90s_facts(), SharedCallContext())
    assert result.max_score == 30.0
    assert result.total_score == 30.0
