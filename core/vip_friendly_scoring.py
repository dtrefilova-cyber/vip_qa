"""VIP Friendly (2-й дзвінок) — бальна рубрика (макс. 57,5)."""

from __future__ import annotations

import re
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

RUBRIC_VERSION = "v1_friendly_ease75"
CALL_TYPE_KEY = "vip_friendly"
MAX_SCORE = 57.5


class FriendlyDevelopmentFacts(BaseModel):
    asked_relevant_personal_questions: bool = False
    followed_up_on_client_answer: bool = False
    supported_client_initiated_topic: bool = False
    returned_to_personal_info_later: bool = False
    guide_level: str = ""
    signal_quotes: list[str] = Field(default_factory=list)
    mechanical_only: bool = False


class PersonalApproachFacts(BaseModel):
    used_prior_interaction_info: bool = False
    reacted_to_shared_personal_info: bool = False
    adapted_communication_style: bool = False
    maintained_positive_contact_without_immediate_action: bool = False
    guide_level: str = ""
    signal_quotes: list[str] = Field(default_factory=list)
    bonuses_only: bool = False
    tech_followup: bool = False


class CallToActionFacts(BaseModel):
    asked_deposit_today: bool = False
    started_with_bonus_before_deposit_intent: bool = False
    first_answer_positive: bool = False
    asked_deposit_tomorrow: bool = False
    second_answer_positive: bool = False
    client_is_military: bool = False
    asked_open_reason_if_declined: bool = False
    invited_to_play_when_possible: bool = False
    invite_quote: str = ""
    client_declared_deposit_today: bool = False
    client_declared_deposit_quote: str = ""
    client_declared_deposit_time: str = ""
    manager_play_questions: list[dict] = Field(default_factory=list)
    deposit_question_quote: str = ""
    deposit_question_time: str = ""
    first_answer: str = ""
    first_answer_quote: str = ""
    first_answer_time: str = ""
    tomorrow_question_quote: str = ""
    tomorrow_question_time: str = ""
    second_answer: str = ""
    second_answer_quote: str = ""
    second_answer_time: str = ""
    open_reason_quote: str = ""
    open_reason_time: str = ""
    first_bonus_offer_quote: str = ""
    first_bonus_offer_time: str = ""


class BonusTermsStated(BaseModel):
    min_deposit: str | None = None
    validity: str | None = None
    wager: str | None = None
    fs_count_and_bet: str | None = None


class BonusOfferFacts(BaseModel):
    deposit_bonus_offered_first: bool = False
    no_deposit_bonus_offered_after: bool = False
    no_deposit_bonus_applicable: bool = False
    all_terms_stated: bool = False
    benefits_explained: bool = False
    bonus_devalued: bool = False
    betking_x2_booster_offered: bool = False
    betking_x2_applicable: bool = False
    first_deposit_bonus_quote: str = ""
    first_deposit_bonus_time: str = ""
    first_no_deposit_bonus_quote: str = ""
    first_no_deposit_bonus_time: str = ""
    terms_stated: BonusTermsStated = Field(default_factory=BonusTermsStated)
    benefits_quote: str = ""
    devalue_quote: str = ""
    x2_quote: str = ""


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


def _level_points(value: str) -> float | None:
    return _LEVEL_POINTS.get(str(value or "").strip().replace(" ", ""))


def _quote_cap(count: int) -> float:
    if count <= 0:
        return 0.0
    if count == 1:
        return 2.5
    if count == 2:
        return 5.0
    return 7.5


def _verified_quotes(quotes: list[str], dialogue: str) -> list[str]:
    kept = []
    for quote in quotes or []:
        found, _clock_at = _quote_hit(dialogue, str(quote or ""), _MANAGER_SPEAKERS)
        if found:
            kept.append(str(quote))
    return kept


def score_friendly_development(f: FriendlyDevelopmentFacts, dialogue: str = "") -> CriterionScore:
    if f.guide_level or f.mechanical_only or f.signal_quotes:
        verified = _verified_quotes(f.signal_quotes, dialogue)
        personal = [quote for quote in verified if not _MECHANICAL.search(quote)]
        if not personal and (f.mechanical_only or verified):
            return CriterionScore(
                "friendly_development",
                0.0,
                7.5,
                ["Лише механічне «як справи / як день / все добре» без продовження"],
            )
        level = _level_points(f.guide_level)
        if level is None:
            level = _quote_cap(len(personal))
        points = min(level, _quote_cap(len(personal)))
        return CriterionScore(
            "friendly_development",
            points,
            7.5,
            [f"Рівень за цитатами ознак: {points:g}"],
        )
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


