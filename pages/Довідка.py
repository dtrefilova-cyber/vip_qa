import streamlit as st

from chrome import setup_page
from ui_theme import render_page_header

setup_page("Довідка", active="help")
render_page_header("Довідка", "AI Quality — оцінювання дзвінків відділу VIP")

st.markdown(
    """
- **Короткі дзвінки** — рубрика «Короткий 90 сек» (макс. 30): завантаження аудіо й бальний аналіз.
- **VIP Friendly (2-й дзвінок)** — окрема сторінка, рубрика макс. 60.
- **Дашборди** — середній % і розбивка з `vip_short_call_logs`.
- **Менеджери** — довідник з Google Sheet MANAGERS.
- **Гайди** — повний текст критеріїв обох типів.
- **Глосарій** — терміни скорингу.
- **Налаштування** — кеш і моніторинг активності.
"""
)

st.info("Питання та пропозиції — до QA-менеджера відділу VIP.")
