import streamlit as st

from chrome import setup_page
from ui_theme import render_page_header

setup_page("Довідка", active="help")
render_page_header("Довідка", "AI Quality — оцінювання коротких дзвінків відділу VIP")

st.markdown(
    """
- **Короткі дзвінки** — єдиний тип дзвінка VIP: завантаження аудіо й аналіз red/green.
- **Дашборди** — огляд вердиктів з `vip_short_call_logs`.
- **Менеджери** — довідник з Google Sheet `VIP_SHORT_SHEET_ID` і статистика red/green.
- **Гайди** — стандарти оцінки короткого VIP-дзвінка.
- **Глосарій** — терміни скорингу.
- **Налаштування** — кеш і моніторинг активності.
"""
)

st.info("Питання та пропозиції — до QA-менеджера відділу VIP.")
