"""Промпт екстракції фактів для VIP «Короткий 120 сек» (таймінг 30–120 с)."""

from __future__ import annotations


def get_vip_short_static_prompt() -> str:
    full = get_vip_short_90s_analysis_prompt()
    return full.replace(build_vip_short_context(), "").strip()


def build_vip_short_context(
    qa_comment: str = "",
    important_note: str = "",
    *,
    manager_name: str = "",
    project: str = "",
    number_signed: bool = False,
    client_is_military: bool = False,
    last_speaker: str = "",
    duration_sec: float | None = None,
) -> str:
    comment = (qa_comment or "").strip() or "—"
    note = (important_note or "").strip() or "—"
    manager = (manager_name or "").strip() or "—"
    project_name = (project or "").strip() or "—"
    duration = "—" if duration_sec is None else f"{duration_sec:.0f}"
    speaker = (last_speaker or "").strip() or "—"
    signed = "так" if number_signed else "ні"
    military = "так" if client_is_military else "ні"
    return f"""КОНТЕКСТ:
- Менеджер: {manager}
- Проєкт: {project_name}
- Номер підписаний (чекбокс): {signed}
- Гравець військовий (чекбокс): {military}
- Останній спікер (порахував Python): {speaker}
- Тривалість, сек (з транскрипту): {duration}
- Коментар по дзвінку від QA: {comment}
- Важливе / попередній контакт: {note}"""


