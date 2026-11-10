"""VIP «Короткий 90 сек» — бальна рубрика (макс. 30), без red/green."""

from __future__ import annotations

import re

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

_NUMBER_SIGNED = re.compile(
    r"номер\s+підпис|підписан\w*|підпис\s*\+|не\s+представ|номер\s+записав",
    re.IGNORECASE,
)
_MILITARY = re.compile(
    r"військов|зсу|всу|служу|на службі|позиці",
    re.IGNORECASE,
)
_MESSENGER = re.compile(
    r"(?<![\w])(?:"
    r"месендж\w*|viber|вайбер|telegram|телеграм|whatsapp|ватсап|вотсап|"
    r"сигнал|signal|тг|вб|wa|tg"
    r")(?![\w])",
    re.IGNORECASE,
)
_SELF_INTRO = re.compile(r"мене звати|моє ім'?я|я ваш|ваш менеджер", re.IGNORECASE)
_SOFT_CHANCE = re.compile(r"можливост|змог", re.IGNORECASE)
_SOFT_PLAY = re.compile(r"погра|бонус|забер", re.IGNORECASE)


def note_says_number_signed(*parts: str) -> bool:
    return any(_NUMBER_SIGNED.search(str(part or "")) for part in parts)


def note_says_military(*parts: str) -> bool:
    return any(_MILITARY.search(str(part or "")) for part in parts)


def note_says_messenger(*parts: str) -> bool:
    return any(_MESSENGER.search(str(part or "")) for part in parts)


def manager_soft_invite_quote(dialogue: str) -> str:
    """Цитата менеджера з м'яким запрошенням. Фраза клієнта або чужий шматок діалогу не рахується."""
    for row in _dialogue_rows(dialogue):
        if not _is_manager_speaker(row["speaker"]):
            continue
        text = re.sub(r"[’‘ʼ`]", "'", row["text"] or "")
        if _SOFT_CHANCE.search(text) and _SOFT_PLAY.search(text):
            return str(row["text"] or "").strip()
    return ""


def military_soft_invite(dialogue: str) -> bool:
    return bool(manager_soft_invite_quote(dialogue))


def verify_contact_quotes(contact: dict, dialogue: str) -> dict:
    """Цитата, якої немає в репліці менеджера, не підтверджує елемент."""
    data = dict(contact or {})
    rows = _dialogue_rows(dialogue)
    pairs = (
        ("greeting_quote", "greeted"),
        ("client_name_quote", "used_client_name"),
        ("project_quote", "named_project"),
        ("availability_quote", "availability_check_done"),
        ("manager_name_quote", "manager_introduced_self"),
    )
    for quote_key, flag in pairs:
        quote = str(data.get(quote_key) or "").strip()
        if len(quote) < 4:
            continue
        needle = re.sub(r"\s+", " ", re.sub(r"\[\d+:\d+\]", " ", quote)).strip().lower()[:48]
        hit = any(
            needle in re.sub(r"\s+", " ", row["text"]).lower()
            for row in rows
            if _is_manager_speaker(row["speaker"])
        )
        if not hit:
            data[flag] = False
    return data


def repair_obvious_contact(facts: dict, dialogue: str) -> dict:
    """Якщо фраза є в репліці менеджера, не лишай позитивний факт false."""
    data = dict(facts or {})
    contact = verify_contact_quotes(dict(data.get("contact") or {}), dialogue)
    manager_lines = []
    speaker_line = re.compile(
        r"^(Менеджер|ch_0)\s*:\s*(?:\[\d+:\d+\]\s*)?(.*)$"
    )
    for raw in (dialogue or "").splitlines():
        match = speaker_line.match(raw.strip())
        if match:
            manager_lines.append(match.group(2) or "")
    blob = "\n".join(manager_lines)
    if re.search(r"добр|вітаю|здравств|привет", blob, re.IGNORECASE):
        contact["greeted"] = True
    intro = "\n".join(manager_lines[:4])
    if re.search(r"(?:алло|ало)\s*,\s*[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ']{2,}", blob):
        contact["used_client_name"] = True
    if re.search(
        r"(?:добрий|доброго)\s+(?:дня|вечора|ранку)?\s*,?\s*[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ']{2,}",
        intro,
        re.IGNORECASE,
    ):
        contact["used_client_name"] = True
    if re.search(
        r"[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ']{2,}\s*,?\s*(?:добрий|доброго)",
        intro,
    ):
        contact["used_client_name"] = True
    first = manager_lines[0] if manager_lines else ""
    if re.match(r"[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ']+\s+[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ']+", first):
        contact["used_client_name"] = True
    if re.search(r"\b777\b|betking|vegas", blob, re.IGNORECASE):
        contact["named_project"] = True
    if _SELF_INTRO.search(blob) or re.search(r"\bце\s+[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ']{2,}", intro):
        contact["manager_introduced_self"] = True
    if re.search(r"хвилин|зручно|є час|можете говорити|можете зараз", blob, re.IGNORECASE):
        contact["availability_check_done"] = True
        contact["availability_check_relevant"] = True
    intro = "\n".join(manager_lines[:3])
    if re.search(r"сайт\w*\s+\S", intro, re.IGNORECASE):
        contact["named_project"] = True
    data["contact"] = contact
    return data


