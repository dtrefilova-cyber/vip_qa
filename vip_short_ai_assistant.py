"""AI-екстракція фактів для VIP Короткий 120 сек (30–120 с) і VIP Friendly."""

from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from core.vip_friendly_scoring import VipFriendlyFactsBundle
from core.vip_short_scoring import VipShort90sFactsBundle

logger = logging.getLogger(__name__)

VIP_SHORT_FACTS_CACHE_TAG = "vip_short90s_r5_20261028"
VIP_FRIENDLY_FACTS_CACHE_TAG = "vip_friendly_full1_20261103"
recent_usages: list[dict] = []
CTA_FACTS_MODEL = "gpt-5.4-mini"

_TRUE = {"true", "1", "yes", "y", "так", "да", "on"}
_FALSE = {"false", "0", "no", "n", "ні", "нет", "off", ""}
_EASE_LEVELS = {"high", "noticeable_gaps", "critical"}
_EASE_ALIASES = {
    "high": "high",
    "10": "high",
    "10.0": "high",
    "7.5": "high",
    "7,5": "high",
    "good": "high",
    "ok": "high",
    "noticeable_gaps": "noticeable_gaps",
    "noticeablegaps": "noticeable_gaps",
    "noticeable gaps": "noticeable_gaps",
    "medium": "noticeable_gaps",
    "5": "noticeable_gaps",
    "5.0": "noticeable_gaps",
    "low": "critical",
    "2.5": "critical",
    "2,5": "critical",
    "weak": "critical",
    "critical": "critical",
    "0": "critical",
    "0.0": "critical",
    "bad": "critical",
}
_OBJECTION_TYPES = {
    "no_desire",
    "no_time",
    "no_payout",
    "no_money",
    "bad_bonus_experience",
    "doubts_about_offer",
    "other",
}
_OBJECTION_HANDLING = {
    "ignored",
    "formal",
    "template_attempt",
    "resolved_no_check",
    "resolved_with_check",
}
_HANDLING_ALIASES = {
    "ignore": "ignored",
    "ignored": "ignored",
    "formal": "formal",
    "template": "template_attempt",
    "template_attempt": "template_attempt",
    "resolved": "resolved_no_check",
    "resolved_no_check": "resolved_no_check",
    "resolved_with_check": "resolved_with_check",
    "resolvedwithcheck": "resolved_with_check",
}


class VipFactsExtractionError(RuntimeError):
    """Помилка витягу фактів — безпечне повідомлення для UI."""


def active_vip_model(default: str | None = None) -> str:
    """Модель фактів VIP short з get_task_config (портал) або OPENAI_MODEL (прототип)."""
    try:
        from ai_models import get_task_config

        return str(get_task_config("facts_vip_short")["model"])
    except Exception:
        pass
    try:
        from utils import OPENAI_ANALYSIS_MODEL

        return str(OPENAI_ANALYSIS_MODEL or default or "")
    except Exception:
        return default or ""


def user_safe_analysis_error(exc: BaseException) -> str:
    """Коротке повідомлення для QA без сирих stack/secret деталей."""
    if isinstance(exc, VipFactsExtractionError):
        return str(exc)
    msg = str(exc or "").lower()
    name = type(exc).__name__.lower()
    if "streamlit" in name or "cannot be called" in msg or "cached" in msg:
        return (
            "Тимчасова помилка інтерфейсу під час аналізу. "
            "Оновіть сторінку і спробуйте ще раз."
        )
    if "timeout" in msg or "timed out" in msg:
        return "Аналіз перевищив час очікування. Спробуйте ще раз."
    if "openai" in msg or "rate limit" in msg or "429" in msg:
        return "Помилка AI-моделі. Спробуйте ще раз за хвилину."
    if "validation" in msg or "pydantic" in msg:
        return "Не вдалося розібрати результат аналізу. Спробуйте ще раз."
    return "Аналіз не завершився. Повідомте розробника."


def _extract_json_object(text: str) -> dict | None:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    blob = text[start : end + 1]
    stripped = re.sub(r",(\s*[}\]])", r"\1", blob)
    for candidate in (blob, stripped):
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return None


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        key = value.strip().lower()
        if key in _TRUE:
            return True
        if key in _FALSE:
            return False
    return default


