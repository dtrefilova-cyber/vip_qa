"""Спільні датакласи та критерії VIP: контакт, P.R.E.P., завершення."""

from __future__ import annotations

import re
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
    availability_check_relevant: bool = True
    availability_check_done: bool = False
    exception_prior_messenger_contact: bool = False
    exception_client_requested_call: bool = False
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
    # Д17: дзвінок за запитом клієнта, або модель позначила перевірку нерелевантною.
    skip_availability = bool(f.exception_client_requested_call) or f.availability_check_relevant is False
    element_labels = [
        (f.greeted, "привітання"),
        (f.used_client_name, "ім'я клієнта"),
        (f.named_project, "назва проєкту"),
    ]
    if not skip_availability:
        element_labels.append(
            (f.availability_check_done, "перевірка зручності («вам зручно» / «є хвилинка»)")
        )
    missing_labels = [label for ok, label in element_labels if not ok]
    if not missing_labels:
        if f.exception_client_requested_call and not f.availability_check_done:
            return 5.0, "Дзвінок за запитом клієнта — перевірка зручності не потрібна" + suffix
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


_CALLBACK_D14_RE = re.compile(
    r"набер|набрат|передзвон|зателефону|понеділ|вівтор|серед|четвер|"
    r"п['’ʼ]ятниц|субот|неділ|завтра|тижн|о \d",
    re.IGNORECASE,
)


def score_closing(f: ClosingFacts, ctx: SharedCallContext) -> CriterionScore:
    if f.connection_dropped and not f.agreed_follow_up:
        return CriterionScore("closing", 5.0, 5.0, ["Зв'язок обірвався"])
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
        quote = f.d14_quote.strip()
        if f.connection_dropped and not (f.agreed_follow_up and _CALLBACK_D14_RE.search(quote)):
            reason = "Зв'язок обірвався"
        elif f.agreed_follow_up and _CALLBACK_D14_RE.search(quote):
            reason = "Д14: домовились про передзвін — " + quote
        else:
            reason = "Д14: автозалік завершення — " + quote
        return CriterionScore("closing", 5.0, 5.0, [reason])
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


_APOSTROPHE_RE = re.compile(r"[’‘ʼ`]")
_QUOTE_MARK_RE = re.compile(r"[«»\"']")
_NUMBER_ONES = (
    ("один", 1),
    ("одна", 1),
    ("одну", 1),
    ("два", 2),
    ("дві", 2),
    ("три", 3),
    ("чотири", 4),
    ("п'ять", 5),
    ("шість", 6),
    ("сім", 7),
    ("вісім", 8),
    ("дев'ять", 9),
)
_NUMBER_TEENS = (
    ("одинадцять", 11),
    ("дванадцять", 12),
    ("тринадцять", 13),
    ("чотирнадцять", 14),
    ("п'ятнадцять", 15),
    ("шістнадцять", 16),
    ("сімнадцять", 17),
    ("вісімнадцять", 18),
    ("дев'ятнадцять", 19),
    ("десять", 10),
)
_NUMBER_TENS = (
    ("двадцять", 20),
    ("тридцять", 30),
    ("сорок", 40),
    ("п'ятдесят", 50),
    ("шістдесят", 60),
    ("сімдесят", 70),
    ("вісімдесят", 80),
    ("дев'яносто", 90),
)
_NUMBER_HUNDREDS = (
    ("сто", 100),
    ("двісті", 200),
    ("триста", 300),
    ("чотириста", 400),
    ("п'ятсот", 500),
    ("шістсот", 600),
    ("сімсот", 700),
    ("вісімсот", 800),
    ("дев'ятсот", 900),
)
_NUMBER_WORDS = _NUMBER_TEENS + _NUMBER_TENS + _NUMBER_HUNDREDS + _NUMBER_ONES + (("нуль", 0),)


def _replace_spoken_numbers(text: str) -> str:
    """Слова-числа 0–10 000 → цифри. «тисяч*» → 1000, «двадцять чотири» → 24."""
    updated = text
    for ten_word, ten_value in _NUMBER_TENS:
        for one_word, one_value in _NUMBER_ONES:
            updated = re.sub(
                rf"\b{ten_word}\s+{one_word}\b",
                str(ten_value + one_value),
                updated,
                flags=re.IGNORECASE,
            )
    updated = re.sub(r"\bтисяч\w*\b", "1000", updated, flags=re.IGNORECASE)
    for word, value in sorted(_NUMBER_WORDS, key=lambda item: len(item[0]), reverse=True):
        updated = re.sub(rf"\b{word}\b", str(value), updated, flags=re.IGNORECASE)
    return updated


def normalize_for_quote(text: str) -> str:
    """Порівняння цитат: лапки, апострофи, числа словами."""
    cleaned = _APOSTROPHE_RE.sub("'", text or "")
    cleaned = re.sub(r"\[\d+:\d+\]", " ", cleaned)
    cleaned = _replace_spoken_numbers(cleaned)
    cleaned = _QUOTE_MARK_RE.sub("", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def quote_token_overlap(quote: str, haystack: str) -> float:
    quote_tokens = re.findall(r"[0-9a-zа-яіїєґ]+", normalize_for_quote(quote))
    hay_tokens = set(re.findall(r"[0-9a-zа-яіїєґ]+", normalize_for_quote(haystack)))
    if not quote_tokens:
        return 0.0
    return sum(1 for token in quote_tokens if token in hay_tokens) / len(quote_tokens)
