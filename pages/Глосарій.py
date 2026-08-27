import streamlit as st

from chrome import setup_page
from ui_theme import render_page_header

setup_page("Глосарій", active="glossary")
render_page_header("Глосарій", "Термінологія VIP-скорингу коротких дзвінків")

st.markdown(
    """
<div class="guide-block">
<ul class="guide-list">
  <li><strong>GREEN / RED</strong> — детермінований вердикт коду, не бал. GPT повертає лише факти.</li>
  <li><strong>Структура</strong> — привітання, привід дзвінка, бонус/умови, прощання.</li>
  <li><strong>Дозвіл ТЛ</strong> — єдина підстава звільнити дзвінок від структури, і лише якщо не минуло 30+ днів.</li>
  <li><strong>4в1</strong> — пакет бонусів; у діалозі може звучати як «два бонуси в доступі».</li>
  <li><strong>бд / БД / бдб</strong> — бездепозитний бонус. «Бездеп» у мовленні менеджера заборонене.</li>
  <li><strong>Фабрикація відповіді</strong> — менеджер відповідає за клієнта і на цьому згортає розмову.</li>
  <li><strong>Автовідповідач</strong> — ширше за голосову пошту: hold, обрив, тиша без живої реакції.</li>
  <li><strong>Mismatch коментаря</strong> — коментар QA прямо суперечить діалогу, не «не згадано дослівно».</li>
</ul>
</div>
""",
    unsafe_allow_html=True,
)
