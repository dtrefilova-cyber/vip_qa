from __future__ import annotations

import html

import streamlit as st

from chrome import setup_page
from ui_theme import render_page_header

setup_page("Гайди", active="guides")
render_page_header(
    "Гайди",
    "Бальні рубрики VIP: «Короткий 90 сек» (макс. 30) і «VIP Friendly» (макс. 57,5)",
)

st.markdown("### Короткий 90 сек (макс. 30)")
_SHORT = [
    ("Встановлення контакту", "0 / 2,5 / 5", "Привітання, ім'я клієнта, проєкт; виключення не знижують бал."),
    ("Робота зі «сливом» / утримання", "0…10", "Реакція на спробу завершити, причина, передзвін, конкретний час, фіксація домовленості."),
    ("Критичні помилки зі сливом", "обнуляє дзвінок", "Продовження пітчу після «не можу говорити», штучне затягування тощо."),
    ("P.R.E.P. / заперечення", "0 / 5 / 7,5 / 10", "Найгірше опрацьоване заперечення визначає бал; без заперечень — автомакс."),
    ("Завершення", "0 / 2,5 / 5", "Питання «чи є ще питання», прощання, відкритий контакт; автозалік якщо клієнт кинув першим."),
]

for name, scale, body in _SHORT:
    st.markdown(
        f"""
        <div class="guide-block guide-criterion">
          <h4>{html.escape(name)} <span class="guide-max">{html.escape(scale)}</span></h4>
          <div class="guide-body">{html.escape(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("### VIP Friendly — 2-й дзвінок (макс. 57,5)")
_FRIENDLY = [
    ("Встановлення контакту", "5", "Спільний критерій з «Коротким»."),
    ("Розвиток френдлі", "7,5", "Особисті питання, follow-up, підтримка теми клієнта, повернення до інфо."),
    ("Індивідуальний підхід", "7,5", "Використання попереднього контакту, адаптація стилю, позитивний контакт."),
    ("Заклик до гри", "10", "Депозит сьогодні → завтра → (не для military) відкрите «чому»."),
    ("Пропозиція бонусів", "5", "Спочатку депозитний бонус, умови, переваги; без знецінення."),
    ("P.R.E.P.", "10", "Спільний критерій."),
    ("Завершення", "5", "Спільний критерій."),
    ("Невимушеність", "7,5", "Рівні high / noticeable_gaps / low / critical — класифікація GPT, бал у коді."),
]

for name, scale, body in _FRIENDLY:
    st.markdown(
        f"""
        <div class="guide-block guide-criterion">
          <h4>{html.escape(name)} <span class="guide-max">{html.escape(scale)}</span></h4>
          <div class="guide-body">{html.escape(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