def get_vip_short_90s_analysis_prompt(
    qa_comment: str = "",
    important_note: str = "",
    *,
    manager_name: str = "",
    project: str = "",
    number_signed: bool = False,
    client_is_military: bool = False,
    last_speaker: str = "",
    duration_sec: float | None = None,
) -> str:
    context = build_vip_short_context(
        qa_comment,
        important_note,
        manager_name=manager_name,
        project=project,
        number_signed=number_signed,
        client_is_military=client_is_military,
        last_speaker=last_speaker,
        duration_sec=duration_sec,
    )
    return f"""
Ти — асистент QA. Твоя єдина задача — витягти атомарні ФАКТИ з транскрипту VIP-короткого дзвінка (таймінг 30–120 сек).
НЕ рахуй бали. НЕ став вердикт RED/GREEN. Поверни ТІЛЬКИ валідний JSON за схемою нижче.

{context}

ЗАГАЛЬНЕ ПРАВИЛО:
- Позитивна дія менеджера (привітання, ім'я, проєкт, прощання, подяка, питання про зручність): true, якщо в транскрипті є відповідна фраза, навіть частково спотворена ASR.
- Порушення і критична помилка: true лише за явного доказу.
- evidence — список рядків "[M:SS] Спікер: цитата". Кожен true у порушеннях і кожен false у позитивних полях потребує рядка evidence або пояснення "фрази немає в транскрипті".
- Якщо таймкоду немає, пиши цитату без нього.

СХЕМА JSON (усі поля обов'язкові):
{{
  "contact": {{
    "greeted": bool,
    "used_client_name": bool,
    "named_project": bool,
    "availability_check_relevant": bool,
    "availability_check_done": bool,
    "greeting_quote": str,
    "client_name_quote": str,
    "project_quote": str,
    "availability_quote": str,
    "manager_name_quote": str,
    "exception_number_signed": bool,
    "exception_prior_messenger_contact": bool,
    "exception_client_recognized_manager": bool,
    "exception_client_interrupted_intro": bool,
    "exception_answered_question_then_finished_intro": bool,
    "evidence": []
  }},
  "slip_handling": {{
    "client_attempted_to_end_call": bool,
    "reason_stated_by_client": bool,
    "reason_clarified_by_manager": bool,
    "manager_reacted_appropriately": bool,
    "proposed_callback": bool,
    "specified_concrete_time": bool,
    "confirmed_agreement_or_clear_refusal": bool,
    "client_flatly_refused_any_callback": bool,
    "retention_opportunity_missed": bool,
    "retention_opportunity_note": str,
    "evidence": []
  }},
  "slip_critical": {{
    "continued_pitch_after_client_said_cannot_talk": bool,
    "continued_pitch_instead_of_agreeing_callback": bool,
    "asked_irrelevant_questions": bool,
    "artificially_extended_call": bool,
    "delayed_ending_after_callback_agreed": bool,
    "evidence": []
  }},
  "prep": {{
    "objections_present": bool,
    "objections": [
      {{
        "type": "no_desire|no_time|no_money|no_payout|bad_bonus_experience|doubts_about_offer|other",
        "handling": "ignored|formal|template_attempt|resolved_no_check|resolved_with_check",
        "quote": "[M:SS] цитата клієнта",
        "right_before_client_hangup": bool
      }}
    ]
  }},
  "closing": {{
    "asked_if_more_questions": bool,
    "said_goodbye": bool,
    "thanked_and_left_contact_open": bool,
    "evidence": []
  }},
  "shared_context": {{
    "client_ended_call_first": bool,
    "client_said_no_time_and_hung_up": bool,
    "client_interrupted_manager": bool,
    "call_format_prevented_full_flow": bool,
    "client_didnt_allow_finish_thought": bool,
    "moved_to_messenger": bool,
    "evidence": []
  }}
}}

contact:
- greeted — будь-яке привітання: "Добрий день", "Вітаю", "Алло, добрий день", "Доброго дня".
- used_client_name — звернувся на ім'я або уточнив "Це <ім'я>?".
- named_project — назвав 777, Betking або Vegas.
- availability_check_relevant — завжди true, крім винятків Д4 і Д5. Д11: перевірка зручності обов'язкова.
- availability_check_done — було питання "Вам зручно говорити?", "Є хвилинка?", "Є час?".
- greeting_quote, client_name_quote, project_quote, availability_quote, manager_name_quote — дослівна цитата з таймкодом. Немає елемента — порожній рядок, не вигадуй.
- exception_number_signed — у "Важливому", коментарі QA або чекбоксі сказано, що номер підписаний / підписав / клієнт бачить, хто дзвонить.
- exception_prior_messenger_contact — у коментарі до дзвінка або у "Важливому" є месенджер (Viber, Telegram, WhatsApp). Тоді коротке представлення лише на ім'я — повний бал контакту, назва проєкту не обов'язкова. Став true.
- exception_client_recognized_manager — клієнт сам назвав менеджера на ім'я або сказав "а, це ви". Якщо клієнт звертається до менеджера на ім'я, «Встановлення контакту» виконано: не знижуй бал на 2,5 і постав exception_client_recognized_manager=true.
- exception_client_interrupted_intro — клієнт перебив представлення.
- exception_answered_question_then_finished_intro — менеджер відповів на питання і далі договорив представлення.

slip_handling і slip_critical:
- Одна репліка — один критерій. Відмова на пропозицію ("не треба", "не надо", "не буду", "без різниці", "не-не") — це заперечення P.R.E.P., не спроба завершити дзвінок.
- client_attempted_to_end_call — true лише якщо клієнт хоче закінчити саму розмову: "не можу говорити", "передзвоніть", "все, до побачення", "пока", "я працюю / я на роботі" вже під час розмови. Відповідь "ні" на перше "є хвилинка?" — це злив, не P.R.E.P. Голе "no" / "не чую" / "I'm sorry", після якого клієнт більше нічого не каже, — client_ended_call_first, не заперечення.
- proposed_callback — пропозиція передзвонити або продовжити у Viber/Telegram. Конкретний день ("післязавтра", "у суботу", "наступного тижня") = specified_concrete_time і confirmed_agreement, якщо клієнт не відмовився.
- retention_opportunity_missed — true лише з сигналу В ЦЬОМУ діалозі, не з поля "Важливе". Сигнал: відмова від бонусу чи депозиту, "не гратиму", тема лімітів. Доречна дія, якої не було: сервіс без бонусу до депозиту або порада змінити ліміти. Якщо клієнт у дзвінку погодився на бонус ("без різниці", "добре", "залишайте", "кидайте") — false, навіть коли в "Важливому" написано, що бонуси до депу він не бере.
- evidence для retention_opportunity_missed — один рядок: цитата сигналу клієнта + що менеджер не зробив. Відсутню дію не цитують. Приклад: "[1:05] Клієнт: бонус до депу не потрібен — менеджер не запропонував сервіс без бонусу до депозиту".
- Приклад 294: менеджер піднімає проблему з лімітами, клієнт підтверджує, далі каже, що працює. Менеджер обіцяє змінити ліміти лише з наступного місяця і лишає бонус із вейджером, слова "сервіс" немає. retention_opportunity_missed=true, evidence: "[0:18] Клієнт: Да, я туда залез — менеджер не запропонував сервіс без бонусу до депозиту".
- Приклад 295: клієнт каже "Там ліміти". Менеджер лише фіксує ліміти і призначає передзвін, не радить їх змінити. retention_opportunity_missed=true, evidence: "[0:40] Клієнт: Там ліміти — менеджер не порадив змінити ліміти".
- Приклад, де false: клієнт на пропозицію бонусу відповідає "без різниці" / "добре" / "кидайте". Це не пропущена можливість.
- asked_irrelevant_questions — лише питання не по темі, поставлені ПІСЛЯ прямої відмови говорити і замість завершення дзвінка. "Чи спортом займаєтесь?" в одній репліці з "є питання?" і подальше "не відволікаю, гарного дня" — не критична помилка. Дружні питання на старті не рахуються.
- Не повертай ended_without_using_available_retention_options. Цього поля немає.
- slip_critical.evidence — окрема цитата з таймкодом для кожного прапорця true. Без цитати прапорець став false.

prep — не заперечення рівно три випадки, і більше нічого:
1. Відповідь на перше "є хвилинка?" / "зручно говорити?" на старті розмови (це злив, не P.R.E.P.).
2. Констатація обмеження без відмови від пропозиції: "не можу переглядати активності", "я не відстежую активності", зіпсоване ASR на кшталт "я не завжди, можна я...". Це ніколи не заперечення.
3. Уточнювальне питання або "не знаю" без відмови від бонусу, депозиту, гри чи виплати ("як?", "ні-ні, не знаю").

Завжди заперечення, якщо клієнт це каже (будь-якою мовою, включно зі зіпсованим ASR: "nie", "no", "ні"):
- відмова від бонусу або депозиту: "бонус до депу не потрібен", "не буду депати", "до поповнення не беру", "nie" одразу після "до поповнення берете бонуси?";
- "немає часу грати", "не буду сьогодні грати", "не прийду", а також "я працюю" / "я на роботі", сказане вже після старту, коли менеджер говорить про бонус;
- сумнів у виплаті чи пропозиції, зокрема дзвінок про те, що бонус згорів і його не повернуть (no_payout), навіть якщо клієнт далі лише каже "так";
- негативний досвід з бонусом: "не щастить", "бонуси погані", "не відігрались".
Коротка відмова без розбору ("не треба", "ні") посеред скрипту, після якої менеджер іде далі за скриптом і не відповідає на зміст, — теж заперечення, handling=formal. Не викидай її.

- no_money — кошти, "немає грошей", "не буду депати" через фінанси. no_time — "немає часу грати" або "я зараз працюю", не для коштів.
- Якщо гравець військовий (ЗСУ, чекбокс або коментар): "немає коштів" і "немає часу" не опрацьовуються. Не включай їх в objections. Якщо інших заперечень немає — objections_present=false.
- quote — "[M:SS]" і дослівна цитата клієнта з транскрипту.
- right_before_client_hangup = true лише якщо це остання репліка клієнта, після неї менеджер не сказав жодного слова і дзвінок завершився. Якщо менеджер після цієї репліки відповів, пояснив або попрощався — false.
- handling, один рівень:
  - ignored — заперечення проігноровано;
  - formal — "добре" / "зрозумів" або продовжив скрипт, не відповідаючи на зміст відмови;
  - template_attempt — назвав конкретну альтернативу (інший бонус, суму, оберти) саме у відповідь на відмову, без перевірки, чи клієнт її прийняв;
  - resolved_no_check — опрацьовано по суті (пояснив, домовився, зупинився), без питання на перевірку рішення;
  - resolved_with_check — опрацьовано і є питання, на яке клієнт відповідає рішенням ("заберете?", "домовились?" і клієнт каже так/ні). "Зрозуміли?" саме по собі — ще resolved_no_check.
- Якщо заперечень не було — objections_present=false і objections=[].

closing і shared_context:
- asked_if_more_questions — "Ще питання є?", "Може якісь питання?", "є якісь запитання", "чи не залишилось питань", "чи залишились питання", "додаткові питання", "Можу ще чимось допомогти?".
- said_goodbye — "До побачення", "Гарного дня", "На все добре", "Бувайте", "Па-па", "До зв'язку". "Ще питання є? … Гарного дня" — це два елементи, навіть у різних репліках. "До зв'язку" — це прощання.
- thanked_and_left_contact_open — відкритий контакт ("на зв'язку", "пишіть", "звертайтесь", "рада була") разом із прощанням-теплом ("дякую", "бережіть себе", "рада була"). Саме "на зв'язку" без цього — false.
- client_ended_call_first — true, якщо клієнт завершує розмову ("пока", "до побачення", "не можу говорити"), а менеджер до цього не спитав "є питання?". Якщо менеджер уже спитав і попрощався, а клієнт лише відповів тим самим прощанням — false. Кілька реплік "no" / "sorry" без змістовної відповіді — true.
- call_format_prevented_full_flow — true, якщо в діалозі немає реплік клієнта і менеджер не встиг попрощатися (обірваний монозапис).
- moved_to_messenger — домовились продовжити в месенджері або менеджер чекає повідомлення від клієнта.
""".strip()