_GOODBYE_RE = re.compile(
    r"гарного|до побачення|на все добре|бережіть себе|па-па|бувайте|до свидания|до зв'?язку|на зв'?язку",
    re.IGNORECASE,
)
_FOLLOW_UP_RE = re.compile(
    r"ще на зв'?язку|спишемо|списатис|напишемо|напишу вам|домовились",
    re.IGNORECASE,
)
_QUESTION_RE = re.compile(
    r"питанн|питань|запитанн|запитань|чимсь допомогти|чимось допомогти|залишил\w*.{0,24}питан",
    re.IGNORECASE,
)
_THANKS_RE = re.compile(r"дякую|спасибі|спасибо", re.IGNORECASE)
_RETENTION_MISS_RE = re.compile(r"не запропонував|не порадив", re.IGNORECASE)
_CLIENT_GOODBYE_RE = re.compile(
    r"\bпока\b|до побачення|до свидания|бувайте|бувай",
    re.IGNORECASE,
)
_END_CALL_RE = re.compile(
    r"не можу говорити|немає часу говорити|передзвон|до побачення|до свидания|\bпока\b|бувай|працюю|работаю|я на роботі",
    re.IGNORECASE,
)
_OFFER_REFUSAL_RE = re.compile(
    r"не надо|не треба|не буду|без різниці|не-не|не потріб|\bnie\b|не хочу",
    re.IGNORECASE,
)


def _dialogue_rows(dialogue: str) -> list[dict]:
    rows = []
    for raw in (dialogue or "").splitlines():
        match = _SPEAKER_LINE.match(raw.strip())
        if not match:
            continue
        rows.append(
            {
                "speaker": match.group("speaker"),
                "time": _clock_seconds(match.group("time"), match.group("sec")),
                "text": match.group("text") or "",
            }
        )
    return rows


def _is_manager_speaker(speaker: str) -> bool:
    return speaker in {"Менеджер", "ch_0"}


def _is_client_speaker(speaker: str) -> bool:
    return speaker in {"Клієнт", "Клиент", "ch_1"}


def repair_obvious_closing(facts: dict, dialogue: str) -> dict:
    """Фрази прощання в останніх репліках менеджера не залежать від чистки."""
    data = dict(facts or {})
    rows = _dialogue_rows(dialogue)
    manager = [row["text"] for row in rows if _is_manager_speaker(row["speaker"])]
    blob = re.sub(r"[’‘ʼ`]", "'", "\n".join(manager[-6:]))
    closing = dict(data.get("closing") or {})
    if _QUESTION_RE.search(blob):
        closing["asked_if_more_questions"] = True
    if _GOODBYE_RE.search(blob):
        closing["said_goodbye"] = True
    open_contact = re.search(
        r"звертай|пишіть|пиши|зв'?яз|на зв'?язку|рада була|радий був|бережіть",
        blob,
        re.IGNORECASE,
    )
    thanked = _THANKS_RE.search(blob) and (open_contact or _GOODBYE_RE.search(blob))
    farewell_open = re.search(r"бережіть\s+себе", blob, re.IGNORECASE)
    if thanked or farewell_open:
        closing["thanked_and_left_contact_open"] = True
    def _plain(text: str) -> str:
        return re.sub(r"[’‘ʼ`]", "'", text or "")

    follow = next((row for row in rows[-6:] if _FOLLOW_UP_RE.search(_plain(row["text"]))), None)
    if follow is not None:
        closing["agreed_follow_up"] = True
        closing["d14_quote"] = str(follow["text"]).strip()
    elif rows and _is_manager_speaker(rows[-1]["speaker"]):
        last = rows[-1]["text"]
        client_spoke = any(_is_client_speaker(row["speaker"]) for row in rows[:-1])
        if client_spoke and not _GOODBYE_RE.search(_plain(last)) and not _THANKS_RE.search(last):
            closing["client_silent_at_end"] = True
            closing["d14_quote"] = str(last).strip() + " — після репліки менеджера відповіді немає"
    data["closing"] = closing
    return data