def score_personal_approach(f: PersonalApproachFacts, dialogue: str = "") -> CriterionScore:
    if f.tech_followup:
        return CriterionScore(
            "personal_approach",
            7.5,
            7.5,
            ["Д16: технічне питання / продовження розмови"],
        )
    if f.guide_level or f.bonuses_only or f.signal_quotes:
        verified = _verified_quotes(f.signal_quotes, dialogue)
        if f.bonuses_only or not verified:
            return CriterionScore(
                "personal_approach",
                0.0,
                7.5,
                ["Лише бонуси без персоналізації"],
            )
        level = _level_points(f.guide_level)
        if level is None:
            level = _quote_cap(len(verified))
        points = min(level, _quote_cap(len(verified)))
        return CriterionScore(
            "personal_approach",
            points,
            7.5,
            [f"Рівень за цитатами ознак: {points:g}"],
        )
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


_QUOTE_LINE = re.compile(
    r"^(?P<speaker>Менеджер|Клієнт|Клиент|ch_\d+)\s*:\s*(?:\[(?P<minute>\d+):(?P<second>\d+)\]\s*)?(?P<body>.*)$",
    re.IGNORECASE,
)
_DEPOSIT_TOKEN = re.compile(r"деп|депозит|поповн|рахунок", re.IGNORECASE)
_CONCRETE_BONUS = re.compile(
    r"\d|фріспін|фриспін|вейджер|бустер|\bфс\b|\bfs\b",
    re.IGNORECASE,
)
_PAST_BONUS = re.compile(
    r"минул|той бонус|до дня народження|гляну по бонус|щось залишу",
    re.IGNORECASE,
)
_MANAGER_SPEAKERS = {"менеджер", "ch_0"}
_CLIENT_SPEAKERS = {"клієнт", "клиент", "ch_1"}
_SOFT_CHANCE = re.compile(r"можлив|змог", re.IGNORECASE)
_SOFT_PLAY = re.compile(r"погра|забер|бонус|чека", re.IGNORECASE)
_ANSWERS = {"positive", "neutral", "negative", "unclear"}
_MECHANICAL = re.compile(r"як\s+справи|як\s+день|все\s+добре", re.IGNORECASE)
_OPEN_REASON = re.compile(r"чому|причин|завад", re.IGNORECASE)
_LEVEL_POINTS = {"7.5": 7.5, "7,5": 7.5, "5": 5.0, "5.0": 5.0, "2.5": 2.5, "2,5": 2.5, "0": 0.0, "0.0": 0.0}


