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

CALL_TYPE_KEYS = {
    CALL_TYPE_SHORT_90S: "vip_short_90s",
    CALL_TYPE_FRIENDLY: "vip_friendly",
}

# Залишено для сумісності імпортів; поля старої red/green картки більше не використовуються в скорингу.
VIP_BONUS_STATUS_OPTIONS = [
    "Бонус нараховано вірно",
    "Бонус нараховано невірно",
    "Бонус не нараховано",
]
