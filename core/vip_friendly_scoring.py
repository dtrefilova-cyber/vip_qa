"""VIP Friendly (2-й дзвінок) — бальна рубрика (макс. 57.5)."""

from __future__ import annotations

from enum import Enum

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

RUBRIC_VERSION = "v1_friendly"
CALL_TYPE_KEY = "vip_friendly"
MAX_SCORE = 57.5


class FriendlyDevelopmentFacts(BaseModel):
    asked_relevant_personal_questions: bool = False
    followed_up_on_client_answer: bool = False
    supported_client_initiated_topic: bool = False
    returned_to_personal_info_later: bool = False


class PersonalApproachFacts(BaseModel):
    used_prior_interaction_info: bool = False
    reacted_to_shared_personal_info: bool = False
    adapted_communication_style: bool = False
    maintained_positive_contact_without_immediate_action: bool = False


class CallToActionFacts(BaseModel):
    asked_deposit_today: bool = False
    started_with_bonus_before_deposit_intent: bool = False
    first_answer_positive: bool = False
    asked_deposit_tomorrow: bool = False
    second_answer_positive: bool = False
    client_is_military: bool = False
    asked_open_reason_if_declined: bool = False


class BonusOfferFacts(BaseModel):
    deposit_bonus_offered_first: bool = False
    no_deposit_bonus_offered_after: bool = False
    no_deposit_bonus_applicable: bool = False
    all_terms_stated: bool = False
    benefits_explained: bool = False
    bonus_devalued: bool = False
    betking_x2_booster_offered: bool = False
    betking_x2_applicable: bool = False


class EaseLevel(str, Enum):
    HIGH = "high"
    NOTICEABLE_GAPS = "noticeable_gaps"
    LOW = "low"
    CRITICAL = "critical"


class EaseFacts(BaseModel):
    level: EaseLevel = EaseLevel.CRITICAL
    signals: list[str] = Field(default_factory=list)


class VipFriendlyFactsBundle(BaseModel):
    contact: ContactFacts = Field(default_factory=ContactFacts)
    friendly_development: FriendlyDevelopmentFacts = Field(
        default_factory=FriendlyDevelopmentFacts
    )
    personal_approach: PersonalApproachFacts = Field(default_factory=PersonalApproachFacts)
    call_to_action: CallToActionFacts = Field(default_factory=CallToActionFacts)
    bonus_offer: BonusOfferFacts = Field(default_factory=BonusOfferFacts)
    prep: PrepFacts = Field(default_factory=PrepFacts)
    closing: ClosingFacts = Field(default_factory=ClosingFacts)
    ease: EaseFacts = Field(default_factory=EaseFacts)
    shared_context: SharedContextFacts = Field(default_factory=SharedContextFacts)


def score_friendly_development(f: FriendlyDevelopmentFacts) -> CriterionScore:
    signals = [
        f.asked_relevant_personal_questions,
        f.followed_up_on_client_answer,
        f.supported_client_initiated_topic,
        f.returned_to_personal_info_later,
    ]
    count = sum(signals)
    table = {4: 7.5, 3: 7.5, 2: 5.0, 1: 2.5, 0: 0.0}
    return CriterionScore(
        "friendly_development",
        table[count],
        7.5,
        [f"Присутні {count} з 4 ознак розвитку френдлі"],
    )


def score_personal_approach(f: PersonalApproachFacts) -> CriterionScore:
    signals = [
        f.used_prior_interaction_info,
        f.reacted_to_shared_personal_info,
        f.adapted_communication_style,
        f.maintained_positive_contact_without_immediate_action,
    ]
    count = sum(signals)
    table = {4: 7.5, 3: 7.5, 2: 5.0, 1: 2.5, 0: 0.0}
    return CriterionScore(
        "personal_approach",
        table[count],
        7.5,
        [f"Присутні {count} з 4 ознак індивідуального підходу"],
    )


def score_call_to_action(f: CallToActionFacts) -> CriterionScore:
    if f.started_with_bonus_before_deposit_intent or not f.asked_deposit_today:
        return CriterionScore(
            "call_to_action",
            0.0,
            10.0,
            ["Не уточнив намір щодо депозиту сьогодні / почав із пропозиції бонусу"],
        )
    if f.first_answer_positive:
        return CriterionScore("call_to_action", 10.0, 10.0, [])

    done = 1
    if f.asked_deposit_tomorrow:
        done += 1
    if f.second_answer_positive:
        return CriterionScore("call_to_action", 10.0, 10.0, [])
    if f.client_is_military:
        missing = 2 - done
    else:
        if f.asked_open_reason_if_declined:
            done += 1
        missing = 3 - done

    table = {0: 10.0, 1: 5.0, 2: 2.5}
    points = table.get(missing, 0.0)
    return CriterionScore(
        "call_to_action",
        points,
        10.0,
        [f"Не виконано {missing} з обов'язкових дій заклику до гри"],
    )


