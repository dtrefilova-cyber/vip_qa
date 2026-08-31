"""AI-екстракція фактів для VIP Короткий 90 сек і VIP Friendly."""

from __future__ import annotations

import json
import re

import streamlit as st

from core.vip_friendly_scoring import VipFriendlyFactsBundle
from core.vip_short_scoring import VipShort90sFactsBundle
from prompts_vip_friendly import get_vip_friendly_analysis_prompt
from prompts_vip_short import get_vip_short_90s_analysis_prompt

VIP_SHORT_FACTS_CACHE_TAG = "vip_short90s_r1_20260831"
VIP_FRIENDLY_FACTS_CACHE_TAG = "vip_friendly_r1_20260831"


def _extract_json_object(text: str) -> dict | None:
    match = re.search(r"\{[\s\S]*\}", text or "")
    if not match:
        return None
    try:
        return json.loads(match.group())
    except Exception:
        return None


def _call_gpt_json(client, model, prompt: str, dialogue: str, max_output_tokens: int) -> dict:
    full_prompt = f"{prompt}\n\nСИРИЙ ТРАНСКРИПТ:\n{dialogue}"
    tokens_budget = max_output_tokens
    last_error = None
    for attempt in range(2):
        if attempt > 0:
            st.warning(f"Retry attempt {attempt}: невалідний JSON від моделі. Помилка: {last_error}")
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
            payload = _extract_json_object(res.choices[0].message.content)
            if payload is not None:
                # allow either root facts or nested {"facts": {...}}
                if isinstance(payload.get("facts"), dict):
                    return dict(payload["facts"])
                return dict(payload)
            last_error = "empty or invalid JSON"
        except Exception as exc:
            last_error = str(exc)
        tokens_budget = int(tokens_budget * 1.6)
    st.error(f"GPT error (VIP facts): {last_error}")
    return {}


def extract_vip_short_90s_facts(
    client,
    model,
    dialogue,
    qa_comment,
    important_note,
    max_output_tokens,
) -> dict:
    prompt = get_vip_short_90s_analysis_prompt(qa_comment, important_note)
    raw = _call_gpt_json(client, model, prompt, dialogue, max_output_tokens)
    return VipShort90sFactsBundle.model_validate(raw or {}).model_dump()


def extract_vip_friendly_facts(
    client,
    model,
    dialogue,
    qa_comment,
    important_note,
    max_output_tokens,
    *,
    client_is_military: bool | None = None,
    betking_x2_applicable: bool | None = None,
) -> dict:
    prompt = get_vip_friendly_analysis_prompt(
        qa_comment,
        important_note,
        client_is_military=client_is_military,
        betking_x2_applicable=betking_x2_applicable,
    )
    raw = _call_gpt_json(client, model, prompt, dialogue, max_output_tokens)
    return VipFriendlyFactsBundle.model_validate(raw or {}).model_dump()


# --- legacy aliases used by older imports ---
def apply_vip_defaults(facts: dict) -> dict:
    """Normalize short-90s facts dict (replaces old red/green defaults)."""
    return VipShort90sFactsBundle.model_validate(facts or {}).model_dump()


def extract_vip_short_facts(client, model, dialogue, qa_comment, important_note, max_output_tokens):
    return extract_vip_short_90s_facts(
        client, model, dialogue, qa_comment, important_note, max_output_tokens
    )
