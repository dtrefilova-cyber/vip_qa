"""Реєстр AI-задач VIP для Streamlit-прототипу (сумісність із портальним get_task_config)."""

from __future__ import annotations

import os

# Окремі виклики фактів (ТЗ п. 4.3–4.4) — усі на тій самій моделі аналізу.
VIP_FACT_TASKS = (
    "facts_vip_short",
    "facts_vip_short_contact",
    "facts_vip_friendly",
    "facts_vip_friendly_cta",
    "facts_vip_friendly_bonus",
    "facts_vip_friendly_rapport",
    "facts_vip_friendly_closing",
    "facts_vip_friendly_contact",
)


def _default_model() -> str:
    try:
        from utils import OPENAI_ANALYSIS_MODEL

        if OPENAI_ANALYSIS_MODEL:
            return str(OPENAI_ANALYSIS_MODEL)
    except Exception:
        pass
    return str(os.environ.get("OPENAI_MODEL") or "gpt-5.4-mini")


def get_task_config(task: str) -> dict:
    """Повертає конфіг задачі: model (+ метадані). Невідома задача → default model."""
    name = str(task or "").strip()
    return {
        "task": name or "facts_vip_short",
        "model": _default_model(),
        "registered": name in VIP_FACT_TASKS,
    }
