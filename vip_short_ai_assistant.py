"""AI-екстракція фактів для VIP-короткого дзвінка."""

import json
import re

import streamlit as st

from prompts_vip_short import get_vip_short_analysis_prompt

EVIDENCE_KEYS = (
    "is_structured_call",
    "answering_machine_detected",
    "client_audio_missing_suspected",
    "is_birthday_greeting",
    "rudeness_detected",
    "objection_ignored",
    "inaccurate_info_suspected",
    "could_not_help_suspected",
    "missing_humanity_suspected",
    "manager_fabricated_client_reason",
    "comment_mismatch_detected",
)

DEFAULT_VIP_FACTS = {
    "is_structured_call": False,
    "answering_machine_detected": False,
    "client_audio_missing_suspected": False,
    "is_birthday_greeting": False,
    "rudeness_detected": False,
    "rudeness_confidence": "low",
    "objection_ignored": False,
    "inaccurate_info_suspected": False,
    "could_not_help_suspected": False,
    "missing_humanity_suspected": False,
    "manager_fabricated_client_reason": False,
    "comment_mismatch_detected": False,
    "evidence": {key: None for key in EVIDENCE_KEYS},
}


def _normalize_evidence_item(value):
    if not isinstance(value, dict):
        return None
    timing = str(value.get("timing") or "").strip()
    quote = str(value.get("quote") or "").strip()
    if not timing and not quote:
        return None
    return {
        "timing": timing,
        "quote": quote,
    }


def normalize_vip_evidence(raw_evidence) -> dict:
    evidence = {key: None for key in EVIDENCE_KEYS}
    if not isinstance(raw_evidence, dict):
        return evidence
    for key in EVIDENCE_KEYS:
        evidence[key] = _normalize_evidence_item(raw_evidence.get(key))
    return evidence


def apply_vip_defaults(facts: dict) -> dict:
    result = dict(DEFAULT_VIP_FACTS)
    incoming = dict(facts or {})
    evidence = normalize_vip_evidence(incoming.pop("evidence", None))
    result.update(incoming)
    result["evidence"] = evidence
    return result


def parse_vip_analysis_response(text):
    match = re.search(r"\{[\s\S]*\}", text or "")
    if not match:
        return None
    payload = json.loads(match.group())
    return apply_vip_defaults(payload.get("facts", {}))


def extract_vip_short_facts(client, model, dialogue, qa_comment, important_note, max_output_tokens):
    prompt = get_vip_short_analysis_prompt(qa_comment, important_note)
    full_prompt = f"{prompt}\n\nСИРИЙ ТРАНСКРИПТ:\n{dialogue}"

    tokens_budget = max_output_tokens
    last_error = None

    for _attempt in range(2):
        if _attempt > 0:
            st.warning(f"Retry attempt {_attempt}: невалідний JSON від моделі. Помилка: {last_error}")
        try:
            res = client.chat.completions.create(
                model=model,
                temperature=0,
                seed=42,
                max_completion_tokens=tokens_budget,
                messages=[
                    {"role": "system", "content": "Return only valid JSON."},
                    {"role": "user", "content": full_prompt},
                ],
            )
            parsed = parse_vip_analysis_response(res.choices[0].message.content)
            if parsed:
                return parsed
            last_error = "empty or invalid JSON"
        except Exception as e:
            last_error = str(e)
        tokens_budget = int(tokens_budget * 1.6)

    st.error(f"GPT error (VIP short): {last_error}")
    return apply_vip_defaults({})
