from __future__ import annotations

import html

import streamlit as st

from chrome import setup_page
from guides_content import GUIDE_VIP_FRIENDLY, GUIDE_VIP_SHORT_90S
from ui_theme import render_page_header


def _render_guide_items(items: list[dict]) -> None:
    for item in items:
        title = html.escape(str(item.get("title") or ""))
        max_pts = html.escape(str(item.get("max_points") or ""))
        with st.expander(f"{item.get('title')} — макс. {item.get('max_points')}", expanded=False):
            st.markdown(
                f"""
                <div class="guide-block guide-criterion">
                  <h4>{title} <span class="guide-max">{max_pts}</span></h4>
                  <div class="guide-body">{html.escape(str(item.get("description") or ""))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if item.get("scale"):
                st.markdown("**Шкала**")
                st.markdown(str(item["scale"]))
            if item.get("notes"):
                st.markdown("**Примітки / виключення**")
                st.markdown(str(item["notes"]))


setup_page("Гайди", active="guides")
render_page_header(
    "Гайди",
    "Повні рубрики з Гайд VIP.xlsx: «Короткий 90 сек» (макс. 30) і «VIP Friendly» (макс. 57,5)",
)

tab_short, tab_friendly = st.tabs(["Короткий 90 сек (макс. 30)", "VIP Friendly (макс. 57,5)"])

with tab_short:
    st.caption("Джерело: аркуш «Короткийдо 100 сек». Вердикт — сума балів; критичні помилки зі сливом обнуляють дзвінок.")
    _render_guide_items(GUIDE_VIP_SHORT_90S)

with tab_friendly:
    st.caption("Джерело: аркуш «VIP FRIENDLY (2-й дзвінок)». Спільні критерії з Коротким — контакт, P.R.E.P., завершення.")
    _render_guide_items(GUIDE_VIP_FRIENDLY)