def repair_goodbye_already_said(facts: dict, dialogue: str) -> dict:
    """Коротка репліка клієнта після прощання менеджера — не обрив дзвінка."""
    data = dict(facts or {})
    rows = _dialogue_rows(dialogue)
    goodbye_at = None
    for index, row in enumerate(rows):
        if _is_manager_speaker(row["speaker"]) and _GOODBYE_RE.search(row["text"]):
            goodbye_at = index
    if goodbye_at is None:
        return data
    client_after = [row["text"] for row in rows[goodbye_at + 1 :] if _is_client_speaker(row["speaker"])]
    shared = dict(data.get("shared_context") or {})
    manager_before = [
        row["text"]
        for row in rows[: goodbye_at + 1]
        if _is_manager_speaker(row["speaker"])
    ]
    def _said_goodbye(text: str) -> bool:
        if _CLIENT_GOODBYE_RE.search(text):
            return True
        # «поки» у довгій репліці означає «ще», а в короткій «все, поки» — прощання.
        return len(_client_words(text)) <= 4 and bool(re.search(r"\bпоки\b", text, re.IGNORECASE))

    client_said_goodbye = any(_said_goodbye(text) for text in client_after)
    if client_said_goodbye and not any(_QUESTION_RE.search(text) for text in manager_before):
        shared["client_ended_call_first"] = True
        data["shared_context"] = shared
        return data
    words = sum(len(re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ']+", text)) for text in client_after)
    if client_said_goodbye or words <= 8:
        shared["client_ended_call_first"] = False
        shared["client_said_no_time_and_hung_up"] = False
        data["shared_context"] = shared
    return data


def _quote_hits_client_line(evidence: str, client_text: str) -> bool:
    quote = re.split(r"\s+[—-]\s+", evidence, maxsplit=1)[0]
    quote = re.sub(r"^\[[^\]]+\]\s*", "", quote)
    quote = re.sub(r"^(Клієнт|Клиент|ch_1)\s*:\s*", "", quote, flags=re.IGNORECASE)
    snippet = re.sub(r"\s+", " ", quote).strip()
    if len(snippet) < 6:
        return False
    folded_line = re.sub(r"\s+", " ", client_text).lower()
    return snippet.lower() in folded_line


def repair_retention_evidence(facts: dict, dialogue: str) -> dict:
    """Пропуск утримання лишається лише з цитати клієнта і опису пропущеної дії."""
    data = dict(facts or {})
    rows = _dialogue_rows(dialogue)
    slip = dict(data.get("slip_handling") or {})
    evidence = [str(item).strip() for item in (slip.get("evidence") or []) if str(item).strip()]
    client_lines = [row["text"] for row in rows if _is_client_speaker(row["speaker"])]
    manager_blob = "\n".join(row["text"] for row in rows if _is_manager_speaker(row["speaker"]))

    def supported(items: list[str]) -> bool:
        for item in items:
            if not _RETENTION_MISS_RE.search(item):
                continue
            if "фрази немає" in item.lower():
                continue
            if any(_quote_hits_client_line(item, line) for line in client_lines):
                return True
        return False

    if slip.get("retention_opportunity_missed") and not supported(evidence):
        slip["retention_opportunity_missed"] = False
        slip["retention_opportunity_note"] = ""

    if not slip.get("retention_opportunity_missed"):
        inferred = _infer_retention_miss(client_lines, manager_blob)
        if inferred:
            slip["retention_opportunity_missed"] = True
            slip["retention_opportunity_note"] = inferred["note"]
            evidence = evidence + [inferred["evidence"]]
    slip["evidence"] = evidence
    data["slip_handling"] = slip
    return data


def _infer_retention_miss(client_lines: list[str], manager_blob: str) -> dict | None:
    limit_line = next((line for line in client_lines if re.search(r"ліміт", line, re.IGNORECASE)), "")
    if limit_line and not re.search(
        r"змін\w{0,8}.{0,24}ліміт|ліміт\w{0,8}.{0,24}змін|порад\w{0,8}.{0,24}ліміт",
        manager_blob,
        re.IGNORECASE,
    ):
        quote = limit_line.strip()
        return {
            "note": "клієнт сказав про ліміти, менеджер не порадив їх змінити",
            "evidence": f"Клієнт: {quote} — менеджер не порадив змінити ліміти",
        }
    return None


def repair_hangup_objections(facts: dict, dialogue: str) -> dict:
    """right_before_client_hangup лише коли після репліки клієнта менеджер уже не говорив."""
    data = dict(facts or {})
    rows = _dialogue_rows(dialogue)
    last_client = None
    for index, row in enumerate(rows):
        if _is_client_speaker(row["speaker"]):
            last_client = index
    prep = dict(data.get("prep") or {})
    objections = []
    for item in prep.get("objections") or []:
        objection = dict(item)
        if not objection.get("right_before_client_hangup"):
            objections.append(objection)
            continue
        quote = str(objection.get("quote") or "")
        found = None
        for index, row in enumerate(rows):
            if _is_client_speaker(row["speaker"]) and _quote_hits_client_line(quote, row["text"]):
                found = index
        manager_after = found is not None and any(
            _is_manager_speaker(row["speaker"]) for row in rows[found + 1 :]
        )
        if found is None or found != last_client or manager_after:
            objection["right_before_client_hangup"] = False
        objections.append(objection)
    prep["objections"] = objections
    data["prep"] = prep
    return data


def apply_call_context(facts: dict, call: dict | None) -> tuple[dict, bool]:
    """Чекбокс або текст «Важливе» вмикають винятки, навіть якщо модель їх пропустила."""
    data = dict(facts or {})
    payload = call or {}
    note = str(payload.get("important_note") or "")
    comment = str(payload.get("qa_comment") or "")
    contact = dict(data.get("contact") or {})
    signed = bool(payload.get("number_signed")) or note_says_number_signed(note, comment)
    if signed:
        contact["exception_number_signed"] = True
    manager_comment = str(payload.get("manager_comment") or "")
    if note_says_messenger(note, comment, manager_comment):
        contact["exception_prior_messenger_contact"] = True
    data["contact"] = contact
    military = bool(payload.get("client_is_military")) or note_says_military(note, comment, manager_comment)
    return data, military


class SlipHandlingFacts(BaseModel):
    client_attempted_to_end_call: bool = False
    reason_stated_by_client: bool = False
    reason_clarified_by_manager: bool = False
    manager_reacted_appropriately: bool = False
    proposed_callback: bool = False
    specified_concrete_time: bool = False
    confirmed_agreement_or_clear_refusal: bool = False
    client_flatly_refused_any_callback: bool = False
    retention_opportunity_missed: bool = False
    retention_opportunity_note: str = ""
    evidence: list[str] = Field(default_factory=list)


class SlipCriticalFacts(BaseModel):
    continued_pitch_after_client_said_cannot_talk: bool = False
    continued_pitch_instead_of_agreeing_callback: bool = False
    asked_irrelevant_questions: bool = False
    artificially_extended_call: bool = False
    delayed_ending_after_callback_agreed: bool = False
    evidence: list[str] = Field(default_factory=list)


class VipShort90sFactsBundle(BaseModel):
    contact: ContactFacts = Field(default_factory=ContactFacts)
    slip_handling: SlipHandlingFacts = Field(default_factory=SlipHandlingFacts)
    slip_critical: SlipCriticalFacts = Field(default_factory=SlipCriticalFacts)
    prep: PrepFacts = Field(default_factory=PrepFacts)
    closing: ClosingFacts = Field(default_factory=ClosingFacts)
    shared_context: SharedContextFacts = Field(default_factory=SharedContextFacts)


def _cap_missed_retention(score: CriterionScore, facts: SlipHandlingFacts) -> CriterionScore:
    evidence = [str(item).strip() for item in (facts.evidence or []) if str(item).strip()]
    evidence = [item for item in evidence if "фрази немає" not in item.lower()]
    if not facts.retention_opportunity_missed or not evidence:
        return score
    note = str(facts.retention_opportunity_note or "").strip() or "не вказано"
    reason = f"Не використано можливість утримання: {note}"
    if score.points > 5.0:
        score.points = 5.0
    if reason not in score.reasons:
        score.reasons.insert(0, reason)
    return score


def score_slip_handling(f: SlipHandlingFacts, ctx: SharedCallContext) -> CriterionScore:
    proposed = bool(f.proposed_callback or ctx.moved_to_messenger)
    if not f.client_attempted_to_end_call:
        return _cap_missed_retention(
            CriterionScore(
                "slip_handling",
                10.0,
                10.0,
                ["Клієнт не намагався завершити дзвінок достроково — критерій не застосовний"],
            ),
            f,
        )
    if ctx.client_ended_call_first or f.client_flatly_refused_any_callback:
        return _cap_missed_retention(
            CriterionScore(
                "slip_handling",
                10.0,
                10.0,
                [
                    "Клієнт завершив дзвінок сам / категорично відмовився від передзвону — не знижується"
                ],
            ),
            f,
        )

    reason_ok = f.reason_stated_by_client or f.reason_clarified_by_manager
    actions = [
        reason_ok,
        f.manager_reacted_appropriately,
        proposed,
        f.specified_concrete_time,
        f.confirmed_agreement_or_clear_refusal,
        not ctx.call_format_prevented_full_flow,
    ]
    missing = actions.count(False)
    if missing == 0:
        scored = CriterionScore("slip_handling", 10.0, 10.0, [])
    elif missing == 1:
        scored = CriterionScore(
            "slip_handling",
            7.5,
            10.0,
            ["Не вистачило однієї дії з утримання контакту"],
        )
    elif missing == 2:
        scored = CriterionScore(
            "slip_handling",
            5.0,
            10.0,
            ["Відреагував на бажання завершити розмову, але не до кінця"],
        )
    elif missing <= 4:
        scored = CriterionScore(
            "slip_handling",
            2.5,
            10.0,
            ["Фактично не працював зі «зливом» клієнта"],
        )
    else:
        scored = CriterionScore(
            "slip_handling",
            0.0,
            10.0,
            ["Не зробив жодної дії з утримання контакту"],
        )
    return _cap_missed_retention(scored, f)


_CRITICAL_FLAGS = (
    (
        "continued_pitch_after_client_said_cannot_talk",
        "Продовжив презентацію, хоча клієнт прямо сказав, що не може говорити",
    ),
    (
        "continued_pitch_instead_of_agreeing_callback",
        "Продовжив продаж замість домовленості про інший контакт",
    ),
    (
        "asked_irrelevant_questions",
        "Ставив питання, що не допомагають зберегти контакт",
    ),
    ("artificially_extended_call", "Штучно затягував дзвінок"),
    (
        "delayed_ending_after_callback_agreed",
        "Затягував завершення після згоди клієнта на передзвін",
    ),
)


def has_critical_slip_violation(f: SlipCriticalFacts) -> tuple[bool, list[str], list[str]]:
    """Прапорець без власного рядка evidence не обнуляє дзвінок."""
    evidence = [str(item).strip() for item in (f.evidence or []) if str(item).strip()]
    true_flags = [label for key, label in _CRITICAL_FLAGS if getattr(f, key)]
    confirmed: list[str] = []
    suspected: list[str] = []
    for index, label in enumerate(true_flags):
        if index < len(evidence):
            confirmed.append(f"{label} {evidence[index]}")
        else:
            suspected.append(f"Підозра на критичну помилку: {label}")
    return bool(confirmed), confirmed, suspected


def score_vip_short_90s(
    facts: VipShort90sFactsBundle,
    ctx: SharedCallContext | None = None,
) -> ScoringResult:
    ctx = ctx or SharedCallContext.from_facts(facts.shared_context.model_dump())
    contact = score_contact(facts.contact)
    slip = score_slip_handling(facts.slip_handling, ctx)
    prep = score_prep(facts.prep, ctx)
    closing = score_closing(facts.closing, ctx)

    is_critical, critical_reasons, suspected = has_critical_slip_violation(facts.slip_critical)
    criteria = [contact, slip, prep, closing]
    before = sum(c.points for c in criteria)
    max_score = sum(c.max_points for c in criteria)
    review_flags = [flag for item in criteria for flag in item.review_flags]
    review_flags.extend(suspected)
    total = 0.0 if is_critical else before

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
        score_before_critical=before,
    )


_LIMITATION_NOT_OBJECTION = re.compile(
    r"активност|не завжди|респект|не можу переглядати|не відстежу",
    re.IGNORECASE,
)
_CLARIFY_NOT_OBJECTION = re.compile(
    r"^(ні[\s-]*ні[, ]*)?(не знаю|как|як|що це)\b",
    re.IGNORECASE,
)
_AGREEMENT_ONLY = re.compile(
    r"^(да|так|угу|ага|добре)([\s,.\-–]+(да|так|угу|ага|добре))*$",
    re.IGNORECASE,
)
_INTERRUPTION = re.compile(r"начальник|мені дзвон|дзвонять", re.IGNORECASE)
_PRIOR_PLAY = re.compile(r"вже грал", re.IGNORECASE)
_REFUSAL_WORD = re.compile(
    r"не треба|не надо|не буду|не хочу|поган|не відігра|не потріб|\bnie\b|не-не",
    re.IGNORECASE,
)
_ALWAYS_OBJECTION_TYPES = {
    "no_payout",
    "bad_bonus_experience",
    "doubts_about_offer",
    "no_desire",
    "no_money",
}
_FORMAL_HANDLING = {
    "formal",
    "ignored",
    "ObjectionHandling.FORMAL",
    "ObjectionHandling.IGNORED",
}
_ALTERNATIVE_AFTER = re.compile(
    r"оберт|гривень|грн|бонус за актив|без вейдж|безвадж",
    re.IGNORECASE,
)
_NOISE_CLIENT = re.compile(
    r"\b(no|ні|нет|sorry|алло|ало|i'm|im)\b",
    re.IGNORECASE,
)


def _client_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ']+", text or "")


def stabilize_short_facts(facts: dict, dialogue: str) -> dict:
    """Знімає хибні заперечення і добудовує факти, які видно з реплік без моделі."""
    data = dict(facts or {})
    rows = _dialogue_rows(dialogue)
    clients = [row for row in rows if _is_client_speaker(row["speaker"])]
    managers = [row for row in rows if _is_manager_speaker(row["speaker"])]
    manager_blob = "\n".join(row["text"] for row in managers)
    prep = dict(data.get("prep") or {})
    objections = [dict(item) for item in (prep.get("objections") or []) if isinstance(item, dict)]

    opening_reply = ""
    for index, row in enumerate(rows):
        if _is_manager_speaker(row["speaker"]) and re.search(r"хвилин|зручно", row["text"], re.IGNORECASE):
            for later in rows[index + 1 :]:
                if _is_client_speaker(later["speaker"]):
                    opening_reply = later["text"]
                    break
            break

    def quote_body(quote: str) -> str:
        folded = re.sub(r"\s+", " ", quote or "").strip()
        body = re.sub(r"^\[[^\]]+\]\s*", "", folded)
        body = re.sub(r"^(Клієнт|Клиент|ch_1)\s*:\s*", "", body, flags=re.IGNORECASE)
        return body.strip(" «»\".,!?")

    def drop_item(item: dict) -> bool:
        body = quote_body(str(item.get("quote") or ""))
        kind = str(item.get("type") or "")
        handling = str(item.get("handling") or "")
        if (
            kind not in _ALWAYS_OBJECTION_TYPES
            and opening_reply
            and body
            and body.lower() in re.sub(r"\s+", " ", opening_reply).lower()
        ):
            return True
        if _LIMITATION_NOT_OBJECTION.search(body):
            return True
        if len(_client_words(body)) <= 4 and _CLARIFY_NOT_OBJECTION.search(body):
            return True
        if kind in {"no_time", "other", "no_desire"} and _AGREEMENT_ONLY.match(body):
            return True
        if _INTERRUPTION.search(body) and not _REFUSAL_WORD.search(body):
            return True
        if _PRIOR_PLAY.search(body) and not _REFUSAL_WORD.search(body):
            return True
        if handling in _FORMAL_HANDLING and re.search(r"ліміт", body, re.IGNORECASE) and not _REFUSAL_WORD.search(body):
            return True
        return False

    kept = []
    for item in objections:
        if drop_item(item):
            continue
        kept.append(item)

    noise_only = bool(clients) and all(
        len(_client_words(row["text"])) <= 4
        and _NOISE_CLIENT.search(row["text"])
        and not _OFFER_REFUSAL_RE.search(row["text"])
        for row in clients
    )
    if noise_only:
        kept = []
        shared = dict(data.get("shared_context") or {})
        shared["client_ended_call_first"] = True
        data["shared_context"] = shared

    client_blob = "\n".join(row["text"] for row in clients)
    slip = dict(data.get("slip_handling") or {})
    if slip.get("client_attempted_to_end_call") and not _END_CALL_RE.search(client_blob):
        if _OFFER_REFUSAL_RE.search(client_blob):
            slip["client_attempted_to_end_call"] = False
            data["slip_handling"] = slip

    if not any(_GOODBYE_RE.search(row["text"]) for row in managers) and managers and not clients:
        shared = dict(data.get("shared_context") or {})
        shared["call_format_prevented_full_flow"] = True
        data["shared_context"] = shared

    shared = dict(data.get("shared_context") or {})
    if shared.get("moved_to_messenger") and not re.search(
        r"viber|вайбер|telegram|телеграм|whatsapp|ватсап|месенджер|напишіть|відпишу|(?<![\w])(?:тг|вб|tg|wa|сигнал|signal)(?![\w])",
        dialogue or "",
        re.IGNORECASE,
    ):
        shared["moved_to_messenger"] = False
        data["shared_context"] = shared

    for item in kept:
        handling = str(item.get("handling") or "")
        if handling not in _FORMAL_HANDLING:
            continue
        body = quote_body(str(item.get("quote") or ""))
        found = None
        if len(body) >= 2:
            for index, row in enumerate(rows):
                if _is_client_speaker(row["speaker"]) and body.lower() in row["text"].lower():
                    found = index
                    break
        offered_after = found is not None and any(
            _is_manager_speaker(row["speaker"]) and _ALTERNATIVE_AFTER.search(row["text"])
            for row in rows[found + 1 :]
        )
        if offered_after:
            item["handling"] = "template_attempt"
            continue
        if str(item.get("type") or "") == "no_time" and re.search(r"не відволікаю", manager_blob, re.IGNORECASE):
            item["handling"] = "resolved_no_check"

    prep["objections"] = kept
    prep["objections_present"] = bool(kept)
    data["prep"] = prep

    crit = dict(data.get("slip_critical") or {})
    if crit.get("asked_irrelevant_questions") and re.search(
        r"не відволікаю|гарного дня|до побачення",
        manager_blob,
        re.IGNORECASE,
    ):
        crit["asked_irrelevant_questions"] = False
    folded = re.sub(r"[^0-9a-zа-яіїєґ]+", "", (dialogue or "").lower())
    grounded = []
    for item in crit.get("evidence") or []:
        compact = re.sub(r"[^0-9a-zа-яіїєґ]+", "", str(item).lower())
        if len(compact) >= 12 and compact[:24] in folded:
            grounded.append(item)
    true_keys = [key for key, _label in _CRITICAL_FLAGS if crit.get(key)]
    for index, key in enumerate(true_keys):
        if index >= len(grounded):
            crit[key] = False
    crit["evidence"] = grounded
    data["slip_critical"] = crit
    return data


def score_vip_short_call(
    facts: dict,
    call: dict | None = None,
    dialogue: str = "",
    source_text: str = "",
) -> dict:
    """Сумісний вхід для app_vip: dict фактів → dict результату для UI/логів."""
    prepared, military = apply_call_context(facts, call)
    heard = dialogue or source_text or ""
    prepared = repair_obvious_contact(prepared, source_text or heard)
    prepared = repair_obvious_closing(prepared, heard)
    prepared = repair_goodbye_already_said(prepared, heard)
    prepared = repair_hangup_objections(prepared, heard)
    prepared = repair_retention_evidence(prepared, heard)
    prepared = stabilize_short_facts(prepared, heard)
    bundle = VipShort90sFactsBundle.model_validate(prepared)
    ctx = SharedCallContext.from_facts(
        bundle.shared_context.model_dump(),
        client_is_military=military,
    )
    result = score_vip_short_90s(bundle, ctx)
    extra = edge_review_flags(dialogue or "")
    if source_text and source_text != dialogue:
        seen = {flag for flag, _key in extra}
        for flag, key in edge_review_flags(source_text):
            if flag not in seen:
                extra.append((flag, key))
    if extra:
        result.review_flags = list(result.review_flags) + [flag for flag, _score in extra]
        by_key = {item.key: item for item in result.criteria}
        for flag, criterion_key in extra:
            item = by_key.get(criterion_key)
            if item is None or item.points >= item.max_points:
                continue
            item.points = item.max_points
            item.reasons = [f"Низька якість краю дзвінка — бал не знижено ({flag})"]
        before = sum(item.points for item in result.criteria)
        result.score_before_critical = before
        result.total_score = 0.0 if result.is_critical_fail else before
        result.percent = (
            round(result.total_score / result.max_score * 100, 1) if result.max_score else 0.0
        )
    return result.to_dict()


_LOW_QUALITY = "[низька якість розпізнавання]"
_SPEAKER_LINE = re.compile(
    r"^(?P<speaker>Менеджер|Клієнт|Клиент|ch_\d+)\s*:\s*(?:\[(?P<time>\d+):(?P<sec>\d+)\]\s*)?(?P<text>.*)$"
)


def _clock_seconds(minutes: str | None, seconds: str | None) -> float | None:
    if minutes is None or seconds is None:
        return None
    return int(minutes) * 60 + int(seconds)


_KNOWN_EDGE_WORDS = {
    "алло", "ало", "добрий", "доброго", "доброе", "день", "дня", "ранок", "ранку", "вітаю",
    "дякую", "вам", "тобі", "гарного", "до", "побачення", "бувайте", "на", "все", "добре",
    "питання", "запитання", "додаткові", "ще", "є", "так", "ні", "да", "хорошо", "менеджер",
    "це", "я", "ваш", "ваша", "із", "з", "у", "в", "і", "та", "ну", "ок", "тоді", "зв'язку",
    "також", "супер", "мене", "звати", "рада", "радий", "була", "був", "бережіть", "себе",
    "па", "добре", "дня",
}


def _has_greeting_element(text: str) -> bool:
    if re.search(r"добр|вітаю|здравств|привет", text or "", re.IGNORECASE):
        return True
    if re.search(r"(?:алло|ало)\s*,\s*[A-ZА-ЯІЇЄҐ]", text or ""):
        return True
    return bool(re.search(r"\b777\b|betking|vegas|бєткінг|вегас", text or "", re.IGNORECASE))


def _short_unknown_line(text: str) -> bool:
    words = re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ']+", text or "")
    if not words or len(words) > 6:
        return False
    unknown = sum(1 for word in words if len(word) > 3 and word.lower() not in _KNOWN_EDGE_WORDS)
    return unknown >= 1


def _distorted(text: str) -> bool:
    raw = text or ""
    if ",," in raw or ".." in raw.replace("...", ""):
        return True
    words = re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ']+", raw)
    if not words:
        return False
    junk = 0
    unknown = 0
    for word in words:
        if re.search(r"[A-Za-z]", word) and re.search(r"[А-Яа-яІіЇїЄєҐґ]", word):
            junk += 1
        elif len(word) <= 2 and word.lower() not in _KNOWN_EDGE_WORDS:
            junk += 1
        elif len(word) > 3 and word.lower() not in _KNOWN_EDGE_WORDS:
            unknown += 1
    if junk and junk / len(words) >= 0.4:
        return True
    return unknown >= 2 and len(words) <= 6


def edge_review_flags(dialogue: str) -> list[tuple[str, str]]:
    """(прапорець, ключ критерію), якщо край репліки менеджера нерозбірливий."""
    manager_lines: list[tuple[float | None, str]] = []
    for raw in (dialogue or "").splitlines():
        match = _SPEAKER_LINE.match(raw.strip())
        if not match:
            continue
        speaker = match.group("speaker")
        if speaker not in {"Менеджер", "ch_0"}:
            continue
        manager_lines.append((_clock_seconds(match.group("time"), match.group("sec")), match.group("text") or ""))
    if not manager_lines:
        return []
    flags: list[tuple[str, str]] = []
    first_time, first_text = manager_lines[0]
    opening = first_time is None or first_time <= 20
    client_said_allo = False
    seen_manager = False
    for raw in (dialogue or "").splitlines():
        match = _SPEAKER_LINE.match(raw.strip())
        if not match:
            continue
        speaker = match.group("speaker")
        text = match.group("text") or ""
        if _is_manager_speaker(speaker):
            seen_manager = True
            continue
        if seen_manager:
            continue
        if _is_client_speaker(speaker) and re.search(r"\b(алло|ало|halo)\b", text, re.IGNORECASE):
            client_said_allo = True
    garbled_opening = _LOW_QUALITY in first_text or _distorted(first_text)
    if opening and (
        (client_said_allo and not _has_greeting_element(first_text))
        or (garbled_opening and not _has_greeting_element(first_text))
        or (garbled_opening and ",," in first_text)
    ):
        flags.append(("greeting_unclear", "contact"))
    last_time = manager_lines[-1][0]
    if last_time is None:
        window = [manager_lines[-1][1]]
    else:
        window = [
            text
            for stamp, text in manager_lines
            if stamp is not None and stamp >= last_time - 15
        ] or [manager_lines[-1][1]]

    def _intelligible(text: str) -> bool:
        if _LOW_QUALITY in text or _distorted(text) or _short_unknown_line(text):
            return False
        return bool(re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ']+", text))

    if not any(_intelligible(text) for text in window):
        flags.append(("closing_unclear", "closing"))
    return flags


def build_perfect_short90s_facts() -> VipShort90sFactsBundle:
    return VipShort90sFactsBundle(
        contact=ContactFacts(
            greeted=True,
            used_client_name=True,
            named_project=True,
            availability_check_done=True,
            availability_check_relevant=True,
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
