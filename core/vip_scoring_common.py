"""Спільні датакласи та критерії VIP: контакт, P.R.E.P., завершення."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


CRITERION_LABELS = {
    "contact": "Встановлення контакту",
    "slip_handling": "Робота зі «зливом» / утримання контакту",
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
    review_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("review_flags", None)
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
    review_flags: list[str] = field(default_factory=list)
    score_before_critical: float = 0.0

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
            "verdict": "scored",
            "verdict_reasons": list(self.critical_reasons)
            if self.is_critical_fail
            else [r for c in self.criteria for r in c.reasons],
            "review_flags": list(self.review_flags),
            "score_before_critical": self.score_before_critical,
            "score_label": f"{self.total_score:g} / {self.max_score:g} ({self.percent}%)",
        }


@dataclass
class SharedCallContext:
    client_ended_call_first: bool = False
    client_said_no_time_and_hung_up: bool = False
    client_interrupted_manager: bool = False
    call_format_prevented_full_flow: bool = False
    client_didnt_allow_finish_thought: bool = False
    moved_to_messenger: bool = False
    client_is_military: bool = False

    @classmethod
    def from_facts(cls, raw: dict | None, *, client_is_military: bool = False) -> "SharedCallContext":
        data = dict(raw or {})
        return cls(
            client_ended_call_first=bool(data.get("client_ended_call_first")),
            client_said_no_time_and_hung_up=bool(data.get("client_said_no_time_and_hung_up")),
            client_interrupted_manager=bool(data.get("client_interrupted_manager")),
            call_format_prevented_full_flow=bool(data.get("call_format_prevented_full_flow")),
            client_didnt_allow_finish_thought=bool(data.get("client_didnt_allow_finish_thought")),
            moved_to_messenger=bool(data.get("moved_to_messenger")),
            client_is_military=bool(client_is_military),
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
    exception_number_signed: bool = False
    manager_introduced_self: bool = False
    greeting_quote: str = ""
    client_name_quote: str = ""
    project_quote: str = ""
    availability_quote: str = ""
    manager_name_quote: str = ""
    evidence: list[str] = Field(default_factory=list)


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
        "no_money",
        "bad_bonus_experience",
        "doubts_about_offer",
        "other",
    ] = "other"
    handling: ObjectionHandling = ObjectionHandling.IGNORED
    quote: str = ""
    offer_quote: str = ""
    right_before_client_hangup: bool = False


class PrepFacts(BaseModel):
    objections_present: bool = False
    objections: list[Objection] = Field(default_factory=list)
    tech_followup: bool = False


class ClosingFacts(BaseModel):
    asked_if_more_questions: bool = False
    said_goodbye: bool = False
    thanked_and_left_contact_open: bool = False
    evidence: list[str] = Field(default_factory=list)
    asked_if_more_questions_quote: str = ""
    said_goodbye_quote: str = ""
    thanked_quote: str = ""
    client_ended_quote: str = ""
    connection_dropped_quote: str = ""
    quote_mode: bool = False
    client_ended_verified: bool = False
    connection_dropped: bool = False
    client_silent_at_end: bool = False
    agreed_follow_up: bool = False
    d14_quote: str = ""


class SharedContextFacts(BaseModel):
    client_ended_call_first: bool = False
    client_said_no_time_and_hung_up: bool = False
    client_interrupted_manager: bool = False
    call_format_prevented_full_flow: bool = False
    client_didnt_allow_finish_thought: bool = False
    moved_to_messenger: bool = False
    evidence: list[str] = Field(default_factory=list)


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


def _evidence_suffix(evidence: list[str] | None) -> str:
    for item in evidence or []:
        text = str(item or "").strip()
        if text:
            return f" {text}" if text.startswith("[") else f" [{text}]"
    return ""


def _contact_without_messenger(f: ContactFacts) -> tuple[float, str]:
    """Звичайний бал і винятки, крім Д5."""
    suffix = _evidence_suffix(f.evidence)
    if any(
        [
            f.exception_number_signed,
            f.exception_client_recognized_manager,
            f.exception_client_interrupted_intro,
            f.exception_answered_question_then_finished_intro,
        ]
    ):
        if f.exception_number_signed:
            reason = "Номер підписаний — назва проєкту не обов'язкова"
        else:
            reason = "Застосовано виключення — оцінка не знижується"
        return 5.0, reason + suffix

    # Д11: перевірка зручності обов'язкова разом із привітанням, ім'ям і проєктом.
    element_labels = [
        (f.greeted, "привітання"),
        (f.used_client_name, "ім'я клієнта"),
        (f.named_project, "назва проєкту"),
        (f.availability_check_done, "перевірка зручності («вам зручно» / «є хвилинка»)"),
    ]
    missing_labels = [label for ok, label in element_labels if not ok]
    if not missing_labels:
        return 5.0, ""
    if len(missing_labels) == 1:
        return 2.5, f"Відсутній елемент привітання: {missing_labels[0]}" + suffix
    joined = ", ".join(missing_labels)
    return 0.0, f"Відсутні елементи привітання: {joined}" + suffix


def _contact_messenger(f: ContactFacts) -> tuple[float, str] | None:
    """Д5. None, якщо месенджера до дзвінка не було."""
    if not f.exception_prior_messenger_contact:
        return None
    suffix = _evidence_suffix(f.evidence)
    if f.manager_introduced_self:
        return 5.0, "Месенджер до дзвінка і менеджер назвав себе" + suffix
    if f.exception_client_recognized_manager:
        return (
            5.0,
            "Месенджер до дзвінка, клієнт звернувся до менеджера на ім'я" + suffix,
        )
    return 2.5, "Месенджер до дзвінка, але менеджер не назвав своє ім'я" + suffix


def score_contact(f: ContactFacts) -> CriterionScore:
    normal, normal_reason = _contact_without_messenger(f)
    messenger = _contact_messenger(f)
    if messenger is None or normal >= messenger[0]:
        reasons = [normal_reason] if normal_reason else []
        return CriterionScore("contact", normal, 5.0, reasons)
    points, reason = messenger
    return CriterionScore("contact", points, 5.0, [reason])


def score_prep(f: PrepFacts, ctx: SharedCallContext | None = None) -> CriterionScore:
    """Без ctx поведінка Friendly лишається попередньою."""
    if f.tech_followup:
        return CriterionScore(
            "prep",
            10.0,
            10.0,
            ["Д16: технічне питання / продовження розмови"],
        )
    flags: list[str] = []
    objections = list(f.objections)
    if ctx is None:
        if not f.objections_present:
            return CriterionScore("prep", 10.0, 10.0, ["Заперечень не було — автоматично максимум"])
        if not objections:
            return CriterionScore("prep", 0.0, 10.0, ["Заперечення заявлені, але не описані — 0"])
    else:
        if f.objections_present and not objections:
            flags.append("prep_objections_missing")
            return CriterionScore(
                "prep",
                10.0,
                10.0,
                ["Заперечень не було — автоматично максимум"],
                flags,
            )
        kept = []
        skipped_military = False
        skipped_hangup = False
        for item in objections:
            if item.right_before_client_hangup:
                skipped_hangup = True
                continue
            if ctx.client_is_military and item.type in {"no_money", "no_time"}:
                skipped_military = True
                continue
            kept.append(item)
        if objections and not kept:
            if skipped_military and not skipped_hangup:
                reason = "Військовий: немає коштів і немає часу можна не опрацьовувати"
            else:
                reason = "Клієнт завершив дзвінок / заперечення не оцінюється — автозалік"
            return CriterionScore("prep", 10.0, 10.0, [reason])
        objections = kept
        if not f.objections_present or not objections:
            return CriterionScore("prep", 10.0, 10.0, ["Заперечень не було — автоматично максимум"])
    worst = min(objections, key=lambda o: _PREP_ORDER.index(o.handling))
    quote = f" {worst.quote.strip()}" if str(worst.quote or "").strip() else ""
    return CriterionScore(
        "prep",
        _PREP_POINTS[worst.handling],
        10.0,
        [f"Найгірше опрацьоване заперечення: {worst.type} → {worst.handling.value}{quote}"],
        flags,
    )


def score_closing(f: ClosingFacts, ctx: SharedCallContext) -> CriterionScore:
    if ctx.moved_to_messenger:
        return CriterionScore(
            "closing",
            5.0,
            5.0,
            ["Розмова переходить у месенджер — автозалік" + _evidence_suffix(f.evidence)],
        )
    if ctx.client_ended_call_first or ctx.call_format_prevented_full_flow:
        return CriterionScore(
            "closing",
            5.0,
            5.0,
            ["Клієнт завершив дзвінок / зв'язок обірвався — автозалік" + _evidence_suffix(f.evidence)],
        )
    if (f.client_silent_at_end or f.agreed_follow_up) and str(f.d14_quote or "").strip():
        return CriterionScore(
            "closing",
            5.0,
            5.0,
            ["Д14: автозалік завершення — " + f.d14_quote.strip()],
        )
    element_labels = [
        (f.asked_if_more_questions, "питання «чи є ще питання»"),
        (f.said_goodbye, "прощання"),
        (f.thanked_and_left_contact_open, "подяка з відкритим контактом"),
    ]
    missing_labels = [label for ok, label in element_labels if not ok]
    if not missing_labels:
        return CriterionScore("closing", 5.0, 5.0, [])
    if len(missing_labels) == 1:
        return CriterionScore(
            "closing",
            2.5,
            5.0,
            [f"Відсутній елемент завершення: {missing_labels[0]}"],
        )
    joined = ", ".join(missing_labels)
    return CriterionScore(
        "closing",
        0.0,
        5.0,
        [f"Відсутні елементи завершення: {joined}"],
    )
