"""Спільні датакласи та критерії VIP: контакт, P.R.E.P., завершення."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


CRITERION_LABELS = {
    "contact": "Встановлення контакту",
    "slip_handling": "Робота зі «сливом» / утримання контакту",
    "prep": "Робота з запереченням (P.R.E.P.)",
    "closing": "Завершення",
    "friendly_development": "Розвиток френдлі",
    "personal_approach": "Індивідуальний підхід",
    "call_to_action": "Заклик до гри",
    "bonus_offer": "Пропозиція бонусів",
    "ease": "Невимушеність",
}


@dataclass
class CriterionScore:
    key: str
    points: float
    max_points: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["label"] = CRITERION_LABELS.get(self.key, self.key)
        return data


@dataclass
class ScoringResult:
    call_type: str
    total_score: float
    max_score: float
    percent: float
    is_critical_fail: bool
    critical_reasons: list[str]
    criteria: list[CriterionScore]
    rubric_version: str = ""

    def to_dict(self) -> dict:
        return {
            "call_type": self.call_type,
            "total_score": self.total_score,
            "max_score": self.max_score,
            "percent": self.percent,
            "is_critical_fail": self.is_critical_fail,
            "critical_reasons": list(self.critical_reasons),
            "criteria": [c.to_dict() for c in self.criteria],
            "rubric_version": self.rubric_version,
            # UI / legacy-compatible fields (not GREEN/RED verdict)
            "verdict": "scored",
            "verdict_reasons": list(self.critical_reasons)
            if self.is_critical_fail
            else [r for c in self.criteria for r in c.reasons],
            "review_flags": [],
            "score_label": f"{self.total_score:g} / {self.max_score:g} ({self.percent}%)",
        }


@dataclass
class SharedCallContext:
    client_ended_call_first: bool = False
    client_said_no_time_and_hung_up: bool = False
    client_interrupted_manager: bool = False
    call_format_prevented_full_flow: bool = False
    client_didnt_allow_finish_thought: bool = False

    @classmethod
    def from_facts(cls, raw: dict | None) -> "SharedCallContext":
        data = dict(raw or {})
        return cls(
            client_ended_call_first=bool(data.get("client_ended_call_first")),
            client_said_no_time_and_hung_up=bool(data.get("client_said_no_time_and_hung_up")),
            client_interrupted_manager=bool(data.get("client_interrupted_manager")),
            call_format_prevented_full_flow=bool(data.get("call_format_prevented_full_flow")),
            client_didnt_allow_finish_thought=bool(data.get("client_didnt_allow_finish_thought")),
        )


class ContactFacts(BaseModel):
    greeted: bool = False
    used_client_name: bool = False
    named_project: bool = False
    availability_check_relevant: bool = False
    availability_check_done: bool = False
    exception_prior_messenger_contact: bool = False
    exception_client_recognized_manager: bool = False
    exception_client_interrupted_intro: bool = False
    exception_answered_question_then_finished_intro: bool = False


class ObjectionHandling(str, Enum):
    IGNORED = "ignored"
    FORMAL = "formal"
    TEMPLATE_ATTEMPT = "template_attempt"
    RESOLVED_NO_CHECK = "resolved_no_check"
    RESOLVED_WITH_CHECK = "resolved_with_check"


class Objection(BaseModel):
    type: Literal[
        "no_desire",
        "no_time",
        "no_payout",
        "bad_bonus_experience",
        "doubts_about_offer",
        "other",
    ] = "other"
    handling: ObjectionHandling = ObjectionHandling.IGNORED


class PrepFacts(BaseModel):
    objections_present: bool = False
    objections: list[Objection] = Field(default_factory=list)


class ClosingFacts(BaseModel):
    asked_if_more_questions: bool = False
    said_goodbye: bool = False
    thanked_and_left_contact_open: bool = False


class SharedContextFacts(BaseModel):
    client_ended_call_first: bool = False
    client_said_no_time_and_hung_up: bool = False
    client_interrupted_manager: bool = False
    call_format_prevented_full_flow: bool = False
    client_didnt_allow_finish_thought: bool = False


_PREP_ORDER = [
    ObjectionHandling.IGNORED,
    ObjectionHandling.FORMAL,
    ObjectionHandling.TEMPLATE_ATTEMPT,
    ObjectionHandling.RESOLVED_NO_CHECK,
    ObjectionHandling.RESOLVED_WITH_CHECK,
]
_PREP_POINTS = {
    ObjectionHandling.IGNORED: 0.0,
    ObjectionHandling.FORMAL: 2.5,
    ObjectionHandling.TEMPLATE_ATTEMPT: 5.0,
    ObjectionHandling.RESOLVED_NO_CHECK: 7.5,
    ObjectionHandling.RESOLVED_WITH_CHECK: 10.0,
}


def score_contact(f: ContactFacts) -> CriterionScore:
    if any(
        [
            f.exception_prior_messenger_contact,
            f.exception_client_recognized_manager,
            f.exception_client_interrupted_intro,
            f.exception_answered_question_then_finished_intro,
        ]
    ):
        return CriterionScore(
            "contact",
            5.0,
            5.0,
            ["Застосовано виключення — оцінка не знижується"],
        )

    required = [f.greeted, f.used_client_name, f.named_project]
    if f.availability_check_relevant:
        required.append(f.availability_check_done)

    missing = required.count(False)
    if missing == 0:
        return CriterionScore("contact", 5.0, 5.0, [])
    if missing == 1:
        return CriterionScore(
            "contact",
            2.5,
            5.0,
            ["Відсутній один із ключових елементів привітання"],
        )
    return CriterionScore(
        "contact",
        0.0,
        5.0,
        ["Жоден з пунктів привітання не озвучено"],
    )


def score_prep(f: PrepFacts) -> CriterionScore:
    if not f.objections_present:
        return CriterionScore(
            "prep",
            10.0,
            10.0,
            ["Заперечень не було — автоматично максимум"],
        )
    if not f.objections:
        return CriterionScore(
            "prep",
            0.0,
            10.0,
            ["Заперечення заявлені, але не описані — 0"],
        )
    worst = min(f.objections, key=lambda o: _PREP_ORDER.index(o.handling))
    return CriterionScore(
        "prep",
        _PREP_POINTS[worst.handling],
        10.0,
        [f"Найгірше опрацьоване заперечення: {worst.type} → {worst.handling.value}"],
    )


def score_closing(f: ClosingFacts, ctx: SharedCallContext) -> CriterionScore:
    if ctx.client_ended_call_first or ctx.call_format_prevented_full_flow:
        return CriterionScore(
            "closing",
            5.0,
            5.0,
            ["Клієнт завершив дзвінок / зв'язок обірвався — автозалік"],
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
        return CriterionScore(
            "closing",
            2.5,
            5.0,
            ["Відсутній один елемент завершення"],
        )
    return CriterionScore(
        "closing",
        0.0,
        5.0,
        ["Відсутні два і більше елементи завершення"],
    )