def _as_dict(value) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _as_str_list(value) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _ease_level(value) -> str:
    if isinstance(value, (int, float)):
        if value >= 7.5:
            return "high"
        if value >= 5:
            return "noticeable_gaps"
        return "critical"
    key = str(value or "").strip().lower().replace("-", "_")
    compact = key.replace(" ", "_")
    if compact in _EASE_LEVELS:
        return compact
    return _EASE_ALIASES.get(key) or _EASE_ALIASES.get(compact) or "critical"


def _coerce_bool_tree(value):
    if isinstance(value, dict):
        return {str(key): _coerce_bool_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_coerce_bool_tree(item) for item in value]
    if isinstance(value, bool) or isinstance(value, (int, float)) or isinstance(value, str):
        if isinstance(value, str) and value.strip().lower() in _TRUE | _FALSE:
            return _as_bool(value)
        if isinstance(value, (int, float)) and value in (0, 1):
            return _as_bool(value)
    return value


def _coerce_objection(item) -> dict:
    data = _as_dict(item)
    raw_type = str(data.get("type") or "other").strip().lower().replace(" ", "_")
    if raw_type not in _OBJECTION_TYPES:
        raw_type = "other"
    raw_handling = str(data.get("handling") or "ignored").strip().lower().replace(" ", "_")
    raw_handling = _HANDLING_ALIASES.get(raw_handling, raw_handling)
    if raw_handling not in _OBJECTION_HANDLING:
        raw_handling = "ignored"
    return {
        "type": raw_type,
        "handling": raw_handling,
        "quote": str(data.get("quote") or "").strip(),
        "offer_quote": _as_text(data.get("offer_quote")),
        "right_before_client_hangup": _as_bool(data.get("right_before_client_hangup")),
    }


def _coerce_prep(value) -> dict:
    if isinstance(value, list):
        objections = [_coerce_objection(item) for item in value]
        return {"objections_present": bool(objections), "objections": objections}
    data = _as_dict(value)
    objections = data.get("objections") or []
    if not isinstance(objections, list):
        objections = []
    coerced = [_coerce_objection(item) for item in objections]
    present = data.get("objections_present")
    return {
        "objections_present": _as_bool(present, default=bool(coerced)),
        "objections": coerced,
    }


def _coerce_ease(value) -> dict:
    if isinstance(value, str) or isinstance(value, (int, float)):
        return {"level": _ease_level(value), "signals": []}
    data = _as_dict(value)
    return {
        "level": _ease_level(data.get("level")),
        "signals": _as_str_list(data.get("signals")),
    }


_CTA_TEXT_FIELDS = (
    "invite_quote",
    "client_declared_deposit_quote",
    "client_declared_deposit_time",
    "deposit_question_quote",
    "deposit_question_time",
    "first_answer",
    "first_answer_quote",
    "first_answer_time",
    "tomorrow_question_quote",
    "tomorrow_question_time",
    "second_answer",
    "second_answer_quote",
    "second_answer_time",
    "open_reason_quote",
    "open_reason_time",
    "first_bonus_offer_quote",
    "first_bonus_offer_time",
)
_CTA_ANSWERS = {"positive", "neutral", "negative", "unclear"}


def _as_text(value) -> str:
    if value is None or value is False:
        return ""
    return str(value).strip()


_QUOTE_FIELDS = {
    "contact": (
        "greeting_quote",
        "client_name_quote",
        "project_quote",
        "availability_quote",
        "manager_name_quote",
    ),
    "closing": (
        "asked_if_more_questions_quote",
        "said_goodbye_quote",
        "thanked_quote",
        "client_ended_quote",
        "connection_dropped_quote",
        "d14_quote",
    ),
}


def _stringify_quotes(data: dict) -> None:
    for section, fields in _QUOTE_FIELDS.items():
        block = data.get(section)
        if not isinstance(block, dict):
            continue
        for field in fields:
            block[field] = _as_text(block.get(field))


