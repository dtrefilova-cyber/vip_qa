"""Константи VIP QA."""

FORBIDDEN_WORDS = [
    "Лотерея",
    "Акція",
    "Розіграш",
    "Реклама",
    "Подарунок",
    "Популяризація",
    "Лотерейний білет",
    "Даруємо",
    "Розігруємо",
    "Конкурс",
    "Кешбек",
    "Компенсація",
    "Повернення",
    "Відшкодуємо",
    "Фріспіни",
    "Безкоштовно",
    "Страхування",
    "страховка",
    "ставка без ризику",
    "фрібет",
    "Бездеп",
]

# Операційна таблиця VIP: аркуш RESULTS (бальні записи)
VIP_SHORT_SHEET_ID = "1ww7dFbI8Gw7Ji96ssgSKBtlvv739xrAL9bNTfCiWqOc"

# Довідник менеджерів (аркуш MANAGERS) + legacy колонкова трекінг-таблиця
VIP_SHORT_MANUAL_TRACKING_SHEET_ID = "1sse7mivevTjwn5PE8o1Nwb26_9PTKXeFrrrTygCL2x0"
VIP_SHORT_MANUAL_TRACKING_WORKSHEET = "RESULTS"
VIP_FRIENDLY_MANUAL_TRACKING_WORKSHEET = "RESULTS FRIENDLY"
VIP_MANAGERS_SHEET_ID = VIP_SHORT_MANUAL_TRACKING_SHEET_ID
VIP_MANAGERS_WORKSHEET = "MANAGERS"

# Журнал оцінок за проєктом (Betking / 777 / Vegas):
# короткі A:M (E — нова колонка після TL, J — формула),
# френдлі O:AD (зсув +1 після insert колонки справа від TL).
VIP_JOURNAL_SHEET_ID = "1-9M9Z4qcZ-5fikWWm-QGBTvjdjwjXnDZjmG4DIHT7Wk"
VIP_JOURNAL_MANAGERS_WORKSHEET = "Менеджери VIP"
VIP_JOURNAL_REVIEWER = "АІ"
VIP_JOURNAL_TZ = "Europe/Kiev"
VIP_JOURNAL_CALL_TYPE_SHORT = "short"
VIP_JOURNAL_CALL_TYPE_FRIENDLY = "friendly"
VIP_JOURNAL_PROJECTS = {
    "betking": {
        "title": "Betking",
        "sheet_id": 445201819,
        "start_row": 3,
    },
    "777": {
        "title": "777",
        "sheet_id": 1229042759,
        "start_row": 3,
    },
    "vegas": {
        "title": "Vegas",
        "sheet_id": 1070088770,
        "start_row": 5,
    },
}

CALL_TYPE_SHORT_90S = "Короткий 120 сек"
CALL_TYPE_SHORT_90S_LEGACY = "Короткий 90 сек"
CALL_TYPE_FRIENDLY = "VIP Friendly (2-й дзвінок)"
CALL_TYPES = [CALL_TYPE_SHORT_90S, CALL_TYPE_FRIENDLY]

CALL_TYPE_KEY_SHORT = "vip_short_90s"
CALL_TYPE_KEY_FRIENDLY = "vip_friendly"

CALL_TYPE_KEYS = {
    CALL_TYPE_SHORT_90S: CALL_TYPE_KEY_SHORT,
    CALL_TYPE_SHORT_90S_LEGACY: CALL_TYPE_KEY_SHORT,
    CALL_TYPE_FRIENDLY: CALL_TYPE_KEY_FRIENDLY,
}

CALL_TYPE_LABELS = {
    CALL_TYPE_KEY_SHORT: CALL_TYPE_SHORT_90S,
    CALL_TYPE_KEY_FRIENDLY: CALL_TYPE_FRIENDLY,
}

CALL_TYPE_MAX_SCORE = {
    CALL_TYPE_KEY_SHORT: 30.0,
    CALL_TYPE_KEY_FRIENDLY: 57.5,
    CALL_TYPE_SHORT_90S: 30.0,
    CALL_TYPE_SHORT_90S_LEGACY: 30.0,
    CALL_TYPE_FRIENDLY: 57.5,
}

# UI slug для session_state / кешу карток (окремо на сторінку)
PAGE_SLUGS = {
    CALL_TYPE_SHORT_90S: "short",
    CALL_TYPE_SHORT_90S_LEGACY: "short",
    CALL_TYPE_FRIENDLY: "friendly",
    CALL_TYPE_KEY_SHORT: "short",
    CALL_TYPE_KEY_FRIENDLY: "friendly",
}

# Поля картки — спільні + контекст скорингу (військовий / підписаний / tech_followup)
CARD_FIELDS_BY_TYPE = {
    CALL_TYPE_KEY_SHORT: [
        "url",
        "project",
        "ret_manager",
        "client_id",
        "call_date",
        "bonus_status",
        "important_note",
        "qa_comment",
        "previous_call_not_service",
        "has_tl_permission",
        "number_signed",
        "client_is_military",
    ],
    CALL_TYPE_KEY_FRIENDLY: [
        "url",
        "project",
        "ret_manager",
        "client_id",
        "call_date",
        "bonus_status",
        "important_note",
        "qa_comment",
        "previous_call_not_service",
        "has_tl_permission",
        "number_signed",
        "client_is_military",
        "tech_followup",
    ],
}

# Інформаційні поля картки (не впливають на бальний скоринг).
VIP_BONUS_STATUS_OPTIONS = [
    "Бонус нараховано вірно",
    "Бонус нараховано невірно",
    "Бонус не нараховано",
]


def resolve_call_type_key(value: str | None) -> str | None:
    """Normalize label or key → storage key (vip_short_90s / vip_friendly)."""
    text = str(value or "").strip()
    if not text:
        return None
    if text in CALL_TYPE_LABELS:
        return text
    if text in CALL_TYPE_KEYS:
        return CALL_TYPE_KEYS[text]
    low = text.lower()
    if "friendly" in low:
        return CALL_TYPE_KEY_FRIENDLY
    if "short" in low or "коротк" in low or "90" in low or "120" in low:
        return CALL_TYPE_KEY_SHORT
    return None


def page_slug(call_type: str) -> str:
    if call_type in PAGE_SLUGS:
        return PAGE_SLUGS[call_type]
    key = resolve_call_type_key(call_type)
    return PAGE_SLUGS.get(key or "", "short")
