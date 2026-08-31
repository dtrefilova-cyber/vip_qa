"""Промпт екстракції фактів для VIP Friendly (2-й дзвінок)."""

from __future__ import annotations


def get_vip_friendly_analysis_prompt(
    qa_comment: str = "",
    important_note: str = "",
    *,
    client_is_military: bool | None = None,
    betking_x2_applicable: bool | None = None,
) -> str:
    comment = (qa_comment or "").strip() or "—"
    note = (important_note or "").strip() or "—"
    military_hint = (
        "true"
        if client_is_military is True
        else ("false" if client_is_military is False else "невідомо — визнач з транскрипту")
    )
    betking_hint = (
        "true"
        if betking_x2_applicable is True
        else ("false" if betking_x2_applicable is False else "невідомо — визнач з контексту проєкту/транскрипту")
    )
    return f"""
Ти — асистент QA. Витягни атомарні ФАКТИ з транскрипту VIP Friendly (2-й дзвінок).
НЕ рахуй бали. НЕ став вердикт. Поверни ТІЛЬКИ валідний JSON.

КОНТЕКСТ:
- Коментар QA / попередній контакт: {comment}
- Важливе: {note}
- Клієнт військовий (картка): {military_hint}
- Betking X2 бустер застосовний (картка/проєкт): {betking_hint}

СХЕМА JSON:
{{
  "contact": {{ ...як у короткому: greeted, used_client_name, named_project, availability_*, exception_* }},
  "friendly_development": {{
    "asked_relevant_personal_questions": bool,
    "followed_up_on_client_answer": bool,
    "supported_client_initiated_topic": bool,
    "returned_to_personal_info_later": bool
  }},
  "personal_approach": {{
    "used_prior_interaction_info": bool,
    "reacted_to_shared_personal_info": bool,
    "adapted_communication_style": bool,
    "maintained_positive_contact_without_immediate_action": bool
  }},
  "call_to_action": {{
    "asked_deposit_today": bool,
    "started_with_bonus_before_deposit_intent": bool,
    "first_answer_positive": bool,
    "asked_deposit_tomorrow": bool,
    "second_answer_positive": bool,
    "client_is_military": bool,
    "asked_open_reason_if_declined": bool
  }},
  "bonus_offer": {{
    "deposit_bonus_offered_first": bool,
    "no_deposit_bonus_offered_after": bool,
    "no_deposit_bonus_applicable": bool,
    "all_terms_stated": bool,
    "benefits_explained": bool,
    "bonus_devalued": bool,
    "betking_x2_booster_offered": bool,
    "betking_x2_applicable": bool
  }},
  "prep": {{
    "objections_present": bool,
    "objections": [{{"type": "...", "handling": "ignored|formal|template_attempt|resolved_no_check|resolved_with_check"}}]
  }},
  "closing": {{
    "asked_if_more_questions": bool,
    "said_goodbye": bool,
    "thanked_and_left_contact_open": bool
  }},
  "ease": {{
    "level": "high|noticeable_gaps|low|critical",
    "signals": ["короткі ознаки з гайду, які обґрунтовують рівень"]
  }},
  "shared_context": {{
    "client_ended_call_first": bool,
    "client_said_no_time_and_hung_up": bool,
    "client_interrupted_manager": bool,
    "call_format_prevented_full_flow": bool,
    "client_didnt_allow_finish_thought": bool
  }}
}}

НЕВИМУШЕНІСТЬ (ease.level) — класифікуй РІВЕНЬ за чек-листом гайду (не став число балів; код мапить high→10, noticeable_gaps→5, low→2.5, critical→0):
- high — жива, природна розмова; немає системної скриптовості; менеджер гнучко реагує
- noticeable_gaps — помітні недоліки: часткова скриптованість, нерівний тон, окремі незручні місця
- low — низький рівень: розмова штучна/скриптова, слабка реакція на клієнта
- critical — критично негативна комунікація: тиск, холодність, ігнор клієнта, токсичний тон

Для P.R.E.P. handling — ті самі рівні, що для короткого дзвінка.
Якщо заперечень немає — objections_present=false, objections=[].
""".strip()