def coerce_vip_friendly_facts(raw: dict | None) -> dict:
    source = _as_dict(raw)
    data = _as_dict(_coerce_bool_tree(source))
    data["ease"] = _coerce_ease(
        data.get("ease") if isinstance(data.get("ease"), (dict, str, int, float)) else data.get("level")
    )
    data["prep"] = _coerce_prep(data.get("prep"))
    for key in (
        "contact",
        "friendly_development",
        "personal_approach",
        "call_to_action",
        "bonus_offer",
        "closing",
        "shared_context",
    ):
        data[key] = _as_dict(data.get(key))
    cta_source = _as_dict(source.get("call_to_action"))
    cta = _as_dict(data.get("call_to_action"))
    for field in _CTA_TEXT_FIELDS:
        if field in cta_source:
            cta[field] = _as_text(cta_source.get(field))
    for field in ("first_answer", "second_answer"):
        if cta.get(field) and cta.get(field) not in _CTA_ANSWERS:
            cta[field] = "unclear"
    data["call_to_action"] = cta
    _stringify_quotes(data)
    return data


_SHORT_TEXT_FIELDS = {
    "slip_handling": ("retention_opportunity_note",),
}
_SHORT_EVIDENCE_SECTIONS = (
    "contact",
    "slip_handling",
    "slip_critical",
    "closing",
    "shared_context",
)


def _preserve_short_text(raw: dict) -> dict:
    saved: dict[tuple[str, str], object] = {}
    for section, fields in _SHORT_TEXT_FIELDS.items():
        block = raw.get(section)
        if not isinstance(block, dict):
            continue
        for field in fields:
            saved[(section, field)] = str(block.get(field) or "")
    for section in _SHORT_EVIDENCE_SECTIONS:
        block = raw.get(section)
        if isinstance(block, dict):
            saved[(section, "evidence")] = _as_str_list(block.get("evidence"))
    prep = raw.get("prep")
    quotes = []
    if isinstance(prep, dict) and isinstance(prep.get("objections"), list):
        quotes = [str(_as_dict(item).get("quote") or "") for item in prep["objections"]]
    saved[("prep", "quotes")] = quotes
    return saved


def _restore_short_text(data: dict, saved: dict) -> None:
    for (section, field), value in saved.items():
        if section == "prep":
            continue
        block = data.get(section)
        if isinstance(block, dict):
            block[field] = value
    quotes = saved.get(("prep", "quotes")) or []
    prep = data.get("prep")
    if isinstance(prep, dict) and isinstance(prep.get("objections"), list):
        for item, quote in zip(prep["objections"], quotes):
            if isinstance(item, dict):
                item["quote"] = quote


def coerce_vip_short_facts(raw: dict | None) -> dict:
    source = _as_dict(raw)
    saved = _preserve_short_text(source)
    data = _as_dict(_coerce_bool_tree(source))
    data["prep"] = _coerce_prep(data.get("prep"))
    for key in (
        "contact",
        "slip_handling",
        "slip_critical",
        "closing",
        "shared_context",
    ):
        data[key] = _as_dict(data.get(key))
    _restore_short_text(data, saved)
    _stringify_quotes(data)
    return data


def _validate_bundle(model, raw: dict, *, label: str):
    coerced = coerce_vip_friendly_facts(raw) if label == "friendly" else coerce_vip_short_facts(raw)
    try:
        return model.model_validate(coerced).model_dump()
    except ValidationError:
        logger.exception("VIP %s facts validation failed; dropping invalid sections", label)
        recovered = {}
        for field_name in model.model_fields:
            try:
                recovered[field_name] = model.model_validate(
                    {field_name: coerced.get(field_name)}
                ).model_dump()[field_name]
            except ValidationError:
                logger.warning("VIP %s dropped invalid section %s", label, field_name)
        return model.model_validate(recovered).model_dump()


def _root_ai():
    """Портальний ai_client, якщо доступний; інакше None (прототип Streamlit)."""
    try:
        import sys
        from pathlib import Path

        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.append(root)
        import ai_client

        return ai_client
    except Exception:
        return None


