"""AI-екстракція фактів для VIP Короткий 90 сек і VIP Friendly."""

from __future__ import annotations

import json
import logging
import re
import time

from pydantic import ValidationError

from core.vip_friendly_scoring import VipFriendlyFactsBundle
from core.vip_short_scoring import VipShort90sFactsBundle
from prompts_vip_friendly import get_vip_friendly_analysis_prompt
from prompts_vip_short import get_vip_short_90s_analysis_prompt

logger = logging.getLogger(__name__)

VIP_SHORT_FACTS_CACHE_TAG = "vip_short90s_r2_20260917"
VIP_FRIENDLY_FACTS_CACHE_TAG = "vip_friendly_r2_20260917"

# 1 основний виклик + 2 повтори при битому JSON / ValidationError.
FACTS_EXTRACT_ATTEMPTS = 2
FACTS_RETRY_DELAY_SEC = 0.8


class VipFactsExtractionError(RuntimeError):
    """Помилка витягу фактів — безпечне повідомлення для UI."""


def user_safe_analysis_error(exc: BaseException) -> str:
    """Коротке повідомлення для QA без сирих stack/secret деталей."""
    if isinstance(exc, VipFactsExtractionError):
        return str(exc)
    msg = str(exc or "").lower()
    name = type(exc).__name__.lower()
    combined = f"{name} {msg}"
    if "streamlit" in name or "cannot be called" in msg or "cached" in msg:
        return (
            "Тимчасова помилка інтерфейсу під час аналізу. "
            "Оновіть сторінку і спробуйте ще раз."
        )
    if any(
        token in combined
        for token in ("timeout", "timed out", "time out", "readtimeout", "connecttimeout")
    ):
        return "Мережевий таймаут під час аналізу. Спробуйте ще раз."
    if any(
        token in combined
        for token in ("deepgram", "payload_error", "failed to parse url", "transcript")
    ):
        return "Не вдалося розпізнати аудіо. Перевірте посилання і спробуйте ще раз."
    if any(
        token in combined
        for token in ("connection", "connecterror", "network", "temporarily unavailable")
    ):
        return "Немає зв'язку з сервісом аналізу. Спробуйте ще раз."
    if any(token in combined for token in ("openai", "rate limit", "429", "apierror")):
        return "Помилка AI-моделі. Спробуйте ще раз за хвилину."
    if any(token in combined for token in ("json", "validation", "pydantic", "parse")):
        return "Не вдалося розібрати відповідь AI. Спробуйте ще раз."
    return (
        "Аналіз не завершився через технічну помилку. "
        "Спробуйте ще раз. Якщо повторюється — повідомте розробника."
    )


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


def _validate_facts_bundle(kind: str, raw: dict, bundle_cls):
    try:
        return bundle_cls.model_validate(raw or {}).model_dump()
    except ValidationError as exc:
        logger.warning("VIP %s facts validation failed: %s", kind, exc)
        raise VipFactsExtractionError(
            "Не вдалося розібрати факти VIP Friendly. Спробуйте ще раз."
            if kind == "friendly"
            else "Не вдалося розібрати факти короткого дзвінка. Спробуйте ще раз."
        ) from exc


def _extract_facts_with_retry(kind: str, client, model, prompt, dialogue, max_output_tokens, bundle_cls):
    """Повторює GPT+валідацію 1–2 рази з паузою — transient JSON/мережа."""
    last_error: BaseException | None = None
    tokens = max_output_tokens
    attempts = max(1, int(FACTS_EXTRACT_ATTEMPTS))
    for attempt in range(attempts):
        try:
            raw = _call_gpt_json(client, model, prompt, dialogue, tokens)
            return _validate_facts_bundle(kind, raw, bundle_cls)
        except VipFactsExtractionError as exc:
            last_error = exc
            logger.warning(
                "VIP %s facts attempt %s/%s failed: %s: %s",
                kind,
                attempt + 1,
                attempts,
                type(exc).__name__,
                exc,
            )
            tokens = int(tokens * 1.6)
            if attempt + 1 >= attempts:
                break
            time.sleep(FACTS_RETRY_DELAY_SEC * (attempt + 1))
        except Exception as exc:
            last_error = exc
            logger.exception(
                "VIP %s facts unexpected error on attempt %s/%s",
                kind,
                attempt + 1,
                attempts,
            )
            tokens = int(tokens * 1.6)
            if attempt + 1 >= attempts:
                break
            time.sleep(FACTS_RETRY_DELAY_SEC * (attempt + 1))
    if isinstance(last_error, VipFactsExtractionError):
        raise last_error
    raise VipFactsExtractionError(
        "Не вдалося витягти факти з дзвінка (відповідь AI). Спробуйте ще раз."
    ) from last_error


def extract_vip_short_90s_facts(
    client,
    model,
    dialogue,
    qa_comment,
    important_note,
    max_output_tokens,
) -> dict:
    prompt = get_vip_short_90s_analysis_prompt(qa_comment, important_note)
    return _extract_facts_with_retry(
        "short",
        client,
        model,
        prompt,
        dialogue,
        max_output_tokens,
        VipShort90sFactsBundle,
    )


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
    return _extract_facts_with_retry(
        "friendly",
        client,
        model,
        prompt,
        dialogue,
        max_output_tokens,
        VipFriendlyFactsBundle,
    )


# --- legacy aliases used by older imports ---
def apply_vip_defaults(facts: dict) -> dict:
    """Normalize short-90s facts dict (replaces old red/green defaults)."""
    return VipShort90sFactsBundle.model_validate(facts or {}).model_dump()


def extract_vip_short_facts(client, model, dialogue, qa_comment, important_note, max_output_tokens):
    return extract_vip_short_90s_facts(
        client, model, dialogue, qa_comment, important_note, max_output_tokens
    )
