"""Friendly-схема контакту має ті самі ключі й визначення, що короткий дзвінок."""

from __future__ import annotations

from prompts_vip_friendly import get_vip_friendly_analysis_prompt
from prompts_vip_short import get_vip_short_90s_analysis_prompt

CONTACT_KEYS = (
    "greeted",
    "used_client_name",
    "named_project",
    "availability_check_relevant",
    "availability_check_done",
    "greeting_quote",
    "client_name_quote",
    "project_quote",
    "availability_quote",
    "manager_name_quote",
    "exception_number_signed",
    "exception_prior_messenger_contact",
    "exception_client_recognized_manager",
    "exception_client_interrupted_intro",
    "exception_answered_question_then_finished_intro",
    "evidence",
)

DEFINITIONS = (
    "greeted — будь-яке привітання",
    "used_client_name — звернувся на ім'я",
    "named_project — назвав 777, Betking або Vegas",
    "availability_check_relevant — завжди true",
    "availability_check_done — було питання",
    "exception_number_signed — у \"Важливому\"",
    "exception_prior_messenger_contact — у коментарі до дзвінка",
    "exception_client_recognized_manager — клієнт сам назвав менеджера",
    "exception_client_interrupted_intro — клієнт перебив представлення",
    "exception_answered_question_then_finished_intro — менеджер відповів на питання",
)


def test_friendly_contact_schema_matches_short_prompt():
    friendly = get_vip_friendly_analysis_prompt()
    short = get_vip_short_90s_analysis_prompt()
    assert "...як у короткому" not in friendly
    for key in CONTACT_KEYS:
        assert f'"{key}"' in friendly
        assert f'"{key}"' in short
    for line in DEFINITIONS:
        assert line in friendly
        assert line in short
    assert '"bonus_offer"' in friendly
    assert "betking_x2_booster_offered" in friendly