def _flat(text: str) -> str:
    cleaned = re.sub(r"\[\d+:\d+\]", " ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def _clock(value: str | None) -> int | None:
    match = re.search(r"(\d+):(\d+)", str(value or ""))
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _quote_hit(
    dialogue: str,
    quote: str,
    speakers: set[str],
    min_len: int = 8,
) -> tuple[bool, int | None]:
    needle = _flat(quote).strip(" «»\"'«»")[:48]
    if len(needle) < min_len:
        return False, None
    for raw in (dialogue or "").splitlines():
        match = _QUOTE_LINE.match(raw.strip())
        if not match or match.group("speaker").lower() not in speakers:
            continue
        if needle not in _flat(match.group("body")):
            continue
        clock = None
        if match.group("minute") is not None:
            clock = int(match.group("minute")) * 60 + int(match.group("second"))
        return True, clock
    return False, None


def invite_quote_counts(quote: str) -> bool:
    """Д2: м'яке запрошення має і «можлив / змог», і «погра / забер / бонус»."""
    text = quote or ""
    return bool(_SOFT_CHANCE.search(text) and _SOFT_PLAY.search(text))


def deposit_question_counts(quote: str) -> bool:
    """Депозит сьогодні: у цитаті є деп, депозит, поповнення або рахунок.

    «Заходити» саме по собі не рахується. Разом із цими словами — рахується.
    """
    return bool(_DEPOSIT_TOKEN.search(quote or ""))


def _apply_play_questions(data: dict, dialogue: str) -> None:
    verified = []
    for item in data.get("manager_play_questions") or []:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        found, clock = _quote_hit(dialogue, quote, _MANAGER_SPEAKERS)
        if not found:
            continue
        if clock is None:
            clock = _clock(str(item.get("time") or ""))
        answer_quote = str(item.get("answer_quote") or "").strip()
        answer_found, _answer_clock = (
            _quote_hit(dialogue, answer_quote, _CLIENT_SPEAKERS) if answer_quote else (False, None)
        )
        answer = str(item.get("answer") or "").strip().lower()
        if answer not in _ANSWERS:
            answer = "unclear"
        verified.append({
            "quote": quote,
            "clock": clock if clock is not None else 10**9,
            "answer": answer,
            "answer_quote": answer_quote if answer_found else "",
            "answer_ok": answer_found,
        })
    verified.sort(key=lambda item: item["clock"])
    data["manager_play_questions"] = [
        {
            "quote": item["quote"],
            "time": "" if item["clock"] >= 10**9 else f"{item['clock'] // 60}:{item['clock'] % 60:02d}",
            "answer": item["answer"],
            "answer_quote": item["answer_quote"],
        }
        for item in verified
    ]
    deposits = [item for item in verified if deposit_question_counts(item["quote"])]
    if not deposits:
        data["asked_deposit_today"] = False
        data["deposit_question_quote"] = ""
        data["first_answer_positive"] = False
        data["asked_deposit_tomorrow"] = False
        data["second_answer_positive"] = False
        data["asked_open_reason_if_declined"] = False
        return
    first = deposits[0]
    data["asked_deposit_today"] = True
    data["deposit_question_quote"] = first["quote"]
    data["deposit_question_time"] = "" if first["clock"] >= 10**9 else f"{first['clock'] // 60}:{first['clock'] % 60:02d}"
    data["first_answer"] = first["answer"]
    data["first_answer_quote"] = first["answer_quote"]
    data["first_answer_positive"] = first["answer_ok"] and first["answer"] == "positive"
    later = [
        item for item in deposits[1:]
        if re.search(r"завтра", item["quote"], re.IGNORECASE)
    ]
    if first["answer"] in {"negative", "neutral"} and later:
        data["asked_deposit_tomorrow"] = True
        data["tomorrow_question_quote"] = later[0]["quote"]
        data["second_answer_positive"] = later[0]["answer_ok"] and later[0]["answer"] == "positive"
    else:
        data["asked_deposit_tomorrow"] = False
        data["tomorrow_question_quote"] = ""
        data["second_answer_positive"] = False
    reasons = [
        item for item in verified
        if item["clock"] > first["clock"] and _OPEN_REASON.search(item["quote"])
    ]
    if first["answer"] in {"negative", "neutral"} and not data["second_answer_positive"] and reasons:
        data["asked_open_reason_if_declined"] = True
        data["open_reason_quote"] = reasons[0]["quote"]
    else:
        data["asked_open_reason_if_declined"] = False
        data["open_reason_quote"] = ""


def ground_call_to_action(cta: dict, dialogue: str) -> dict:
    """Старі факти без цитат не чіпає. Новий блок заклику зводить до цитат у транскрипті."""
    if (
        "deposit_question_quote" not in cta
        and "first_bonus_offer_quote" not in cta
        and "manager_play_questions" not in cta
    ):
        return cta
    data = dict(cta)
    if "manager_play_questions" in data:
        _apply_play_questions(data, dialogue)
    found, line_clock = _quote_hit(
        dialogue, str(data.get("deposit_question_quote") or ""), _MANAGER_SPEAKERS
    )
    quote = str(data.get("deposit_question_quote") or "")
    deposit_ok = found and deposit_question_counts(quote)
    data["asked_deposit_today"] = deposit_ok
    if not deposit_ok:
        data["deposit_question_quote"] = ""
        data["deposit_question_time"] = ""
    deposit_clock = line_clock if deposit_ok else None
    if deposit_clock is None and deposit_ok:
        deposit_clock = _clock(str(data.get("deposit_question_time") or ""))

    answer_found, _answer_clock = _quote_hit(
        dialogue, str(data.get("first_answer_quote") or ""), _CLIENT_SPEAKERS
    )
    data["first_answer_positive"] = answer_found and str(data.get("first_answer") or "") == "positive"
    if not answer_found:
        data["first_answer_quote"] = ""

    tomorrow_found, _tomorrow_clock = _quote_hit(
        dialogue, str(data.get("tomorrow_question_quote") or ""), _MANAGER_SPEAKERS
    )
    data["asked_deposit_tomorrow"] = tomorrow_found
    if not tomorrow_found:
        data["tomorrow_question_quote"] = ""

    second_found, _second_clock = _quote_hit(
        dialogue, str(data.get("second_answer_quote") or ""), _CLIENT_SPEAKERS
    )
    data["second_answer_positive"] = second_found and str(data.get("second_answer") or "") == "positive"

    reason_found, _reason_clock = _quote_hit(
        dialogue, str(data.get("open_reason_quote") or ""), _MANAGER_SPEAKERS
    )
    data["asked_open_reason_if_declined"] = reason_found
    if not reason_found:
        data["open_reason_quote"] = ""

    bonus_found, bonus_line_clock = _quote_hit(
        dialogue, str(data.get("first_bonus_offer_quote") or ""), _MANAGER_SPEAKERS
    )
    bonus_quote = str(data.get("first_bonus_offer_quote") or "")
    bonus_clock = bonus_line_clock if bonus_found else None
    if bonus_clock is None and bonus_found:
        bonus_clock = _clock(str(data.get("first_bonus_offer_time") or ""))
    concrete = bool(_CONCRETE_BONUS.search(bonus_quote)) and not _PAST_BONUS.search(bonus_quote)
    data["started_with_bonus_before_deposit_intent"] = bool(
        deposit_ok
        and bonus_found
        and concrete
        and deposit_clock is not None
        and bonus_clock is not None
        and bonus_clock < deposit_clock
    )
    if not (bonus_found and concrete):
        data["first_bonus_offer_quote"] = ""
        data["first_bonus_offer_time"] = ""

    invite = str(data.get("invite_quote") or "").strip()
    invite_found, _invite_clock = (
        _quote_hit(dialogue, invite, _MANAGER_SPEAKERS) if invite else (False, None)
    )
    invite_ok = invite_found and invite_quote_counts(invite)
    data["invited_to_play_when_possible"] = invite_ok
    if not invite_ok:
        data["invite_quote"] = ""
    declared = str(data.get("client_declared_deposit_quote") or "").strip()
    if data.get("client_declared_deposit_today") and declared:
        declared_found, _declared_clock = _quote_hit(dialogue, declared, _CLIENT_SPEAKERS)
        if not declared_found or not deposit_question_counts(declared):
            data["client_declared_deposit_today"] = False
            data["client_declared_deposit_quote"] = ""
    return data


def score_call_to_action(f: CallToActionFacts) -> CriterionScore:
    if f.client_declared_deposit_today and str(f.client_declared_deposit_quote or "").strip():
        return CriterionScore(
            "call_to_action",
            10.0,
            10.0,
            ["Клієнт сам сказав, що гратиме сьогодні на депозит"],
        )
    if f.client_is_military and f.invited_to_play_when_possible and str(f.invite_quote or "").strip():
        return CriterionScore(
            "call_to_action",
            10.0,
            10.0,
            [f"Військовий: м'яке запрошення менеджера — {f.invite_quote.strip()}"],
        )
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

    table = {0: 10.0, 1: 5.0, 2: 5.0, 3: 2.5}
    points = table.get(missing, 0.0)
    return CriterionScore(
        "call_to_action",
        points,
        10.0,
        [f"Не виконано {missing} з обов'язкових дій заклику до гри"],
    )


_TERM_KEYS = ("min_deposit", "validity", "wager", "fs_count_and_bet")
_NA_TERMS = {"n/a", "na", "н/д"}
_DEVALUE = re.compile(r"забер\w*.{0,40}якщо\s+захочете|коли\s+буде\s+час", re.IGNORECASE)
_X2 = re.compile(r"\bx2\b|х2|бустер", re.IGNORECASE)
_BONUS_OFFER = re.compile(r"депозит|поповн|пополн|бонус|фріспін|фриспін|вейджер|бустер|спін", re.IGNORECASE)
_DEPOSIT_BONUS = re.compile(
    r"до\s+депозит|(?<!без)на\s+деп|(?<!без)депозитн|на\s+поповнен|до\s+поповнен|пополн|поповн",
    re.IGNORECASE,
)
_NOT_AN_OFFER = re.compile(r"гляну по бонус|щось залишу", re.IGNORECASE)


def _term_value(value) -> str | None:
    if value is None or value is False:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none"}:
        return None
    if text.lower() in _NA_TERMS:
        return "n/a"
    return text


def _term_counts(value: str | None, dialogue: str) -> bool:
    if value == "n/a":
        return True
    if not value:
        return False
    found, _clock_at = _quote_hit(dialogue, value, _MANAGER_SPEAKERS, min_len=4)
    return found


def ground_bonus_offer(bonus: dict, dialogue: str) -> dict:
    """Старі факти без цитат не чіпає. Новий блок бонусів зводить до цитат і таймкодів."""
    if "first_deposit_bonus_quote" not in bonus and "terms_stated" not in bonus:
        return bonus
    data = dict(bonus)
    applicable = bool(data.get("betking_x2_applicable"))
    deposit_quote = str(data.get("first_deposit_bonus_quote") or "")
    no_deposit_quote = str(data.get("first_no_deposit_bonus_quote") or "")
    if not _DEPOSIT_BONUS.search(deposit_quote) and _DEPOSIT_BONUS.search(no_deposit_quote):
        data["first_deposit_bonus_quote"] = no_deposit_quote
        data["first_deposit_bonus_time"] = str(data.get("first_no_deposit_bonus_time") or "")
        data["first_no_deposit_bonus_quote"] = ""
        data["first_no_deposit_bonus_time"] = ""
        deposit_quote = no_deposit_quote
        no_deposit_quote = ""
    deposit_found, deposit_clock = _quote_hit(dialogue, deposit_quote, _MANAGER_SPEAKERS)
    deposit_ok = (
        deposit_found
        and bool(_DEPOSIT_BONUS.search(deposit_quote))
        and not _NOT_AN_OFFER.search(deposit_quote)
    )
    if deposit_clock is None and deposit_ok:
        deposit_clock = _clock(str(data.get("first_deposit_bonus_time") or ""))
    no_deposit_found, no_deposit_clock = _quote_hit(dialogue, no_deposit_quote, _MANAGER_SPEAKERS)
    no_deposit_ok = no_deposit_found and not _NOT_AN_OFFER.search(no_deposit_quote)
    if no_deposit_clock is None and no_deposit_ok:
        no_deposit_clock = _clock(str(data.get("first_no_deposit_bonus_time") or ""))
    if not deposit_ok:
        data["deposit_bonus_offered_first"] = False
        data["first_deposit_bonus_quote"] = ""
        data["first_deposit_bonus_time"] = ""
    elif not no_deposit_ok:
        data["deposit_bonus_offered_first"] = True
    elif deposit_clock is not None and no_deposit_clock is not None:
        data["deposit_bonus_offered_first"] = deposit_clock <= no_deposit_clock
    else:
        data["deposit_bonus_offered_first"] = False
    data["no_deposit_bonus_offered_after"] = bool(
        deposit_ok
        and no_deposit_ok
        and deposit_clock is not None
        and no_deposit_clock is not None
        and no_deposit_clock > deposit_clock
    )
    if no_deposit_ok:
        data["no_deposit_bonus_applicable"] = True
    else:
        data["first_no_deposit_bonus_quote"] = ""
        data["first_no_deposit_bonus_time"] = ""
    terms_raw = data.get("terms_stated") if isinstance(data.get("terms_stated"), dict) else {}
    terms = {key: _term_value(terms_raw.get(key)) for key in _TERM_KEYS}
    for key, value in terms.items():
        if value and value != "n/a" and not _term_counts(value, dialogue):
            terms[key] = None
    data["terms_stated"] = terms
    data["all_terms_stated"] = all(_term_counts(terms[key], dialogue) for key in _TERM_KEYS)
    benefits = str(data.get("benefits_quote") or "")
    benefits_found, _benefits_clock = _quote_hit(dialogue, benefits, _MANAGER_SPEAKERS)
    data["benefits_explained"] = benefits_found
    if not benefits_found:
        data["benefits_quote"] = ""
    devalue = str(data.get("devalue_quote") or "")
    devalue_found, _devalue_clock = _quote_hit(dialogue, devalue, _MANAGER_SPEAKERS)
    data["bonus_devalued"] = bool(devalue_found and _DEVALUE.search(devalue))
    if not data["bonus_devalued"]:
        data["devalue_quote"] = ""
    x2_quote = str(data.get("x2_quote") or "")
    x2_found, _x2_clock = _quote_hit(dialogue, x2_quote, _MANAGER_SPEAKERS, min_len=3)
    data["betking_x2_booster_offered"] = bool(x2_found and _X2.search(x2_quote))
    if not data["betking_x2_booster_offered"]:
        data["x2_quote"] = ""
    data["betking_x2_applicable"] = applicable
    return data


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
    EaseLevel.LOW: 0.0,
    EaseLevel.CRITICAL: 0.0,
}


