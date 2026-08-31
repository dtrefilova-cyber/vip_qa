"""VIP «Короткий 90 сек» — бальна рубрика (макс. 30), без red/green."""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.vip_scoring_common import (
    ClosingFacts,
    ContactFacts,
    CriterionScore,
    PrepFacts,
    ScoringResult,
    SharedCallContext,
    SharedContextFacts,
    score_closing,
    score_contact,
    score_prep,
)

RUBRIC_VERSION = "v2_90sec"
CALL_TYPE_KEY = "vip_short_90s"
MAX_SCORE = 30.0


class SlipHandlingFacts(BaseModel):
    client_attempted_to_end_call: bool = False
    reason_stated_by_client: bool = False
    reason_clarified_by_manager: bool = False
    manager_reacted_appropriately: bool = False
    proposed_callback: bool = False
    specified_concrete_time: bool = False
    confirmed_agreement_or_clear_refusal: bool = False
    client_flatly_refused_any_callback: bool = False


class SlipCriticalFacts(BaseModel):
    continued_pitch_after_client_said_cannot_talk: bool = False
    continued_pitch_instead_of_agreeing_callback: bool = False
    asked_irrelevant_questions: bool = False
    artificially_extended_call: bool = False
    delayed_ending_after_callback_agreed: bool = False
    ended_without_using_available_retention_options: bool = False


class VipShort90sFactsBundle(BaseModel):
    contact: ContactFacts = Field(default_factory=ContactFacts)
    slip_handling: SlipHandlingFacts = Field(default_factory=SlipHandlingFacts)
    slip_critical: SlipCriticalFacts = Field(default_factory=SlipCriticalFacts)
    prep: PrepFacts = Field(default_factory=PrepFacts)
    closing: ClosingFacts = Field(default_factory=ClosingFacts)
    shared_context: SharedContextFacts = Field(default_factory=SharedContextFacts)


def score_slip_handling(f: SlipHandlingFacts, ctx: SharedCallContext) -> CriterionScore:
    if not f.client_attempted_to_end_call:
        return CriterionScore(
            "slip_handling",
            10.0,
            10.0,
            ["Клієнт не намагався завершити дзвінок достроково — критерій не застосовний"],
        )
    if ctx.client_ended_call_first or f.client_flatly_refused_any_callback:
        return CriterionScore(
            "slip_handling",
            10.0,
            10.0,
            [
                "Клієнт завершив дзвінок сам / категорично відмовився від передзвону — не знижується"
            ],
        )

    reason_ok = f.reason_stated_by_client or f.reason_clarified_by_manager
    actions = [
        reason_ok,
        f.manager_reacted_appropriately,
        f.proposed_callback,
        f.specified_concrete_time,
        f.confirmed_agreement_or_clear_refusal,
        not ctx.call_format_prevented_full_flow,
    ]
    missing = actions.count(False)
    if missing == 0:
        return CriterionScore("slip_handling", 10.0, 10.0, [])
    if missing == 1:
        return CriterionScore(
            "slip_handling",
            7.5,
            10.0,
            ["Не вистачило однієї дії з утримання контакту"],
        )
    if missing == 2:
        return CriterionScore(
            "slip_handling",
            5.0,
            10.0,
            ["Відреагував на бажання завершити розмову, але не до кінця"],
        )
    if missing <= 4:
        return CriterionScore(
            "slip_handling",
            2.5,
            10.0,
            ["Фактично не працював зі «сливом» клієнта"],
        )
    return CriterionScore(
        "slip_handling",
        0.0,
        10.0,
        ["Не зробив жодної дії з утримання контакту"],
    )


def has_critical_slip_violation(f: SlipCriticalFacts) -> tuple[bool, list[str]]:
    flags = {
        "Продовжив презентацію, хоча клієнт прямо сказав, що не може говорити": (
            f.continued_pitch_after_client_said_cannot_talk
        ),
        "Продовжив продаж замість домовленості про інший контакт": (
            f.continued_pitch_instead_of_agreeing_callback
        ),
        "Ставив питання, що не допомагають зберегти контакт": f.asked_irrelevant_questions,
        "Штучно затягував дзвінок": f.artificially_extended_call,
        "Затягував завершення після згоди клієнта на передзвін": (
            f.delayed_ending_after_callback_agreed
        ),
        "Завершив дзвінок, не використавши доречні можливості утримання контакту": (
            f.ended_without_using_available_retention_options
        ),
    }
    reasons = [label for label, val in flags.items() if val]
    return (len(reasons) > 0, reasons)


def score_vip_short_90s(
    facts: VipShort90sFactsBundle,
    ctx: SharedCallContext | None = None,
) -> ScoringResult:
    ctx = ctx or SharedCallContext.from_facts(facts.shared_context.model_dump())
    contact = score_contact(facts.contact)
    slip = score_slip_handling(facts.slip_handling, ctx)
    prep = score_prep(facts.prep)
    closing = score_closing(facts.closing, ctx)

    is_critical, critical_reasons = has_critical_slip_violation(facts.slip_critical)
    criteria = [contact, slip, prep, closing]
    total = 0.0 if is_critical else sum(c.points for c in criteria)
    max_score = sum(c.max_points for c in criteria)

    return ScoringResult(
        call_type=CALL_TYPE_KEY,
        total_score=total,
        max_score=max_score,
        percent=round(total / max_score * 100, 1) if max_score else 0.0,
        is_critical_fail=is_critical,
        critical_reasons=critical_reasons,
        criteria=criteria,
        rubric_version=RUBRIC_VERSION,
    )


def score_vip_short_call(facts: dict, call: dict | None = None, dialogue: str = "") -> dict:
    """Сумісний вхід для app_vip: dict фактів → dict результату для UI/логів."""
    _ = (call, dialogue)
    bundle = VipShort90sFactsBundle.model_validate(facts or {})
    ctx = SharedCallContext.from_facts(bundle.shared_context.model_dump())
    return score_vip_short_90s(bundle, ctx).to_dict()


def build_perfect_short90s_facts() -> VipShort90sFactsBundle:
    return VipShort90sFactsBundle(
        contact=ContactFacts(
            greeted=True,
            used_client_name=True,
            named_project=True,
            availability_check_relevant=False,
        ),
        slip_handling=SlipHandlingFacts(client_attempted_to_end_call=False),
        slip_critical=SlipCriticalFacts(),
        prep=PrepFacts(objections_present=False, objections=[]),
        closing=ClosingFacts(
            asked_if_more_questions=True,
            said_goodbye=True,
            thanked_and_left_contact_open=True,
        ),
    )
