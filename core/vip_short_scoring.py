"""Детермінований вердикт VIP-короткого дзвінка: red / green / review.

GPT дає тільки факти (vip_short_ai_assistant.extract_vip_short_facts).
Статус бонусу і ручні прапорці QA приходять у call dict.
Вся логіка вердикту — тут, кодом, без винятків.
"""

from qa_comments import detect_forbidden_phrases_in_dialogue


def _evidence_suffix(evidence) -> str:
    if not isinstance(evidence, dict):
        return ""
    timing = str(evidence.get("timing") or "").strip()
    quote = str(evidence.get("quote") or "").strip()
    bits = []
    if timing:
        bits.append(timing)
    if quote:
        bits.append(f"«{quote}»")
    if not bits:
        return ""
    return f" ({' | '.join(bits)})"


def _with_evidence(text: str, evidence) -> str:
    return f"{text}{_evidence_suffix(evidence)}"


def _fact_evidence(facts: dict, key: str):
    evidence = facts.get("evidence") or {}
    if not isinstance(evidence, dict):
        return None
    return evidence.get(key)


def score_vip_short_call(facts: dict, call: dict, dialogue: str) -> dict:
    """
    call — ручні поля кволіті:
      previous_call_not_service, days_since_last_service_30plus,
      has_tl_permission, qa_comment, bonus_issue, needs_callback, callback_happened.
    Повертає {"verdict": "red"|"green", "verdict_reasons": [...], "review_flags": [...]}
    """
    reasons = []
    review_flags = []

    forbidden_found = detect_forbidden_phrases_in_dialogue(dialogue)

    previous_call_not_service = bool(call.get("previous_call_not_service"))
    days_30plus = bool(call.get("days_since_last_service_30plus"))
    has_tl_permission = bool(call.get("has_tl_permission"))
    qa_comment = str(call.get("qa_comment") or "").strip()
    bonus_issue = bool(call.get("bonus_issue"))
    needs_callback = bool(call.get("needs_callback"))
    callback_happened = call.get("callback_happened")

    if facts.get("is_birthday_greeting"):
        return {
            "verdict": "green",
            "verdict_reasons": [
                _with_evidence(
                    "Привітання з Днем народження",
                    _fact_evidence(facts, "is_birthday_greeting"),
                )
            ],
            "review_flags": [],
        }

    if facts.get("answering_machine_detected"):
        return {
            "verdict": "red",
            "verdict_reasons": [
                _with_evidence(
                    "На лінії не було живого клієнта (автовідповідач/утримання/обрив зв'язку) — "
                    "реальної розмови не відбулось",
                    _fact_evidence(facts, "answering_machine_detected"),
                )
            ],
            "review_flags": [],
        }

    # Дозвіл ТЛ — єдина підстава для звільнення від вимоги структури,
    # і лише якщо не минуло 30+ днів з останньої сервісної розмови.
    structure_exempt = has_tl_permission and not days_30plus
    if not facts.get("is_structured_call") and not structure_exempt:
        reasons.append(
            _with_evidence(
                "Дзвінок без структури і без дозволу ТЛ",
                _fact_evidence(facts, "is_structured_call"),
            )
        )

    if previous_call_not_service:
        reasons.append("Попередній дзвінок не був сервісним")

    if days_30plus:
        reasons.append("30+ днів з останньої сервісної розмови — дзвінок мав бути сервісним")

    if bonus_issue:
        reasons.append("Проблема з нарахуванням бонусу")

    if needs_callback and not callback_happened:
        reasons.append("Потрібен був повторний дзвінок, але його не було")

    if forbidden_found:
        reasons.append(f"Заборонені слова: {', '.join(forbidden_found)}")

    if not qa_comment:
        reasons.append("Відсутній коментар по дзвінку")

    if facts.get("rudeness_detected") and facts.get("rudeness_confidence") in ("medium", "high"):
        reasons.append(
            _with_evidence(
                "Виявлено грубість/хамство",
                _fact_evidence(facts, "rudeness_detected"),
            )
        )

    if facts.get("manager_fabricated_client_reason"):
        reasons.append(
            _with_evidence(
                "Менеджер \"зливає\" розмову: фабрикує відповідь/стан/причину за клієнта "
                "замість реальної відповіді, і на цьому згортає розмову",
                _fact_evidence(facts, "manager_fabricated_client_reason"),
            )
        )

    if facts.get("comment_mismatch_detected"):
        reasons.append(
            _with_evidence(
                "Коментар не відповідає змісту дзвінка",
                _fact_evidence(facts, "comment_mismatch_detected"),
            )
        )

    # --- Критерії з Гайду, раніше були лише review, тепер RED напряму ---
    # (objection_ignored, inaccurate_info_suspected, could_not_help_suspected,
    # missing_humanity_suspected прямо названі критичними в Гайд_коротких_ВІП —
    # переведено з review_flags у reasons)
    if facts.get("objection_ignored"):
        reasons.append(
            _with_evidence(
                "Ігнор заперечення або мінімальне опрацювання",
                _fact_evidence(facts, "objection_ignored"),
            )
        )
    if facts.get("inaccurate_info_suspected"):
        reasons.append(
            _with_evidence(
                "Надання недостовірної інформації",
                _fact_evidence(facts, "inaccurate_info_suspected"),
            )
        )
    if facts.get("could_not_help_suspected"):
        reasons.append(
            _with_evidence(
                "Не допоміг клієнту у питанні, яке міг вирішити",
                _fact_evidence(facts, "could_not_help_suspected"),
            )
        )
    if facts.get("missing_humanity_suspected"):
        reasons.append(
            _with_evidence(
                "Відсутня невимушеність і базова людяність, коли вона була необхідна",
                _fact_evidence(facts, "missing_humanity_suspected"),
            )
        )

    verdict = "red" if reasons else "green"
    if verdict == "green" and not review_flags:
        reasons = ["Дзвінок без зауважень."]

    return {
        "verdict": verdict,
        "verdict_reasons": reasons,
        "review_flags": review_flags,
    }
