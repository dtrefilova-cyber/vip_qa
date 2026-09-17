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
    PREP_ALLOWED_POINTS,
    PrepFacts,
    SharedCallContext,
    score_contact,
    score_prep,
)
from core.vip_short_scoring import (
    SLIP_HANDLING_ALLOWED_POINTS,
    SlipCriticalFacts,
    SlipHandlingFacts,
    build_perfect_short90s_facts,
    evidence_quote_in_transcript,
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


def test_slip_handling_returns_2_5_when_barely_working():
    f = SlipHandlingFacts(
        client_attempted_to_end_call=True,
        reason_stated_by_client=True,
        reason_clarified_by_manager=False,
        manager_reacted_appropriately=False,
        proposed_callback=False,
        specified_concrete_time=False,
        confirmed_agreement_or_clear_refusal=False,
        client_flatly_refused_any_callback=False,
    )
    result = score_slip_handling(f, SharedCallContext())
    assert result.points == 2.5
    assert result.points in SLIP_HANDLING_ALLOWED_POINTS


def test_prep_formal_returns_2_5():
    f = PrepFacts(
        objections_present=True,
        objections=[Objection(type="no_desire", handling=ObjectionHandling.FORMAL)],
    )
    result = score_prep(f)
    assert result.points == 2.5
    assert result.points in PREP_ALLOWED_POINTS


def test_slip_and_prep_allowed_scale_includes_2_5():
    assert 2.5 in SLIP_HANDLING_ALLOWED_POINTS
    assert 2.5 in PREP_ALLOWED_POINTS
    assert SLIP_HANDLING_ALLOWED_POINTS == (0.0, 2.5, 5.0, 7.5, 10.0)
    assert PREP_ALLOWED_POINTS == (0.0, 2.5, 5.0, 7.5, 10.0)


def test_slip_critical_violation_zeroes_whole_call():
    facts = build_perfect_short90s_facts()
    quote = "Я зараз не можу говорити, передзвоніть пізніше"
    facts.slip_handling.client_attempted_to_end_call = True
    facts.slip_critical = SlipCriticalFacts(
        continued_pitch_after_client_said_cannot_talk=True,
        critical_evidence_quote=quote,
    )
    dialogue = f"Клієнт: {quote}\nМенеджер: Так, по бонусу сьогодні 45 спінів."
    result = score_vip_short_90s(facts, SharedCallContext(), dialogue=dialogue)
    assert result.is_critical_fail is True
    assert result.total_score == 0.0
    assert result.review_flags == []


def test_slip_critical_without_quote_does_not_zero():
    facts = build_perfect_short90s_facts()
    facts.slip_critical = SlipCriticalFacts(
        asked_irrelevant_questions=True,
        artificially_extended_call=True,
        critical_evidence_quote="",
    )
    dialogue = "Клієнт: Добрий день. Все гаразд. Дякую. До побачення."
    result = score_vip_short_90s(facts, SharedCallContext(), dialogue=dialogue)
    assert result.is_critical_fail is False
    assert result.total_score == 30.0
    assert result.review_flags


def test_slip_critical_quote_not_in_transcript_does_not_zero():
    facts = build_perfect_short90s_facts()
    facts.slip_critical = SlipCriticalFacts(
        continued_pitch_after_client_said_cannot_talk=True,
        critical_evidence_quote="Я зараз не можу говорити",
    )
    dialogue = "Клієнт: Давайте не будемо про це. Дякую. До побачення."
    result = score_vip_short_90s(facts, SharedCallContext(), dialogue=dialogue)
    assert evidence_quote_in_transcript("Я зараз не можу говорити", dialogue) is False
    assert result.is_critical_fail is False
    assert result.total_score == 30.0
    assert result.review_flags


def test_slip_critical_unrelated_quote_in_transcript_does_not_zero():
    facts = build_perfect_short90s_facts()
    quote = "Давайте не будемо про це"
    facts.slip_critical = SlipCriticalFacts(
        continued_pitch_after_client_said_cannot_talk=True,
        critical_evidence_quote=quote,
    )
    dialogue = f"Клієнт: {quote}. Не вийшло, то не вийшло."
    result = score_vip_short_90s(facts, SharedCallContext(), dialogue=dialogue)
    assert result.is_critical_fail is False
    assert result.review_flags


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
