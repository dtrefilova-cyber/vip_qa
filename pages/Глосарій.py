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
  <li><strong>VIP Friendly (2-й дзвінок)</strong> — бальна рубрика до 60 балів; окрема сторінка в сайдбарі.</li>
  <li><strong>Злив клієнта</strong> — спроба клієнта достроково завершити розмову; критерій утримання контакту (Короткий).</li>
  <li><strong>Критична помилка (зливу)</strong> — порушення з гайду зі зливом, яке обнуляє весь короткий дзвінок (0/30).</li>
  <li><strong>P.R.E.P.</strong> — робота з запереченням; бал береться по найгіршому рівню опрацювання серед усіх заперечень.</li>
  <li><strong>Розвиток френдлі</strong> — особисті питання, follow-up і повернення до тем клієнта (Friendly).</li>
  <li><strong>Індивідуальний підхід</strong> — опора на попередній контакт і адаптація стилю (Friendly).</li>
  <li><strong>Невимушеність</strong> — якісний рівень діалогу (high…critical); GPT класифікує рівень, код мапить у бали.</li>
  <li><strong>Заклик до гри</strong> — уточнення депозиту сьогодні/завтра; для військових без питання «чому».</li>
  <li><strong>Факти GPT</strong> — атомарні true/false / enum; бали рахує лише Python.</li>
</ul>
</div>
""",
    unsafe_allow_html=True,
)
