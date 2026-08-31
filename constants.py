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

# Таблиця "VIP короткі": аркуш MANAGERS і RESULTS
VIP_SHORT_SHEET_ID = "1ww7dFbI8Gw7Ji96ssgSKBtlvv739xrAL9bNTfCiWqOc"

CALL_TYPE_SHORT_90S = "Короткий 90 сек"
CALL_TYPE_FRIENDLY = "VIP Friendly (2-й дзвінок)"
CALL_TYPES = [CALL_TYPE_SHORT_90S, CALL_TYPE_FRIENDLY]

CALL_TYPE_KEY_SHORT = "vip_short_90s"
CALL_TYPE_KEY_FRIENDLY = "vip_friendly"

CALL_TYPE_KEYS = {
    CALL_TYPE_SHORT_90S: CALL_TYPE_KEY_SHORT,
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
    CALL_TYPE_FRIENDLY: 57.5,
}

# UI slug для session_state / кешу карток (окремо на сторінку)
PAGE_SLUGS = {
    CALL_TYPE_SHORT_90S: "short",
    CALL_TYPE_FRIENDLY: "friendly",
    CALL_TYPE_KEY_SHORT: "short",
    CALL_TYPE_KEY_FRIENDLY: "friendly",
}

# Поля картки — однакові для обох типів (інформаційні; на бал не впливають, окрім контексту Friendly)
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
    if "short" in low or "коротк" in low or "90" in low:
        return CALL_TYPE_KEY_SHORT
    return None


def page_slug(call_type: str) -> str:
    if call_type in PAGE_SLUGS:
        return PAGE_SLUGS[call_type]
    key = resolve_call_type_key(call_type)
    return PAGE_SLUGS.get(key or "", "short")