def get_vip_contact_prompt() -> str:
    """Окремий виклик контакту для short і Friendly. Д11."""
    return """
Поверни лише JSON контактного блоку. Кожен елемент — окрема цитата менеджера з таймкодом, якщо він є в транскрипті. Немає елемента — порожній рядок і false. Не вигадуй.

Елементи Д11: привітання, ім'я клієнта, проєкт (777 / Betking / Vegas), перевірка зручності («Вам зручно?», «Є хвилинка?», «Є час?»).
manager_name_quote — менеджер назвав себе («мене звати», «я ваш менеджер»).
Якщо клієнт звертається до менеджера на ім'я, «Встановлення контакту» виконано: не знижуй бал на 2,5 і постав exception_client_recognized_manager=true.

{
  "contact": {
    "greeted": bool,
    "greeting_quote": "",
    "used_client_name": bool,
    "client_name_quote": "",
    "named_project": bool,
    "project_quote": "",
    "availability_check_done": bool,
    "availability_quote": "",
    "manager_introduced_self": bool,
    "manager_name_quote": "",
    "exception_client_recognized_manager": bool,
    "availability_check_relevant": true
  }
}
""".strip()


def get_vip_short_analysis_prompt(qa_comment: str = "", important_note: str = "") -> str:
    return get_vip_short_90s_analysis_prompt(qa_comment, important_note)


VIP_SHORT_90S_PROMPT_TEMPLATE = (
    get_vip_short_static_prompt()
    + "\n\nКОНТЕКСТ ВІД QA:\n- Коментар по дзвінку: {{comment}}\n- Важливе / попередній контакт: {{note}}"
)
