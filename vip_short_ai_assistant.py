"""AI-екстракція фактів для VIP Короткий 90 сек і VIP Friendly."""

from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from core.vip_friendly_scoring import VipFriendlyFactsBundle
from core.vip_short_scoring import VipShort90sFactsBundle
from prompts_vip_friendly import get_vip_friendly_analysis_prompt
from prompts_vip_short import get_vip_short_90s_analysis_prompt

logger = logging.getLogger(__name__)

VIP_SHORT_FACTS_CACHE_TAG = "vip_short90s_r1_20260831"
VIP_FRIENDLY_FACTS_CACHE_TAG = "vip_friendly_r1_20260831"


class VipFactsExtractionError(RuntimeError):
    """Помилка витягу фактів — безпечне повідомлення для UI."""


def _extract_json_object(text: str) -> dict | None:
    match = re.search(r"\{[\s\S]*\}", text or "")
    if not match:
        return None
    try:
        return json.loads(match.group())
    except Exception:
        return None


def _call_gpt_json(client, model, prompt: str, dialogue: str, max_output_tokens: int) -> dict:
    """Виклик GPT. Без st.* — викликається з @st.cache_data."""
    full_prompt = f"{prompt}\n\nСИРИЙ ТРАНСКРИПТ:\n{dialogue}"
    tokens_budget = max_output_tokens
    last_error = None
    for attempt in range(2):
        if attempt > 0:
            logger.warning(
                "VIP facts retry %s: invalid JSON from model (%s)", attempt, last_error
            )
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
            content = (res.choices[0].message.content or "") if res.choices else ""
            payload = _extract_json_object(content)
            if payload is not None:
                # allow either root facts or nested {"facts": {...}}
                if isinstance(payload.get("facts"), dict):
                    return dict(payload["facts"])
                return dict(payload)
            last_error = "empty or invalid JSON"
        except Exception as exc:
            last_error = str(exc)
            logger.exception("VIP facts GPT call failed")
        tokens_budget = int(tokens_budget * 1.6)
    raise VipFactsExtractionError(
        "Не вдалося витягти факти з дзвінка (відповідь AI). Спробуйте ще раз."
    )


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
    try:
        return VipShort90sFactsBundle.model_validate(raw or {}).model_dump()
    except ValidationError as exc:
        logger.exception("VIP short facts validation failed")
        raise VipFactsExtractionError(
            "Не вдалося розібрати факти короткого дзвінка. Спробуйте ще раз."
        ) from exc


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
    try:
        return VipFriendlyFactsBundle.model_validate(raw or {}).model_dump()
    except ValidationError as exc:
        logger.exception("VIP friendly facts validation failed")
        raise VipFactsExtractionError(
            "Не вдалося розібрати факти VIP Friendly. Спробуйте ще раз."
        ) from exc


# --- legacy aliases used by older imports ---
def apply_vip_defaults(facts: dict) -> dict:
    """Normalize short-90s facts dict (replaces old red/green defaults)."""
    return VipShort90sFactsBundle.model_validate(facts or {}).model_dump()


def extract_vip_short_facts(client, model, dialogue, qa_comment, important_note, max_output_tokens):
    return extract_vip_short_90s_facts(
        client, model, dialogue, qa_comment, important_note, max_output_tokens
    )