def _openai_chat_json(client, model: str, system: str, user: str, max_output_tokens: int) -> str:
    """Прямий виклик OpenAI chat.completions для прототипу Streamlit."""
    res = client.chat.completions.create(
        model=model,
        temperature=0,
        seed=42,
        max_completion_tokens=max_output_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (res.choices[0].message.content or "") if res.choices else ""


def _call_gpt_json(
    client,
    model,
    system: str,
    user: str,
    task: str,
    max_output_tokens: int,
    *,
    model_override: str | None = None,
    effort_override: str | None = None,
) -> dict:
    payload, _usage = _call_gpt_json_usage(
        client,
        model,
        system,
        user,
        task,
        max_output_tokens,
        model_override=model_override,
        effort_override=effort_override,
    )
    return payload


def _call_gpt_json_usage(
    client,
    model,
    system: str,
    user: str,
    task: str,
    max_output_tokens: int,
    *,
    model_override: str | None = None,
    effort_override: str | None = None,
) -> tuple[dict, dict]:
    """Виклик GPT. Без st.* — викликається з @st.cache_data.

    Портал: ai_client.call_model(task, ...).
    Прототип: OpenAI client + реєстр задач ai_models.get_task_config.
    """
    try:
        from app_fastapi import ai_config
    except ImportError:
        ai_config = None
    ai_client = _root_ai()
    try:
        from ai_models import get_task_config

        task_cfg = get_task_config(task)
    except Exception:
        task_cfg = {"model": model, "task": task}
    resolved_model = str(model_override or task_cfg.get("model") or model or "").strip()
    last_error = None
    for attempt in range(2):
        if attempt > 0:
            logger.warning(
                "VIP facts retry %s: invalid JSON from model (%s)", attempt, last_error
            )
        try:
            if ai_client is not None:
                result = ai_client.call_model(
                    task,
                    system,
                    user,
                    max_out=max_output_tokens,
                    model_override=model_override,
                    effort_override=effort_override,
                )
                if ai_config is not None:
                    ai_config.log_usage("vip", result.get("model_used") or resolved_model, result)
                content = result["text"]
                usage = dict(result.get("usage") or {})
                usage["model_used"] = result.get("model_used") or resolved_model
            else:
                content = _openai_chat_json(
                    client, resolved_model, system, user, max_output_tokens
                )
                usage = {"model_used": resolved_model, "task": task}
            payload = _extract_json_object(content)
            usage["task"] = task
            recent_usages.append(usage)
            if payload is not None:
                # allow either root facts or nested {"facts": {...}}
                if isinstance(payload.get("facts"), dict):
                    return dict(payload["facts"]), usage
                return dict(payload), usage
            last_error = "empty or invalid JSON"
        except Exception as exc:
            if ai_client is not None and type(exc).__name__ == "OutputLengthError":
                raise
            last_error = str(exc)
            logger.exception("VIP facts GPT call failed task=%s", task)
    raise VipFactsExtractionError(
        "Не вдалося витягти факти з дзвінка (відповідь AI). Спробуйте ще раз."
    )


def _dialogue_context(dialogue: str) -> tuple[str, float | None]:
    last_speaker = ""
    duration = None
    for raw in (dialogue or "").splitlines():
        match = re.match(
            r"^(Менеджер|Клієнт|Клиент|ch_\d+)\s*:\s*(?:\[(\d+):(\d+)\]\s*)?(.*)$",
            raw.strip(),
        )
        if not match:
            continue
        last_speaker = match.group(1)
        if match.group(2) is not None:
            duration = int(match.group(2)) * 60 + int(match.group(3))
    return last_speaker, duration


_SLIP_BOOLS = (
    "client_attempted_to_end_call",
    "reason_stated_by_client",
    "reason_clarified_by_manager",
    "manager_reacted_appropriately",
    "proposed_callback",
    "specified_concrete_time",
    "confirmed_agreement_or_clear_refusal",
    "client_flatly_refused_any_callback",
    "retention_opportunity_missed",
)


def fact_vote_count() -> int:
    """Скільки витягів усереднювати. 1 — як раніше. 3 вмикає більшість для зливу і P.R.E.P."""
    import os

    try:
        count = int(os.environ.get("VIP_SHORT_FACT_VOTES", "1") or "1")
    except ValueError:
        count = 1
    return max(1, count)


def _majority_bool(values: list[bool]) -> bool:
    return sum(1 for value in values if value) * 2 > len(values)


def _prep_points(prep: dict) -> float:
    from core.vip_scoring_common import PrepFacts, score_prep

    try:
        return float(score_prep(PrepFacts.model_validate(prep or {})).points)
    except Exception:
        return -1.0


def _vote_slip_and_prep(samples: list[dict]) -> dict:
    """Більшість по bool зливу. Заперечення — варіант, чий бал P.R.E.P. є медіаною."""
    base = dict(samples[0])
    slips = [dict(sample.get("slip_handling") or {}) for sample in samples]
    merged = dict(slips[0])
    for key in _SLIP_BOOLS:
        merged[key] = _majority_bool([bool(item.get(key)) for item in slips])
    donors = [item for item in slips if bool(item.get("retention_opportunity_missed")) == merged["retention_opportunity_missed"]]
    donor = max(donors or slips, key=lambda item: len(item.get("evidence") or []))
    merged["retention_opportunity_note"] = donor.get("retention_opportunity_note") or ""
    merged["evidence"] = list(donor.get("evidence") or [])
    base["slip_handling"] = merged
    ranked = sorted(
        (dict(sample.get("prep") or {}) for sample in samples),
        key=_prep_points,
    )
    base["prep"] = ranked[len(ranked) // 2]
    return base


def _merge_contact(facts: dict, block: dict) -> dict:
    merged = dict(facts or {})
    contact = dict(merged.get("contact") or {})
    contact.update(dict(block or {}))
    merged["contact"] = contact
    return merged


def extract_contact_result(
    client,
    model,
    dialogue: str,
    *,
    task: str,
    model_override: str | None = None,
) -> dict:
    from prompts_vip_short import get_vip_contact_prompt

    raw, _usage = _call_gpt_json_usage(
        client,
        model,
        get_vip_contact_prompt(),
        "СИРИЙ ТРАНСКРИПТ:\n" + dialogue,
        task,
        800,
        model_override=model_override,
    )
    block = raw.get("contact") if isinstance(raw.get("contact"), dict) else raw
    return dict(block or {})


def extract_vip_short_90s_facts(
    client,
    model,
    dialogue,
    qa_comment,
    important_note,
    max_output_tokens,
    *,
    manager_name: str = "",
    project: str = "",
    number_signed: bool = False,
    client_is_military: bool = False,
    dialogue_for_context: str = "",
) -> dict:
    from prompts_vip_short import (
        VIP_SHORT_90S_PROMPT_TEMPLATE,
        build_vip_short_context,
        get_vip_short_static_prompt,
    )

    try:
        from app_fastapi import ai_config
    except ImportError:
        ai_config = None

    last_speaker, duration = _dialogue_context(dialogue_for_context or dialogue)
    system = get_vip_short_static_prompt()
    user = (
        build_vip_short_context(
            qa_comment,
            important_note,
            manager_name=manager_name,
            project=project,
            number_signed=number_signed,
            client_is_military=client_is_military,
            last_speaker=last_speaker,
            duration_sec=duration,
        )
        + "\n\nСИРИЙ ТРАНСКРИПТ:\n"
        + dialogue
    )
    if ai_config is not None:
        template = ai_config.active_prompt("vip", "short_90s_facts", VIP_SHORT_90S_PROMPT_TEMPLATE)
        if template != VIP_SHORT_90S_PROMPT_TEMPLATE:
            system = ai_config.render_prompt(
                template,
                {
                    "comment": (qa_comment or "").strip() or "—",
                    "note": (important_note or "").strip() or "—",
                },
            )
            user = f"СИРИЙ ТРАНСКРИПТ:\n{dialogue}"
    samples = []
    for _ in range(fact_vote_count()):
        raw = _call_gpt_json(client, model, system, user, "facts_vip_short", max_output_tokens)
        samples.append(_validate_bundle(VipShort90sFactsBundle, raw or {}, label="short"))
    facts = samples[0] if len(samples) == 1 else _vote_slip_and_prep(samples)
    try:
        block = extract_contact_result(
            client,
            model,
            dialogue,
            task="facts_vip_short_contact",
        )
        facts = _merge_contact(facts, block)
    except VipFactsExtractionError:
        logger.exception("VIP short contact call failed; keeping the main contact")
    return facts


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
    from prompts_vip_friendly import (
        VIP_FRIENDLY_PROMPT_TEMPLATE,
        build_vip_friendly_context,
        get_vip_friendly_static_prompt,
    )

    try:
        from app_fastapi import ai_config
    except ImportError:
        ai_config = None

    system = get_vip_friendly_static_prompt()
    user = (
        build_vip_friendly_context(
            qa_comment,
            important_note,
            client_is_military=client_is_military,
            betking_x2_applicable=betking_x2_applicable,
        )
        + "\n\nСИРИЙ ТРАНСКРИПТ:\n"
        + dialogue
    )
    if ai_config is not None:
        template = ai_config.active_prompt("vip", "friendly_facts", VIP_FRIENDLY_PROMPT_TEMPLATE)
        if template != VIP_FRIENDLY_PROMPT_TEMPLATE:
            system = ai_config.render_prompt(
                template,
                {
                    "comment": (qa_comment or "").strip() or "—",
                    "note": (important_note or "").strip() or "—",
                    "military_hint": "невідомо — визнач з транскрипту",
                    "betking_hint": "невідомо — визнач з контексту проєкту/транскрипту",
                },
            )
            user = f"СИРИЙ ТРАНСКРИПТ:\n{dialogue}"
    raw = _call_gpt_json(client, model, system, user, "facts_vip_friendly", max_output_tokens)
    facts = _validate_bundle(VipFriendlyFactsBundle, raw or {}, label="friendly")
    try:
        cta, _usage = extract_vip_friendly_cta_result(
            client,
            model,
            dialogue,
            qa_comment,
            important_note,
            client_is_military=client_is_military,
            betking_x2_applicable=betking_x2_applicable,
            model_override=CTA_FACTS_MODEL,
        )
    except VipFactsExtractionError:
        logger.exception("VIP friendly CTA call failed; keeping the main call_to_action")
        cta = dict(facts.get("call_to_action") or {})
        for field in _CTA_TEXT_FIELDS:
            cta.pop(field, None)
    facts = merge_friendly_cta(facts, cta)
    try:
        bonus, _usage = extract_vip_friendly_bonus_result(
            client,
            model,
            dialogue,
            qa_comment,
            important_note,
            client_is_military=client_is_military,
            betking_x2_applicable=betking_x2_applicable,
            model_override=CTA_FACTS_MODEL,
        )
    except VipFactsExtractionError:
        logger.exception("VIP friendly bonus call failed; keeping the main bonus_offer")
        bonus = dict(facts.get("bonus_offer") or {})
        for field in (
            "first_deposit_bonus_quote",
            "first_deposit_bonus_time",
            "first_no_deposit_bonus_quote",
            "first_no_deposit_bonus_time",
            "terms_stated",
            "benefits_quote",
            "devalue_quote",
            "x2_quote",
        ):
            bonus.pop(field, None)
    facts = merge_friendly_bonus(facts, bonus)
    try:
        rapport = extract_vip_friendly_rapport_result(
            client,
            model,
            dialogue,
            qa_comment,
            important_note,
            client_is_military=client_is_military,
            betking_x2_applicable=betking_x2_applicable,
            model_override=CTA_FACTS_MODEL,
        )
        facts = merge_friendly_rapport(facts, rapport)
    except VipFactsExtractionError:
        logger.exception("VIP friendly rapport call failed; keeping the main blocks")
    try:
        closing = extract_vip_friendly_closing_result(
            client,
            model,
            dialogue,
            qa_comment,
            important_note,
            client_is_military=client_is_military,
            betking_x2_applicable=betking_x2_applicable,
            model_override=CTA_FACTS_MODEL,
        )
        facts = merge_friendly_closing(facts, closing)
    except VipFactsExtractionError:
        logger.exception("VIP friendly closing call failed; keeping the main closing")
    try:
        block = extract_contact_result(
            client,
            model,
            dialogue,
            task="facts_vip_friendly_contact",
            model_override=CTA_FACTS_MODEL,
        )
        facts = _merge_contact(facts, block)
    except VipFactsExtractionError:
        logger.exception("VIP friendly contact call failed; keeping the main contact")
    return facts


def merge_friendly_cta(facts: dict, cta: dict) -> dict:
    """Підставляє лише блок заклику. Військовий прапор лишається з основних фактів."""
    merged = dict(facts or {})
    previous = dict(merged.get("call_to_action") or {})
    block = dict(cta or {})
    block["client_is_military"] = bool(previous.get("client_is_military"))
    merged["call_to_action"] = block
    return merged


def extract_vip_friendly_cta_result(
    client,
    model,
    dialogue,
    qa_comment,
    important_note,
    *,
    client_is_military: bool | None = None,
    betking_x2_applicable: bool | None = None,
    model_override: str | None = None,
    effort_override: str | None = None,
) -> tuple[dict, dict]:
    from core.vip_friendly_scoring import CallToActionFacts, ground_call_to_action
    from prompts_vip_friendly import build_vip_friendly_context, get_vip_friendly_cta_prompt

    system = get_vip_friendly_cta_prompt()
    user = (
        build_vip_friendly_context(
            qa_comment,
            important_note,
            client_is_military=client_is_military,
            betking_x2_applicable=betking_x2_applicable,
        )
        + "\n\nСИРИЙ ТРАНСКРИПТ:\n"
        + dialogue
    )
    raw, usage = _call_gpt_json_usage(
        client,
        model,
        system,
        user,
        "facts_vip_friendly_cta",
        1200,
        model_override=model_override,
        effort_override=effort_override,
    )
    block = raw.get("call_to_action") if isinstance(raw.get("call_to_action"), dict) else raw
    block = dict(block or {})
    questions = []
    for item in block.get("manager_play_questions") or []:
        if not isinstance(item, dict):
            continue
        questions.append({
            "quote": _as_text(item.get("quote")),
            "time": _as_text(item.get("time")),
            "answer": _as_text(item.get("answer")).lower(),
            "answer_quote": _as_text(item.get("answer_quote")),
        })
    block["manager_play_questions"] = questions
    coerced = coerce_vip_friendly_facts({"call_to_action": block}).get("call_to_action") or {}
    coerced["manager_play_questions"] = questions
    try:
        dumped = CallToActionFacts.model_validate(coerced).model_dump()
    except ValidationError:
        logger.exception("VIP friendly CTA section invalid")
        dumped = CallToActionFacts().model_dump()
    return ground_call_to_action(dumped, dialogue), usage


def merge_friendly_bonus(facts: dict, bonus: dict) -> dict:
    """Підставляє лише блок бонусів. Застосовність X2 лишається з основних фактів."""
    merged = dict(facts or {})
    previous = dict(merged.get("bonus_offer") or {})
    block = dict(bonus or {})
    if "betking_x2_applicable" in previous:
        block["betking_x2_applicable"] = bool(previous.get("betking_x2_applicable"))
    merged["bonus_offer"] = block
    return merged


def extract_vip_friendly_bonus_result(
    client,
    model,
    dialogue,
    qa_comment,
    important_note,
    *,
    client_is_military: bool | None = None,
    betking_x2_applicable: bool | None = None,
    model_override: str | None = None,
    effort_override: str | None = None,
) -> tuple[dict, dict]:
    from core.vip_friendly_scoring import BonusOfferFacts, _term_value, ground_bonus_offer
    from prompts_vip_friendly import build_vip_friendly_context, get_vip_friendly_bonus_prompt

    system = get_vip_friendly_bonus_prompt()
    user = (
        build_vip_friendly_context(
            qa_comment,
            important_note,
            client_is_military=client_is_military,
            betking_x2_applicable=betking_x2_applicable,
        )
        + "\n\nСИРИЙ ТРАНСКРИПТ:\n"
        + dialogue
    )
    raw, usage = _call_gpt_json_usage(
        client,
        model,
        system,
        user,
        "facts_vip_friendly_bonus",
        1200,
        model_override=model_override,
        effort_override=effort_override,
    )
    block = raw.get("bonus_offer") if isinstance(raw.get("bonus_offer"), dict) else raw
    block = dict(block or {})
    for field in (
        "first_deposit_bonus_quote",
        "first_deposit_bonus_time",
        "first_no_deposit_bonus_quote",
        "first_no_deposit_bonus_time",
        "benefits_quote",
        "devalue_quote",
        "x2_quote",
    ):
        if field in block:
            block[field] = _as_text(block.get(field))
    terms = block.get("terms_stated") if isinstance(block.get("terms_stated"), dict) else {}
    block["terms_stated"] = {
        key: _term_value(terms.get(key))
        for key in ("min_deposit", "validity", "wager", "fs_count_and_bet")
    }
    try:
        dumped = BonusOfferFacts.model_validate(block).model_dump()
    except ValidationError:
        logger.exception("VIP friendly bonus section invalid")
        dumped = BonusOfferFacts().model_dump()
    return ground_bonus_offer(dumped, dialogue), usage


def _section_user(qa_comment, important_note, dialogue, client_is_military, betking_x2_applicable) -> str:
    from prompts_vip_friendly import build_vip_friendly_context

    return (
        build_vip_friendly_context(
            qa_comment,
            important_note,
            client_is_military=client_is_military,
            betking_x2_applicable=betking_x2_applicable,
        )
        + "\n\nСИРИЙ ТРАНСКРИПТ:\n"
        + dialogue
    )


def merge_friendly_rapport(facts: dict, rapport: dict) -> dict:
    merged = dict(facts or {})
    friendly = dict(rapport.get("friendly_development") or {})
    approach = dict(rapport.get("personal_approach") or {})
    if friendly:
        merged["friendly_development"] = friendly
    if approach:
        merged["personal_approach"] = approach
    return merged


def extract_vip_friendly_rapport_result(
    client,
    model,
    dialogue,
    qa_comment,
    important_note,
    *,
    client_is_military: bool | None = None,
    betking_x2_applicable: bool | None = None,
    model_override: str | None = None,
    effort_override: str | None = None,
) -> dict:
    from core.vip_friendly_scoring import FriendlyDevelopmentFacts, PersonalApproachFacts
    from prompts_vip_friendly import get_vip_friendly_rapport_prompt

    raw, _usage = _call_gpt_json_usage(
        client,
        model,
        get_vip_friendly_rapport_prompt(),
        _section_user(qa_comment, important_note, dialogue, client_is_military, betking_x2_applicable),
        "facts_vip_friendly_rapport",
        1200,
        model_override=model_override,
        effort_override=effort_override,
    )
    friendly = {
        "guide_level": _as_text(raw.get("friendly_level")),
        "signal_quotes": _as_str_list(raw.get("friendly_signals")),
        "mechanical_only": _as_bool(raw.get("mechanical_only")),
    }
    approach = {
        "guide_level": _as_text(raw.get("approach_level")),
        "signal_quotes": _as_str_list(raw.get("approach_signals")),
        "bonuses_only": _as_bool(raw.get("bonuses_only")),
    }
    return {
        "friendly_development": FriendlyDevelopmentFacts.model_validate(friendly).model_dump(),
        "personal_approach": PersonalApproachFacts.model_validate(approach).model_dump(),
    }


def merge_friendly_closing(facts: dict, closing: dict) -> dict:
    merged = dict(facts or {})
    merged["closing"] = dict(closing or {})
    return merged


def extract_vip_friendly_closing_result(
    client,
    model,
    dialogue,
    qa_comment,
    important_note,
    *,
    client_is_military: bool | None = None,
    betking_x2_applicable: bool | None = None,
    model_override: str | None = None,
    effort_override: str | None = None,
) -> dict:
    from core.vip_scoring_common import ClosingFacts
    from prompts_vip_friendly import get_vip_friendly_closing_prompt

    raw, _usage = _call_gpt_json_usage(
        client,
        model,
        get_vip_friendly_closing_prompt(),
        _section_user(qa_comment, important_note, dialogue, client_is_military, betking_x2_applicable),
        "facts_vip_friendly_closing",
        800,
        model_override=model_override,
        effort_override=effort_override,
    )
    block = {
        "asked_if_more_questions_quote": _as_text(raw.get("asked_if_more_questions_quote")),
        "said_goodbye_quote": _as_text(raw.get("said_goodbye_quote")),
        "thanked_quote": _as_text(raw.get("thanked_quote")),
        "client_ended_quote": _as_text(raw.get("client_ended_quote")),
        "connection_dropped_quote": _as_text(raw.get("connection_dropped_quote")),
        "quote_mode": True,
    }
    return ClosingFacts.model_validate(block).model_dump()


# --- legacy aliases used by older imports ---
def apply_vip_defaults(facts: dict) -> dict:
    """Normalize short-90s facts dict (replaces old red/green defaults)."""
    return _validate_bundle(VipShort90sFactsBundle, facts or {}, label="short")


def extract_vip_short_facts(client, model, dialogue, qa_comment, important_note, max_output_tokens):
    return extract_vip_short_90s_facts(
        client, model, dialogue, qa_comment, important_note, max_output_tokens
    )