def score_bonus_offer(f: BonusOfferFacts) -> CriterionScore:
    if not f.deposit_bonus_offered_first or f.bonus_devalued:
        return CriterionScore(
            "bonus_offer",
            0.0,
            5.0,
            ["Не запропонував депозитний бонус першим / знецінив бонус"],
        )
    order_ok = (not f.no_deposit_bonus_applicable) or f.no_deposit_bonus_offered_after
    betking_ok = (not f.betking_x2_applicable) or f.betking_x2_booster_offered
    checklist = [order_ok, f.all_terms_stated, f.benefits_explained, betking_ok]
    if all(checklist):
        return CriterionScore("bonus_offer", 5.0, 5.0, [])
    return CriterionScore(
        "bonus_offer",
        2.5,
        5.0,
        ["Не озвучено одну з обов'язкових умов/переваг бонусу"],
    )


_EASE_POINTS = {
    EaseLevel.HIGH: 7.5,
    EaseLevel.NOTICEABLE_GAPS: 5.0,
    EaseLevel.LOW: 2.5,
    EaseLevel.CRITICAL: 0.0,
}


def score_ease(f: EaseFacts) -> CriterionScore:
    return CriterionScore("ease", _EASE_POINTS[f.level], 7.5, list(f.signals or []))


def score_vip_friendly(
    facts: VipFriendlyFactsBundle,
    ctx: SharedCallContext | None = None,
) -> ScoringResult:
    ctx = ctx or SharedCallContext.from_facts(facts.shared_context.model_dump())
    criteria = [
        score_contact(facts.contact),
        score_friendly_development(facts.friendly_development),
        score_personal_approach(facts.personal_approach),
        score_call_to_action(facts.call_to_action),
        score_bonus_offer(facts.bonus_offer),
        score_prep(facts.prep),
        score_closing(facts.closing, ctx),
        score_ease(facts.ease),
    ]
    total = sum(c.points for c in criteria)
    max_score = sum(c.max_points for c in criteria)
    return ScoringResult(
        call_type=CALL_TYPE_KEY,
        total_score=total,
        max_score=max_score,
        percent=round(total / max_score * 100, 1) if max_score else 0.0,
        is_critical_fail=False,
        critical_reasons=[],
        criteria=criteria,
        rubric_version=RUBRIC_VERSION,
    )


def score_vip_friendly_call(facts: dict, call: dict | None = None, dialogue: str = "") -> dict:
    _ = dialogue
    data = dict(facts or {})
    # Allow card context to seed military / betking flags if GPT omitted them
    if call:
        cta = dict(data.get("call_to_action") or {})
        if "client_is_military" not in cta and call.get("client_is_military") is not None:
            cta["client_is_military"] = bool(call.get("client_is_military"))
        data["call_to_action"] = cta
        bonus = dict(data.get("bonus_offer") or {})
        if call.get("betking_x2_applicable") is not None:
            bonus["betking_x2_applicable"] = bool(call.get("betking_x2_applicable"))
        data["bonus_offer"] = bonus
    bundle = VipFriendlyFactsBundle.model_validate(data)
    ctx = SharedCallContext.from_facts(bundle.shared_context.model_dump())
    return score_vip_friendly(bundle, ctx).to_dict()


def build_perfect_friendly_facts() -> VipFriendlyFactsBundle:
    return VipFriendlyFactsBundle(
        contact=ContactFacts(
            greeted=True,
            used_client_name=True,
            named_project=True,
        ),
        friendly_development=FriendlyDevelopmentFacts(
            asked_relevant_personal_questions=True,
            followed_up_on_client_answer=True,
            supported_client_initiated_topic=True,
            returned_to_personal_info_later=True,
        ),
        personal_approach=PersonalApproachFacts(
            used_prior_interaction_info=True,
            reacted_to_shared_personal_info=True,
            adapted_communication_style=True,
            maintained_positive_contact_without_immediate_action=True,
        ),
        call_to_action=CallToActionFacts(
            asked_deposit_today=True,
            first_answer_positive=True,
        ),
        bonus_offer=BonusOfferFacts(
            deposit_bonus_offered_first=True,
            all_terms_stated=True,
            benefits_explained=True,
            no_deposit_bonus_applicable=False,
            betking_x2_applicable=False,
        ),
        prep=PrepFacts(objections_present=False),
        closing=ClosingFacts(
            asked_if_more_questions=True,
            said_goodbye=True,
            thanked_and_left_contact_open=True,
        ),
        ease=EaseFacts(level=EaseLevel.HIGH, signals=["Живий природний діалог"]),
    )
