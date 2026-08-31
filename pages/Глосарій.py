import streamlit as st

from chrome import setup_page
from ui_theme import render_page_header

setup_page("Глосарій", active="glossary")
render_page_header("Глосарій", "Термінологія VIP бального скорингу")

st.markdown(
    """
<div class="guide-block">
<ul class="guide-list">
  <li><strong>Короткий 90 сек</strong> — бальна рубрика до 30 балів; замінює старий red/green «Короткий».</li>
  <li><strong>VIP Friendly (2-й дзвінок)</strong> — бальна рубрика до 57,5 бала.</li>
  <li><strong>Слив клієнта</strong> — спроба клієнта достроково завершити розмову; критерій утримання контакту.</li>
  <li><strong>P.R.E.P.</strong> — робота з запереченням; бал береться по найгіршому рівню опрацювання.</li>
  <li><strong>Розвиток френдлі</strong> — особисті питання, follow-up і повернення до тем клієнта.</li>
  <li><strong>Індивідуальний підхід</strong> — опора на попередній контакт і адаптація стилю.</li>
  <li><strong>Невимушеність</strong> — якісний рівень діалогу (high…critical), який GPT класифікує, а код мапить у бали.</li>
  <li><strong>Критична помилка (Короткий)</strong> — обнуляє весь дзвінок (0/30), без окремої red/green-надбудови.</li>
  <li><strong>Факти GPT</strong> — атомарні true/false / enum; бали рахує лише Python.</li>
</ul>
</div>
""",
    unsafe_allow_html=True,
)