def score_ease(f: EaseFacts) -> CriterionScore:
    return CriterionScore("ease", _EASE_POINTS[f.level], 7.5, list(f.signals or []))


def _in_tail(dialogue: str, quote: str, speakers: set[str]) -> bool:
    found, clock = _quote_hit(dialogue, quote, speakers)
    if not found:
        return False
    clocks = []
    bodies = []
    for raw in (dialogue or "").splitlines():
        match = _QUOTE_LINE.match(raw.strip())
        if not match:
            continue
        if match.group("minute") is not None:
            clocks.append(int(match.group("minute")) * 60 + int(match.group("second")))
        if match.group("speaker").lower() in speakers:
            bodies.append(match.group("body"))
    if clock is not None and clocks and clock >= max(clocks) - 90:
        return True
    needle = _flat(quote)[:48]
    return bool(needle) and needle in _flat(" ".join(bodies[-6:]))


def ground_closing(closing: dict, dialogue: str) -> dict:
    """Старі факти без цитат не чіпає. Нове завершення — лише цитати в кінці дзвінка."""
    if "asked_if_more_questions_quote" not in closing and "client_ended_quote" not in closing:
        return closing
    data = dict(closing)
    data["asked_if_more_questions"] = _in_tail(
        dialogue, str(data.get("asked_if_more_questions_quote") or ""), _MANAGER_SPEAKERS
    )
    data["said_goodbye"] = _in_tail(
        dialogue, str(data.get("said_goodbye_quote") or ""), _MANAGER_SPEAKERS
    )
    thanked = str(data.get("thanked_quote") or "")
    data["thanked_and_left_contact_open"] = _in_tail(dialogue, thanked, _MANAGER_SPEAKERS) and bool(
        re.search(r"дяк|зв|пиш|зверта|береж", thanked, re.IGNORECASE)
    )
    data["client_ended_verified"] = _in_tail(
        dialogue, str(data.get("client_ended_quote") or ""), _CLIENT_SPEAKERS
    )
    data["connection_dropped"] = _in_tail(
        dialogue,
        str(data.get("connection_dropped_quote") or ""),
        _MANAGER_SPEAKERS | _CLIENT_SPEAKERS,
    )
    data["quote_mode"] = True
    return data


