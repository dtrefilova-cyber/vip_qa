"""Промпт екстракції фактів для VIP «Короткий 90 сек»."""

from __future__ import annotations


def get_vip_short_90s_analysis_prompt(qa_comment: str = "", important_note: str = "") -> str:
    comment = (qa_comment or "").strip() or "—"
    note = (important_note or "").strip() or "—"
    return f"""
Ти — асистент QA. Твоя єдина задача — витягти атомарні ФАКТИ з транскрипту VIP-короткого дзвінка (до ~90–100 сек).
НЕ рахуй бали. НЕ став вердикт RED/GREEN. Поверни ТІЛЬКИ валідний JSON за схемою нижче.

КОНТЕКСТ ВІД QA:
- Коментар по дзвінку: {comment}
- Важливе / попередній контакт: {note}

СХЕМА JSON (усі поля обов'язкові; якщо не впевнений — false / порожній список):
{{
  "contact": {{
    "greeted": bool,
    "used_client_name": bool,
    "named_project": bool,
    "availability_check_relevant": bool,
    "availability_check_done": bool,
    "exception_prior_messenger_contact": bool,
    "exception_client_recognized_manager": bool,
    "exception_client_interrupted_intro": bool,
    "exception_answered_question_then_finished_intro": bool
  }},
  "slip_handling": {{
    "client_attempted_to_end_call": bool,
    "reason_stated_by_client": bool,
    "reason_clarified_by_manager": bool,
    "manager_reacted_appropriately": bool,
    "proposed_callback": bool,
    "specified_concrete_time": bool,
    "confirmed_agreement_or_clear_refusal": bool,
    "client_flatly_refused_any_callback": bool
  }},
  "slip_critical": {{
    "continued_pitch_after_client_said_cannot_talk": bool,
    "continued_pitch_instead_of_agreeing_callback": bool,
    "asked_irrelevant_questions": bool,
    "artificially_extended_call": bool,
    "delayed_ending_after_callback_agreed": bool,
    "ended_without_using_available_retention_options": bool
  }},
  "prep": {{
    "objections_present": bool,
    "objections": [
      {{
        "type": "no_desire|no_time|no_payout|bad_bonus_experience|doubts_about_offer|other",
        "handling": "ignored|formal|template_attempt|resolved_no_check|resolved_with_check"
      }}
    ]
  }},
  "closing": {{
    "asked_if_more_questions": bool,
    "said_goodbye": bool,
    "thanked_and_left_contact_open": bool
  }},
  "shared_context": {{
    "client_ended_call_first": bool,
    "client_said_no_time_and_hung_up": bool,
    "client_interrupted_manager": bool,
    "call_format_prevented_full_flow": bool,
    "client_didnt_allow_finish_thought": bool
  }}
}}

ПРАВИЛА ДЛЯ P.R.E.P. (handling) — обери ОДИН рівень на кожне заперечення:
- ignored — заперечення проігноровано
- formal — формальна реакція / зміна теми без опрацювання
- template_attempt — шаблонна відповідь, але спроба була
- resolved_no_check — опрацьовано, без уточнювального питання на перевірку реакції
- resolved_with_check — опрацьовано + уточнювальне питання

Якщо заперечень не було — objections_present=false і objections=[].
""".strip()


# backward-compatible alias
def get_vip_short_analysis_prompt(qa_comment: str = "", important_note: str = "") -> str:
    return get_vip_short_90s_analysis_prompt(qa_comment, important_note)
