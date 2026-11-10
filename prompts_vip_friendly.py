"""Промпт екстракції фактів для VIP Friendly (2-й дзвінок)."""

from __future__ import annotations


def build_vip_friendly_context(
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
    return f"""КОНТЕКСТ:
- Коментар QA / попередній контакт: {comment}
- Важливе: {note}
- Клієнт військовий (картка): {military_hint}
- Betking X2 бустер застосовний (картка/проєкт): {betking_hint}"""


def get_vip_friendly_static_prompt() -> str:
    return get_vip_friendly_analysis_prompt().replace(build_vip_friendly_context(), "").strip()


def get_vip_friendly_analysis_prompt(
    qa_comment: str = "",
    important_note: str = "",
    *,
    client_is_military: bool | None = None,
    betking_x2_applicable: bool | None = None,
) -> str:
    context = build_vip_friendly_context(
        qa_comment,
        important_note,
        client_is_military=client_is_military,
        betking_x2_applicable=betking_x2_applicable,
    )
    return f"""
Ти — асистент QA. Витягни атомарні ФАКТИ з транскрипту VIP Friendly (2-й дзвінок).
НЕ рахуй бали. НЕ став вердикт. Поверни ТІЛЬКИ валідний JSON.

{context}

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
    "asked_open_reason_if_declined": bool,
    "invited_to_play_when_possible": bool
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
    "level": "high|noticeable_gaps|critical",
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

ВІЙСЬКОВИЙ (клієнт ЗСУ, картка або коментар):
- P.R.E.P.: "немає коштів" і "немає часу" не опрацьовуються. Не включай їх в objections. Інших заперечень немає — objections_present=false.
- Заклик до гри м'якший: достатньо запросити пограти і забрати бонус по можливості ("пограйте, коли буде змога", "заберіть бонус по можливості"). Тоді invited_to_play_when_possible=true і client_is_military=true. Питання "чому не сьогодні" не вимагається. Такий заклик не є помилкою "почав з бонусу".

КОНТАКТ: якщо в коментарі або "Важливому" є месенджер (Viber, Telegram, WhatsApp), коротке представлення лише на ім'я — це повний контакт. exception_prior_messenger_contact=true, назва проєкту не обов'язкова.

ЗАВЕРШЕННЯ: "чи не залишилось питань" / "чи залишились питання" = asked_if_more_questions. "До зв'язку" = said_goodbye.

НЕВИМУШЕНІСТЬ (ease.level) — лише три рівні. Не став число балів і не використовуй 10 чи 2.5. Код мапить high→7.5, noticeable_gaps→5, critical→0.
Оцінюй природність, реакцію на стан клієнта, якість взаємодії і загальне враження. Розмова має бути діалогом, а не монологом; живою; з урахуванням відповідей клієнта; зрозумілою; персоналізованою під ситуацію.
- high — 7,5. Живий діалог: реагує на відповіді й емоції, ставить доречні питання, адаптує подачу, пояснює зрозуміло, показує зацікавленість. Незначні недоліки, які не псують розмову, лишають цей рівень.
- noticeable_gaps — 5. Помітні недоліки, розмова ще не розвалена: частковий монолог, слабке залучення, відповіді клієнта не використані, слабка реакція на емоції чи коментарі, скриптована або формальна подача, невдалий темп, перебивання, довгі паузи (2 і більше), складні пояснення, невпевненість, немає реакції на особисту ситуацію.
- critical — 0. Розмова переважно монолог, майже немає реакції на відповіді, ігнор емоцій або потреб, системна скриптованість, холодна подача, немає персоналізації, немає підтримки у важливій ситуації. Також весь дзвінок механічний, діалогу немає, тон токсичний, грубий або тиснучий, сильний дискомфорт.
Додатково: якщо клієнт вперше сказав про службу у війську — у high має бути подяка. Якщо сказав про складні обставини або поганий стан — у high має бути доречна підтримка. Звичайна ділова ввічлива подача, коли менеджер відповідає на запити, не є помилкою. Лише факти з транскрипту: не вигадуй тон чи емоції, якщо їх не видно з тексту.

Для P.R.E.P. handling — ті самі рівні, що для короткого дзвінка.
Якщо заперечень немає — objections_present=false, objections=[].
""".strip()


def get_vip_friendly_cta_prompt() -> str:
    """Окремий короткий виклик лише для заклику. Решту фактів він не витягує."""
    return """
Ти витягуєш лише факти заклику до гри з транскрипту VIP Friendly.
НЕ рахуй бали. Прапорці asked_deposit_today, started_with_bonus_before_deposit_intent, first_answer_positive, asked_deposit_tomorrow, second_answer_positive, asked_open_reason_if_declined не став — їх виставляє код за цитатами.
Поверни ТІЛЬКИ валідний JSON. Цитата — дослівний фрагмент репліки або порожній рядок. Таймкод — як у рядку, формат M:SS, або порожній рядок. Не вигадуй фраз, яких немає в транскрипті.

{
  "manager_play_questions": [
    {"quote": "", "time": "", "answer": "positive|neutral|negative|unclear", "answer_quote": ""}
  ],
  "first_bonus_offer_quote": "",
  "first_bonus_offer_time": "",
  "client_is_military": false,
  "invited_to_play_when_possible": false,
  "invite_quote": "",
  "client_declared_deposit_today": false,
  "client_declared_deposit_quote": "",
  "client_declared_deposit_time": ""
}

ЗАКЛИК ДО ГРИ (гайд).
Менеджер обов'язково уточнює, чи буде клієнт грати саме сьогодні НА ДЕПОЗИТ. Якщо перша відповідь негативна або нейтральна — уточнює, чи буде грати на депозит завтра. Якщо і друга відповідь негативна — відкрите питання про причину відмови.
Правильні питання, дослівно: «Будете сьогодні робити поповнення?», «Граєте сьогодні на депозит?», «Будете сьогодні вносити депозит?», «Будете сьогодні поповнювати рахунок?», «ви сьогодні на поповнення грати будете?».
manager_play_questions — УСІ питання менеджера про гру або поповнення сьогодні чи завтра, кожне з відповіддю клієнта. «Заходити» без «деп», «депозит», «поповн» або «рахунок» теж включи в список: код сам відсіє його. «Заходити» разом із цими словами — це питання про депозит, не викидай його.
answer: positive — згода грати на депозит; neutral — ні згоди, ні відмови; negative — відмова; unclear — з репліки не видно. answer_quote — репліка клієнта.
Питання про завтра — лише після негативної або нейтральної відповіді про сьогодні.
first_bonus_offer_quote — перша конкретна пропозиція бонусу на сьогодні: сума, тип або умови. Згадка минулого бонусу, «гляну по бонусах», «щось залишу» — не пропозиція, лишай поле порожнім.

Д2. Клієнт військовий: достатньо м'якого запрошення пограти, забрати бонус або сказати, що менеджер чекає, по можливості («пограйте, коли буде змога», «заберіть бонус по можливості», «я вас по можливості чекаю»). Тоді client_is_military=true, invited_to_play_when_possible=true, invite_quote — цитата менеджера. Питання «чому не сьогодні» не вимагається.
Д3. Якщо клієнт сам сказав, що гратиме сьогодні на депозит, до питання менеджера — client_declared_deposit_today=true і цитата клієнта.
Д9. Бали не став. Відсутність однієї обов'язкової дії кодує код як 5.
""".strip()


def get_vip_friendly_bonus_prompt() -> str:
    """Окремий короткий виклик лише для пропозиції бонусів."""
    return """
Ти витягуєш лише факти пропозиції бонусів з транскрипту VIP Friendly.
НЕ рахуй бали. Прапорці deposit_bonus_offered_first, no_deposit_bonus_offered_after, all_terms_stated, benefits_explained, bonus_devalued, betking_x2_booster_offered не став — їх виставляє код за цитатами і таймкодами.
Поверни ТІЛЬКИ валідний JSON. Цитата — дослівний фрагмент репліки менеджера або порожній рядок. Умова, якої в цьому бонусі немає, — рядок "n/a". Умова, яку менеджер мав сказати і не сказав, — null. Таймкод — M:SS або порожній рядок.

{
  "first_deposit_bonus_quote": "",
  "first_deposit_bonus_time": "",
  "first_no_deposit_bonus_quote": "",
  "first_no_deposit_bonus_time": "",
  "terms_stated": {
    "min_deposit": null,
    "validity": null,
    "wager": null,
    "fs_count_and_bet": null
  },
  "benefits_quote": "",
  "devalue_quote": "",
  "x2_quote": "",
  "no_deposit_bonus_applicable": false
}

ПРОПОЗИЦІЯ БОНУСІВ (гайд).
Структура: спочатку депозитний бонус, потім бездепозитний, якщо він передбачений умовами. Озвучити актуальні умови: мінімальна сума, термін, вейджер, фріспіни і ставка за потреби. Підкреслити переваги. Не знецінювати бонус. Для Betking — бустер Х2.
first_deposit_bonus_quote — перша пропозиція депозитного бонусу на сьогодні. first_no_deposit_bonus_quote — перша пропозиція бездепозитного, якщо вона є. Згадка минулого бонусу, «гляну по бонусах», «щось залишу» — не пропозиція.
terms_stated: min_deposit — мінімальна сума депозиту; validity — термін дії або активації; wager — вейджер або відіграш; fs_count_and_bet — кількість фріспінів і ставка. Кожне поле — цитата, null або "n/a".
benefits_quote — фраза, де менеджер пояснює вигоду бонусу.
devalue_quote — лише якщо менеджер знецінює бонус. Приклади з гайду: «заберете, якщо захочете», «коли буде час, подивитесь». Інакше порожній рядок.
x2_quote — фраза про бустер Х2, якщо її сказано. no_deposit_bonus_applicable=true, якщо бездепозитний бонус для цього дзвінка передбачений.
""".strip()


def get_vip_friendly_rapport_prompt() -> str:
    """Окремий виклик: розвиток френдлі і індивідуальний підхід."""
    return """
Ти витягуєш лише «Розвиток френдлі» і «Індивідуальний підхід» з транскрипту VIP Friendly.
НЕ рахуй бали числом у полі level інакше як одне зі значень шкали. Поверни ТІЛЬКИ валідний JSON. Цитата — дослівний фрагмент репліки менеджера або порожній список.

{
  "friendly_level": "7.5|5|2.5|0",
  "friendly_signals": [""],
  "mechanical_only": false,
  "approach_level": "7.5|5|2.5|0",
  "approach_signals": [""],
  "bonuses_only": false
}

РОЗВИТОК ФРЕНДЛІ (гайд).
7,5 — активно розвиває дружній контакт. 5 — підтримує атмосферу, але мало особистих питань або не розвиває відповіді. 2,5 — окремі спроби, розмова переважно стандартна. 0 — дружній контакт відсутній, лише сценарій.
Ознаки з цитатою: доречне питання про життя, інтереси чи плани; підтримка розмови після відповіді; уточнення або коментар; нейтральне саморозкриття; підтримав тему клієнта; повернувся до особистої інформації пізніше.
mechanical_only=true лише якщо є механічне «Як справи?», «Як день проходить?» або «Все добре?» і немає жодного продовження. Тоді friendly_level=0.
Не є розвитком: особисте питання без зв'язку з розмовою; надмірне втручання; розповідь про себе без інтересу клієнта.

ІНДИВІДУАЛЬНИЙ ПІДХІД (гайд).
7,5 — персональний підхід протягом усього діалогу. 5 — коректний контакт, але недостатньо враховує особливості. 2,5 — переважно за сценарієм. 0 — персонального підходу немає.
Ознаки з цитатою: інформація з попередньої взаємодії; реакція на особисте, яким поділився клієнт; адаптація стилю; позитивний контакт без миттєвої дії.
bonuses_only=true, якщо менеджер лише коротко лишив бонуси і немає жодної персоналізації. Тоді approach_level=0.
Не є підходом: механічне ім'я; стандартне «як ваші справи?» без розвитку; однакова подача незалежно від відповідей.
""".strip()


def get_vip_friendly_closing_prompt() -> str:
    """Окремий виклик: завершення дзвінка."""
    return """
Ти витягуєш лише завершення VIP Friendly. НЕ рахуй бали. Поверни ТІЛЬКИ валідний JSON.
Цитата — дослівний фрагмент з кінця дзвінка або порожній рядок. Не вигадуй фраз.

{
  "asked_if_more_questions_quote": "",
  "said_goodbye_quote": "",
  "thanked_quote": "",
  "client_ended_quote": "",
  "connection_dropped_quote": ""
}

ЗАВЕРШЕННЯ (гайд, як у короткому дзвінку).
Три елементи, кожен — цитата менеджера в кінці розмови:
- asked_if_more_questions_quote: «чи не залишилось питань», «чи залишились питання»;
- said_goodbye_quote: прощання, «до зв'язку», «на все добре», «до побачення»;
- thanked_quote: дяка і відкритий контакт («дякую», «пишіть», «звертайтесь», «бережіть»).
client_ended_quote — цитата клієнта, лише якщо він сам завершив дзвінок уже на етапі завершення. Прощання менеджера, після якого клієнт лише відповів «до» або «добре», не є завершенням клієнтом.
connection_dropped_quote — цитата останніх реплік, лише якщо зв'язок перервався.
Те, що формат дзвінка не дав пройти всі етапи, цитатою завершення не є. Тоді всі поля порожні, якщо елементів завершення не було.
""".strip()


VIP_FRIENDLY_PROMPT_TEMPLATE = (
    get_vip_friendly_static_prompt()
    + "\n\nКОНТЕКСТ:\n- Коментар QA / попередній контакт: {{comment}}\n- Важливе: {{note}}"
    + "\n- Клієнт військовий (картка): {{military_hint}}"
    + "\n- Betking X2 бустер застосовний (картка/проєкт): {{betking_hint}}"
)
