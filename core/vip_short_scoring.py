"""VIP «Короткий 120 сек» (таймінг 30–120 с) — бальна рубрика (макс. 30), без red/green."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from constants import PROJECT_ASR_PATTERNS
from core.vip_scoring_common import (
    ClosingFacts,
    ContactFacts,
    CriterionScore,
    PrepFacts,
    ScoringResult,
    SharedCallContext,
    SharedContextFacts,
    normalize_for_quote,
    quote_token_overlap,
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


_NAME_TOKEN = r"[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ']{2,}"
_NAME_STOP = {"дня", "вечора", "ранку", "вам", "вас", "день", "вечір"}
_LOW_QUALITY = "[низька якість розпізнавання]"
_CLIENT_REQUEST_NOTE_RE = re.compile(
    r"по\s+запиту|за\s+запитом|запит\w*\s+на\s+дзвін|"
    r"сам\w*\s+прос\w+\s+(?:передзвон|набрат)|просив\w*\s+зателефонув",
    re.IGNORECASE,
)
_CLIENT_REQUEST_LINE_RE = re.compile(r"запит\w*.{0,30}дзвін", re.IGNORECASE)
_DIMINUTIVES = {
    "дмитро": ("діма", "дима", "дімон", "димон"),
    "наталія": ("наталя", "наташа"),
    "наталя": ("наташа", "наталія"),
    "тетяна": ("таня", "танія"),
    "олександр": ("саша",),
    "олександра": ("саша",),
    "єлизавета": ("ліза", "лиза"),
    "анастасія": ("настя",),
    "євгеній": ("женя",),
    "євгенія": ("женя",),
    "валерія": ("лера",),
    "софія": ("соня", "софія", "софия"),
    "софия": ("соня", "софія"),
}
_CALLBACK_LINE_RE = re.compile(
    r"набер|набрат|передзвон|зателефону|понеділ|вівтор|серед|четвер|"
    r"п['’ʼ]ятниц|субот|неділ|завтра|тижн|о \d",
    re.IGNORECASE,
)
_OPEN_CONTACT_RE = re.compile(
    r"на зв'?язку|пишіть|звертайтес|маякуй|скин\w*\s+мені|мені\s+скин\w*|"
    r"напиш\w*\s+мені|чекаю\s+(?:на\s+)?(?:вас|ваш)",
    re.IGNORECASE,
)
_WISH_RE = re.compile(r"бажаю|гарного|тихої|доброї|бережіть", re.IGNORECASE)
_CLIENT_EXIT_RE = re.compile(
    r"гарного\s+(?:вам\s+)?(?:вечора|дня)|до\s+побачення|до\s+свидания|\bпока\b",
    re.IGNORECASE,
)
_PITCH_AFTER_EXIT_RE = re.compile(r"\?|бонус|грат|заход|сайт", re.IGNORECASE)
_FAREWELL_LINE_RE = re.compile(
    r"до\s*побачен|допобач|до\s*свидан|гарного|на все добре|бережіть|бувайте|па-па|\bпока\b",
    re.IGNORECASE,
)
_CALLBACK_AGREEMENT_RE = re.compile(
    r"коли|котр|о \d|понеділ|вівтор|серед|четвер|п['’ʼ]ятниц|субот|неділ|завтра|тижн|"
    r"зателефон|набрат|передзвон",
    re.IGNORECASE,
)


def _manager_lines(dialogue: str) -> list[str]:
    return [
        row["text"]
        for row in _dialogue_rows(dialogue)
        if _is_manager_speaker(row["speaker"])
    ]


def _glued_speaker_texts(dialogue: str, speaker_ok) -> list[str]:
    glued: list[str] = []
    for row in _dialogue_rows(dialogue):
        if not speaker_ok(row["speaker"]):
            continue
        if glued and glued[-1][0] == row["speaker"]:
            glued[-1][1] += " " + (row["text"] or "")
        else:
            glued.append([row["speaker"], row["text"] or ""])
    return [text for _speaker, text in glued]


def _quote_in_manager_lines(dialogue: str, quote: str) -> bool:
    needle = normalize_for_quote(quote)[:48]
    if len(needle) < 4:
        return False
    lines = _manager_lines(dialogue)
    glued = _glued_speaker_texts(dialogue, _is_manager_speaker)
    for text in lines + glued:
        if needle in normalize_for_quote(text):
            return True
    for index, text in enumerate(lines):
        haystacks = [text]
        if index + 1 < len(lines):
            haystacks.append(text + " " + lines[index + 1])
        if any(quote_token_overlap(quote, hay) >= 0.8 for hay in haystacks):
            return True
    return False


def verify_contact_quotes(contact: dict, *dialogues: str) -> dict:
    """Цитата підтверджена, якщо вона є в репліці менеджера хоча б в одному тексті."""
    data = dict(contact or {})
    texts = [text for text in dialogues if text]
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
        if not any(_quote_in_manager_lines(text, quote) for text in texts):
            data[flag] = False
    return data


def _name_token_ok(token: str) -> bool:
    return bool(token) and token.casefold() not in _NAME_STOP


def _client_name_in_lines(lines: list[str]) -> bool:
    intro = "\n".join(lines[:4])
    blob = "\n".join(lines)
    first = lines[0] if lines else ""
    patterns = (
        re.compile(rf"(?i:алло|ало)\s*,\s*({_NAME_TOKEN})"),
        re.compile(
            rf"(?i:добрий|доброго)\s+(?i:дня|вечора|ранку)?\s*,?\s*({_NAME_TOKEN})"
        ),
        re.compile(rf"({_NAME_TOKEN})\s*,?\s*(?i:добрий|доброго)"),
    )
    for pattern, source in (
        (patterns[0], blob),
        (patterns[1], intro),
        (patterns[2], intro),
    ):
        for match in pattern.finditer(source):
            if _name_token_ok(match.group(1)):
                return True
    two = re.match(rf"({_NAME_TOKEN})\s+({_NAME_TOKEN})", first)
    if two and _name_token_ok(two.group(1)) and _name_token_ok(two.group(2)):
        return True
    return False


def _normalize_project_key(value: str) -> str:
    text = str(value or "").strip().lower().replace("’", "'")
    if text in {"betking", "bet king", "беткінг", "бєткінг"} or "betking" in text:
        return "betking"
    if "777" in text or "сімки" in text:
        return "777"
    if "vegas" in text or "вегас" in text:
        return "vegas"
    return text


def _projects_mentioned(text: str) -> set[str]:
    found = set()
    for key, pattern in PROJECT_ASR_PATTERNS.items():
        if re.search(pattern, text or "", re.IGNORECASE):
            found.add(key)
    return found


def _project_signal(lines: list[str], card_project: str) -> str:
    """match | mismatch | unclear | '' — лише перші 4 репліки менеджера."""
    intro = "\n".join(lines[:4])
    found = _projects_mentioned(intro)
    card = _normalize_project_key(card_project)
    if card in PROJECT_ASR_PATTERNS and card in found:
        return "match"
    others = found - ({card} if card in PROJECT_ASR_PATTERNS else set())
    if card in PROJECT_ASR_PATTERNS and others:
        return "mismatch"
    if not card and found:
        return "match"
    if re.search(r"батьк\w*", intro, re.IGNORECASE):
        return "unclear"
    if _LOW_QUALITY in intro and re.search(r"сайт\w*\s+\S+", intro, re.IGNORECASE):
        return "unclear"
    return ""


def _manager_name_forms(ret_manager: str) -> list[str]:
    parts = [part for part in re.split(r"\s+", str(ret_manager or "").strip()) if part]
    given = parts[1] if len(parts) >= 2 else (parts[0] if parts else "")
    given = given.casefold().replace("’", "'")
    forms = []
    if given:
        forms.append(given)
        forms.extend(_DIMINUTIVES.get(given, ()))
    unique = []
    for form in forms:
        if form and form not in unique:
            unique.append(form)
    return unique


def _manager_introduced(lines: list[str], ret_manager: str) -> bool:
    blob = "\n".join(lines)
    intro = "\n".join(lines[:4])
    first = lines[0] if lines else ""
    if _SELF_INTRO.search(blob):
        return True
    if re.search(rf"\bце\s+{_NAME_TOKEN}", intro):
        return True
    if re.search(r"\bцей\s+[а-яіїєґ']{3,}", first, re.IGNORECASE):
        return True
    for name in _manager_name_forms(ret_manager):
        if re.search(
            rf"\b(?:це|цей|я|мене звати)\s+{re.escape(name)}\b",
            blob,
            re.IGNORECASE,
        ):
            return True
    return False


def _append_flag(data: dict, flag: str) -> None:
    flags = list(data.get("_review_flags") or [])
    if flag not in flags:
        flags.append(flag)
    data["_review_flags"] = flags


def repair_obvious_contact(facts: dict, *dialogues: str, call: dict | None = None) -> dict:
    """Позитивний факт = OR по всіх текстах. Без збігу false лишається false."""
    data = dict(facts or {})
    texts = [text for text in dialogues if text]
    contact = verify_contact_quotes(dict(data.get("contact") or {}), *texts)
    payload = call or {}
    card_project = str(payload.get("project") or "")
    ret_manager = str(payload.get("ret_manager") or "")
    greeted = used_name = named_project = introduced = availability = False
    saw_mismatch = saw_unclear = False
    for dialogue in texts:
        lines = _manager_lines(dialogue)
        blob = "\n".join(lines)
        if re.search(r"добр|вітаю|здравств|привет", blob, re.IGNORECASE):
            greeted = True
        if _client_name_in_lines(lines):
            used_name = True
        signal = _project_signal(lines, card_project)
        if signal == "match":
            named_project = True
        elif signal == "mismatch":
            saw_mismatch = True
        elif signal == "unclear":
            saw_unclear = True
        if _manager_introduced(lines, ret_manager):
            introduced = True
        if re.search(r"хвилин|зручно|є час|можете говорити|можете зараз", blob, re.IGNORECASE):
            availability = True
    if greeted:
        contact["greeted"] = True
    if used_name:
        contact["used_client_name"] = True
    if named_project:
        contact["named_project"] = True
    elif saw_mismatch:
        contact["named_project"] = False
        _append_flag(data, "project_mismatch")
    if saw_unclear and not named_project and not saw_mismatch:
        _append_flag(data, "project_unclear")
    if introduced:
        contact["manager_introduced_self"] = True
    if availability:
        contact["availability_check_done"] = True
        contact["availability_check_relevant"] = True
    data["contact"] = contact
    return data


_GOODBYE_RE = re.compile(
    r"гарного|до побачення|на все добре|бережіть себе|па-па|бувайте|до свидания|до зв'?язку|на зв'?язку",
    re.IGNORECASE,
)
_FOLLOW_UP_RE = re.compile(
    r"ще на зв'?язку|спишемо|списатис|напишемо|напишу вам|домовились|"
    r"наберу|наберемо|передзвоню|зателефоную|"
    r"набрати.{0,30}(?:понеділ|вівтор|серед|четвер|п['’ʼ]ятниц|субот|неділ|завтра|тижн)",
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
    tail = blob
    if len(manager) < 6:
        tail = blob + "\n" + (dialogue or "")[-400:]
    open_contact = _OPEN_CONTACT_RE.search(tail)
    warmth = _THANKS_RE.search(tail) or _WISH_RE.search(tail)
    if open_contact and warmth:
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
        words = re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ']+", last or "")
        connection_check = bool(
            re.search(r"\b(?:алло|ало)\b|ви мене чуєте", last or "", re.IGNORECASE)
        ) and len(words) <= 8
        if client_spoke and connection_check:
            closing["connection_dropped"] = True
            closing["client_silent_at_end"] = True
            closing["d14_quote"] = str(last).strip()
        elif client_spoke and not _GOODBYE_RE.search(_plain(last)) and not _THANKS_RE.search(last):
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


def _manager_requested_call(*dialogues: str) -> bool:
    for dialogue in dialogues:
        for line in _manager_lines(dialogue or ""):
            if _CLIENT_REQUEST_LINE_RE.search(line):
                return True
    return False


def mark_client_requested_call(contact: dict, call: dict | None, *dialogues: str) -> dict:
    data = dict(contact or {})
    payload = call or {}
    note = str(payload.get("important_note") or "")
    comment = str(payload.get("qa_comment") or "")
    if _CLIENT_REQUEST_NOTE_RE.search(note) or _CLIENT_REQUEST_NOTE_RE.search(comment) or _manager_requested_call(*dialogues):
        data["exception_client_requested_call"] = True
    return data


def apply_call_context(facts: dict, call: dict | None, *dialogues: str) -> tuple[dict, bool]:
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
    contact = mark_client_requested_call(contact, payload, *dialogues)
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


def _client_exit_followed_by_farewell_only(dialogue: str) -> bool:
    """Після останньої репліки клієнта менеджер сказав не більше одного прощання."""
    rows = _dialogue_rows(dialogue)
    last_client = None
    for index, row in enumerate(rows):
        if _is_client_speaker(row["speaker"]):
            last_client = index
    if last_client is None:
        return True
    manager_after = [row for row in rows[last_client + 1 :] if _is_manager_speaker(row["speaker"])]
    if not manager_after:
        return True
    non_farewell = [row for row in manager_after if not _FAREWELL_LINE_RE.search(row["text"] or "")]
    farewells = [row for row in manager_after if _FAREWELL_LINE_RE.search(row["text"] or "")]
    return not non_farewell and len(farewells) <= 1


def score_slip_handling(
    f: SlipHandlingFacts,
    ctx: SharedCallContext,
    dialogue: str = "",
) -> CriterionScore:
    proposed = bool(f.proposed_callback or ctx.moved_to_messenger)
    client_ended = bool(ctx.client_ended_call_first)
    if dialogue and not _client_exit_followed_by_farewell_only(dialogue):
        client_ended = False
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
    if client_ended or f.client_flatly_refused_any_callback:
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
    dialogue: str = "",
) -> ScoringResult:
    ctx = ctx or SharedCallContext.from_facts(facts.shared_context.model_dump())
    contact = score_contact(facts.contact)
    slip = score_slip_handling(facts.slip_handling, ctx, dialogue)
    prep = score_prep(facts.prep, ctx)
    closing = score_closing(facts.closing, ctx)

    is_critical, critical_reasons, suspected = has_critical_slip_violation(facts.slip_critical)
    criteria = [contact, slip, prep, closing]
    if is_critical:
        slip.points = 0.0
        slip.reasons = list(critical_reasons) or ["Критична помилка при роботі зі зливом"]
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
    dropped_unclear = False
    for item in objections:
        if drop_item(item):
            continue
        if _quote_is_unclear_asr(str(item.get("quote") or ""), clients, _speaker_is_cyrillic(managers)):
            dropped_unclear = True
            continue
        kept.append(item)
    if dropped_unclear:
        _append_flag(data, "prep_unclear_asr")

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
    manager_cyr = _speaker_is_cyrillic(managers)
    if slip.get("client_attempted_to_end_call"):
        evidence = [str(item) for item in (slip.get("evidence") or []) if str(item).strip()]
        if evidence and all(_quote_is_unclear_asr(item, clients, manager_cyr) for item in evidence):
            slip["client_attempted_to_end_call"] = False
            _append_flag(data, "slip_unclear_asr")
        elif _client_stayed_after_slip(rows):
            slip["client_attempted_to_end_call"] = False
        elif not _END_CALL_RE.search(client_blob) and _OFFER_REFUSAL_RE.search(client_blob):
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


def _latin_ratio(text: str) -> float:
    letters = re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґЁё]", text or "")
    if not letters:
        return 0.0
    latin = sum(1 for char in letters if "a" <= char.lower() <= "z")
    return latin / len(letters)


def _speaker_is_cyrillic(rows: list[dict]) -> bool:
    blob = " ".join(row.get("text") or "" for row in rows)
    letters = re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґЁё]", blob)
    if not letters:
        return False
    cyrillic = sum(1 for char in letters if not ("a" <= char.lower() <= "z"))
    return cyrillic / len(letters) >= 0.5


def _text_unclear_asr(text: str, manager_cyrillic: bool) -> bool:
    if _LOW_QUALITY in (text or ""):
        return True
    return bool(manager_cyrillic and _latin_ratio(text) >= 0.6)


def _quote_is_unclear_asr(quote: str, clients: list[dict], manager_cyrillic: bool) -> bool:
    body = re.sub(r"^\[[^\]]+\]\s*", "", quote or "")
    body = re.sub(r"^(?:Клієнт|Клиент|ch_1)\s*:\s*", "", body, flags=re.IGNORECASE).strip()
    if _text_unclear_asr(quote, manager_cyrillic) or _text_unclear_asr(body, manager_cyrillic):
        return True
    for row in clients:
        line = row.get("text") or ""
        if body and len(body) >= 3 and body.lower() in line.lower() and _text_unclear_asr(line, manager_cyrillic):
            return True
    return False


def _client_stayed_after_slip(rows: list[dict]) -> bool:
    times = [row["time"] for row in rows if row.get("time") is not None]
    if not times or max(times) < 45:
        return False
    if any(
        _is_client_speaker(row["speaker"]) and _CLIENT_EXIT_RE.search(row["text"] or "")
        for row in rows
    ):
        return False
    manager_cyr = _speaker_is_cyrillic([row for row in rows if _is_manager_speaker(row["speaker"])])
    slip_at = None
    for index, row in enumerate(rows):
        if not _is_client_speaker(row["speaker"]):
            continue
        if _END_CALL_RE.search(row["text"] or "") or _text_unclear_asr(row["text"] or "", manager_cyr):
            slip_at = index
            break
    if slip_at is None:
        return False
    substantive = 0
    for row in rows[slip_at + 1 :]:
        if not _is_client_speaker(row["speaker"]):
            continue
        if len(_client_words(row["text"])) >= 3 and not _text_unclear_asr(row["text"] or "", manager_cyr):
            substantive += 1
    return substantive >= 3


def _evidence_is_grounded(item: str, dialogue: str) -> bool:
    folded = re.sub(r"[^0-9a-zа-яіїєґ]+", "", (dialogue or "").lower())
    compact = re.sub(r"[^0-9a-zа-яіїєґ]+", "", str(item).lower())
    return len(compact) >= 12 and compact[:24] in folded


def _ground_critical(crit: dict, dialogue: str) -> dict:
    grounded = [item for item in (crit.get("evidence") or []) if _evidence_is_grounded(str(item), dialogue)]
    true_keys = [key for key, _label in _CRITICAL_FLAGS if crit.get(key)]
    for index, key in enumerate(true_keys):
        if index >= len(grounded):
            crit[key] = False
    crit["evidence"] = grounded
    return crit


def _groundable_pair(dialogue: str, client_text: str, manager_text: str) -> str:
    snippet = (client_text or "").strip()
    index = (dialogue or "").lower().find(snippet[:48].lower()) if snippet else -1
    if index >= 0:
        window = re.sub(r"\s+", " ", (dialogue or "")[index : index + 90])
    else:
        window = snippet
    return f"{window.strip()} → {(manager_text or '').strip()}"


def detect_ignored_client_exit(dialogue: str) -> dict:
    """Після явного прощання клієнта менеджер продовжив розмову по суті."""
    rows = _dialogue_rows(dialogue)
    goodbyes = [
        index
        for index, row in enumerate(rows)
        if _is_client_speaker(row["speaker"]) and _CLIENT_EXIT_RE.search(row["text"] or "")
    ]
    result = {
        "continued_pitch_instead_of_agreeing_callback": False,
        "artificially_extended_call": False,
        "evidence": [],
    }
    if not goodbyes:
        return result
    pitches = []
    for row in rows[goodbyes[0] + 1 :]:
        if not _is_manager_speaker(row["speaker"]):
            continue
        text = row["text"] or ""
        if _FAREWELL_LINE_RE.search(text) or _CALLBACK_AGREEMENT_RE.search(text):
            continue
        if _PITCH_AFTER_EXIT_RE.search(text):
            pitches.append(row)
    if len(pitches) < 2:
        return result
    result["continued_pitch_instead_of_agreeing_callback"] = True
    if len(goodbyes) >= 2:
        result["artificially_extended_call"] = True
    client_text = rows[goodbyes[0]]["text"] or ""
    for pitch in pitches[:2]:
        result["evidence"].append(_groundable_pair(dialogue, client_text, pitch["text"] or ""))
    return result


def _merge_ignored_exit(facts: dict, dialogue: str) -> dict:
    data = dict(facts or {})
    detected = detect_ignored_client_exit(dialogue)
    if not detected["continued_pitch_instead_of_agreeing_callback"]:
        return data
    crit = dict(data.get("slip_critical") or {})
    crit["continued_pitch_instead_of_agreeing_callback"] = True
    if detected["artificially_extended_call"]:
        crit["artificially_extended_call"] = True
    crit["evidence"] = list(crit.get("evidence") or []) + list(detected["evidence"])
    data["slip_critical"] = _ground_critical(crit, dialogue)
    shared = dict(data.get("shared_context") or {})
    shared["client_ended_call_first"] = False
    data["shared_context"] = shared
    return data


def _apply_callback_follow_up(facts: dict, dialogue: str) -> dict:
    data = dict(facts or {})
    slip = data.get("slip_handling") or {}
    if not (
        slip.get("proposed_callback")
        and slip.get("specified_concrete_time")
        and slip.get("confirmed_agreement_or_clear_refusal")
        and not slip.get("client_flatly_refused_any_callback")
    ):
        return data
    closing = dict(data.get("closing") or {})
    closing["agreed_follow_up"] = True
    quote = ""
    for text in reversed(_manager_lines(dialogue)):
        if _CALLBACK_LINE_RE.search(re.sub(r"[’‘ʼ`]", "'", text or "")):
            quote = str(text).strip()
            break
    if quote:
        closing["d14_quote"] = quote
    elif not str(closing.get("d14_quote") or "").strip():
        closing["d14_quote"] = "домовились про передзвін"
    data["closing"] = closing
    return data


def score_vip_short_call(
    facts: dict,
    call: dict | None = None,
    dialogue: str = "",
    source_text: str = "",
) -> dict:
    """Сумісний вхід для app_vip: dict фактів → dict результату для UI/логів."""
    heard = dialogue or source_text or ""
    prepared, military = apply_call_context(facts, call, heard, source_text or "")
    prepared = repair_obvious_contact(prepared, heard, source_text or "", call=call)
    prepared = repair_obvious_closing(prepared, heard)
    callback_text = heard
    if not any(_CALLBACK_LINE_RE.search(re.sub(r"[’‘ʼ`]", "'", line)) for line in _manager_lines(heard)):
        callback_text = source_text or heard
    prepared = _apply_callback_follow_up(prepared, callback_text)
    prepared = repair_goodbye_already_said(prepared, heard)
    prepared = repair_hangup_objections(prepared, heard)
    prepared = repair_retention_evidence(prepared, heard)
    prepared = stabilize_short_facts(prepared, heard)
    prepared = _merge_ignored_exit(prepared, heard)
    review_flags = [str(flag) for flag in (prepared.pop("_review_flags", []) or [])]
    bundle = VipShort90sFactsBundle.model_validate(prepared)
    ctx = SharedCallContext.from_facts(
        bundle.shared_context.model_dump(),
        client_is_military=military,
    )
    result = score_vip_short_90s(bundle, ctx, heard)
    extra = edge_review_flags(dialogue or "")
    if source_text and source_text != dialogue:
        seen = {flag for flag, _key in extra}
        for flag, key in edge_review_flags(source_text):
            if flag not in seen:
                extra.append((flag, key))
    if "project_unclear" in review_flags and ("project_unclear", "contact") not in extra:
        extra.append(("project_unclear", "contact"))
    if review_flags:
        result.review_flags = list(result.review_flags) + [
            flag for flag in review_flags if flag not in result.review_flags
        ]
    if extra:
        result.review_flags = list(dict.fromkeys(list(result.review_flags) + [flag for flag, _score in extra]))
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