def score_quoted_closing(f: ClosingFacts) -> CriterionScore:
    """Автозалік лише з цитати завершення клієнтом або обриву зв'язку."""
    if f.client_ended_verified:
        return CriterionScore(
            "closing",
            5.0,
            5.0,
            ["Клієнт завершив дзвінок на етапі завершення"],
        )
    if (f.client_silent_at_end or f.agreed_follow_up) and str(f.d14_quote or "").strip():
        return CriterionScore(
            "closing",
            5.0,
            5.0,
            ["Д14: автозалік завершення — " + f.d14_quote.strip()],
        )
    if f.connection_dropped:
        return CriterionScore(
            "closing",
            5.0,
            5.0,
            ["Зв'язок перервався"],
        )
    elements = [
        f.asked_if_more_questions,
        f.said_goodbye,
        f.thanked_and_left_contact_open,
    ]
    missing = elements.count(False)
    if missing == 0:
        return CriterionScore("closing", 5.0, 5.0, [])
    if missing == 1:
        return CriterionScore("closing", 2.5, 5.0, ["Відсутній один елемент завершення"])
    return CriterionScore("closing", 0.0, 5.0, ["Відсутні два і більше елементи завершення"])


def score_vip_friendly(
    facts: VipFriendlyFactsBundle,
    ctx: SharedCallContext | None = None,
    dialogue: str = "",
) -> ScoringResult:
    ctx = ctx or SharedCallContext.from_facts(facts.shared_context.model_dump())
    if facts.call_to_action.client_is_military:
        ctx.client_is_military = True
    criteria = [
        score_contact(facts.contact),
        score_friendly_development(facts.friendly_development, dialogue),
        score_personal_approach(facts.personal_approach, dialogue),
        score_call_to_action(facts.call_to_action),
        score_bonus_offer(facts.bonus_offer),
        score_prep(facts.prep, ctx),
        score_quoted_closing(facts.closing) if facts.closing.quote_mode else score_closing(facts.closing, ctx),
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
    from core.vip_short_scoring import (
        manager_soft_invite_quote,
        note_says_messenger,
        note_says_military,
        repair_obvious_closing,
        repair_obvious_contact,
    )

    data = dict(facts or {})
    call = call or {}
    cta = dict(data.get("call_to_action") or {})
    note = str(call.get("important_note") or "")
    comment = str(call.get("qa_comment") or "")
    manager_comment = str(call.get("manager_comment") or "")
    military = bool(cta.get("client_is_military")) or bool(call.get("client_is_military"))
    military = military or note_says_military(note, comment, manager_comment)
    cta["client_is_military"] = military
    invite = manager_soft_invite_quote(dialogue)
    if military and invite:
        cta["invited_to_play_when_possible"] = True
        cta["invite_quote"] = invite
    elif not str(cta.get("invite_quote") or "").strip():
        cta["invited_to_play_when_possible"] = False
    cta = ground_call_to_action(cta, dialogue)
    quote = str(cta.get("client_declared_deposit_quote") or "")
    if cta.get("client_declared_deposit_today") and quote:
        client_blob = "\n".join(
            line.split(":", 1)[-1]
            for line in (dialogue or "").splitlines()
            if line.strip().startswith(("Клієнт", "Клиент", "ch_1"))
        )
        if quote.strip(" «»\"")[:24].lower() not in client_blob.lower():
            cta["client_declared_deposit_today"] = False
    data["call_to_action"] = cta
    bonus = dict(data.get("bonus_offer") or {})
    if call.get("betking_x2_applicable") is not None:
        bonus["betking_x2_applicable"] = bool(call.get("betking_x2_applicable"))
    data["bonus_offer"] = ground_bonus_offer(bonus, dialogue)
    if note_says_messenger(note, comment, manager_comment):
        contact = dict(data.get("contact") or {})
        contact["exception_prior_messenger_contact"] = True
        data["contact"] = contact
    if dialogue:
        data = repair_obvious_contact(data, dialogue)
    if call.get("tech_followup"):
        approach = dict(data.get("personal_approach") or {})
        approach["tech_followup"] = True
        data["personal_approach"] = approach
        prep = dict(data.get("prep") or {})
        prep["tech_followup"] = True
        data["prep"] = prep
    data["closing"] = ground_closing(dict(data.get("closing") or {}), dialogue)
    if dialogue:
        data = repair_obvious_closing(data, dialogue)
    bundle = VipFriendlyFactsBundle.model_validate(data)
    ctx = SharedCallContext.from_facts(bundle.shared_context.model_dump())
    return score_vip_friendly(bundle, ctx, dialogue).to_dict()


def build_perfect_friendly_facts() -> VipFriendlyFactsBundle:
    return VipFriendlyFactsBundle(
        contact=ContactFacts(
            greeted=True,
            used_client_name=True,
            named_project=True,
            availability_check_done=True,
            availability_check_relevant=True,
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
