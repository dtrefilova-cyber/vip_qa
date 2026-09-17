"""VIP «Короткий 90 сек» — бальна рубрика (макс. 30), без red/green."""

from __future__ import annotations

import logging

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

logger = logging.getLogger(__name__)

RUBRIC_VERSION = "v2_90sec"
CALL_TYPE_KEY = "vip_short_90s"
MAX_SCORE = 30.0

# Градація «Робота зі зливом» за гайдом: 0 / 2,5 / 5 / 7,5 / 10.
SLIP_HANDLING_ALLOWED_POINTS = (0.0, 2.5, 5.0, 7.5, 10.0)

CRITICAL_SUPPRESSED_NO_QUOTE = (
    "Критичний гейт не застосовано: немає цитати клієнта про бажання завершити розмову. "
    "Потрібна ручна перевірка QA."
)
CRITICAL_SUPPRESSED_QUOTE_NOT_IN_TRANSCRIPT = (
    "Критичний гейт не застосовано: цитата «зливу» не знайдена в транскрипті. "
    "Потрібна ручна перевірка QA."
)
CRITICAL_SUPPRESSED_QUOTE_NOT_A_LEAK = (
    "Критичний гейт не застосовано: цитата не показує бажання клієнта завершити розмову. "
    "Потрібна ручна перевірка QA."
)

# Репліка клієнта має містити хоча б один сигнал «зливу» (бажання завершити / зайнятість / брак часу).
_CLIENT_END_CALL_MARKERS = (
    "не можу говор",
    "не могу говор",
    "не можу розмов",
    "зайнят",
    "занят",
    "немає часу",
    "нема часу",
    "нет времени",
    "передзвон",
    "перезвон",
    "не дзвон",
    "не звон",
    "не телефон",
    "поспіша",
    "спешу",
    "не цікаво",
    "не интересно",
    "не хочу",
    "незручно",
    "неудобно",
    "не зараз",
    "не сейчас",
    "пізніше",
    "позже",
    "не до розмов",
    "за керм",
    "на роботі",
    "на работе",
)


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
    # Дослівна репліка клієнта з транскрипту, що підтверджує «злив».
    critical_evidence_quote: str = ""


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
            ["Фактично не працював зі «зливом» клієнта"],
        )
    return CriterionScore(
        "slip_handling",
        0.0,
        10.0,
        ["Не зробив жодної дії з утримання контакту"],
    )


def _normalize_for_quote_match(text: str) -> str:
    return " ".join((text or "").split()).casefold()


def evidence_quote_in_transcript(quote: str, transcript: str) -> bool:
    """Проста перевірка: нормалізована цитата є підрядком транскрипту."""
    q = _normalize_for_quote_match(quote)
    if not q:
        return False
    return q in _normalize_for_quote_match(transcript)


def quote_shows_client_wanted_to_end(quote: str) -> bool:
    q = _normalize_for_quote_match(quote)
    if not q:
        return False
    return any(marker in q for marker in _CLIENT_END_CALL_MARKERS)


def has_critical_slip_violation(
    f: SlipCriticalFacts,
    transcript: str = "",
) -> tuple[bool, list[str], list[str]]:
    """Повертає (is_critical, reasons, review_flags).

    Критичне обнулення лише якщо є прапорець І цитата «зливу» знайдена в транскрипті.
    """
    flags = {
        "Після прямої репліки клієнта, що не може говорити, менеджер продовжив презентацію": (
            f.continued_pitch_after_client_said_cannot_talk
        ),
        "Після бажання клієнта завершити розмову менеджер продовжив продаж замість домовленості про інший контакт": (
            f.continued_pitch_instead_of_agreeing_callback
        ),
        "Після сигналу «зливу» менеджер ставив питання, що не допомагають зберегти контакт і не стосуються причини/передзвону": (
            f.asked_irrelevant_questions
        ),
        "Після сигналу «зливу» менеджер штучно затягував дзвінок (продовжив продукт/бонуси без мети утримання)": (
            f.artificially_extended_call
        ),
        "Клієнт уже погодив передзвін, але менеджер затягував завершення презентацією": (
            f.delayed_ending_after_callback_agreed
        ),
        "Клієнт хотів завершити розмову і не відмовився від передзвону, але менеджер завершив дзвінок без спроби утримати контакт": (
            f.ended_without_using_available_retention_options
        ),
    }
    reasons = [label for label, val in flags.items() if val]
    if not reasons:
        return False, [], []

    quote = (f.critical_evidence_quote or "").strip()
    if not quote:
        logger.warning(
            "VIP short critical flags set without evidence quote; gate suppressed. flags=%s",
            reasons,
        )
        return False, [], [CRITICAL_SUPPRESSED_NO_QUOTE]
    if not evidence_quote_in_transcript(quote, transcript):
        logger.warning(
            "VIP short critical evidence quote not found in transcript; gate suppressed. quote=%r",
            quote[:200],
        )
        return False, [], [CRITICAL_SUPPRESSED_QUOTE_NOT_IN_TRANSCRIPT]
    if not quote_shows_client_wanted_to_end(quote):
        logger.warning(
            "VIP short critical quote is not a client end-call signal; gate suppressed. quote=%r",
            quote[:200],
        )
        return False, [], [CRITICAL_SUPPRESSED_QUOTE_NOT_A_LEAK]
    return True, reasons, []


def score_vip_short_90s(
    facts: VipShort90sFactsBundle,
    ctx: SharedCallContext | None = None,
    dialogue: str = "",
) -> ScoringResult:
    ctx = ctx or SharedCallContext.from_facts(facts.shared_context.model_dump())
    contact = score_contact(facts.contact)
    slip = score_slip_handling(facts.slip_handling, ctx)
    prep = score_prep(facts.prep)
    closing = score_closing(facts.closing, ctx)

    is_critical, critical_reasons, review_flags = has_critical_slip_violation(
        facts.slip_critical,
        transcript=dialogue or "",
    )
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
        review_flags=review_flags,
    )


def score_vip_short_call(facts: dict, call: dict | None = None, dialogue: str = "") -> dict:
    """Сумісний вхід для app_vip: dict фактів → dict результату для UI/логів."""
    _ = call
    bundle = VipShort90sFactsBundle.model_validate(facts or {})
    ctx = SharedCallContext.from_facts(bundle.shared_context.model_dump())
    return score_vip_short_90s(bundle, ctx, dialogue=dialogue or "").to_dict()


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
