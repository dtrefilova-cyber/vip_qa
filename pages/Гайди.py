from __future__ import annotations

import html

import streamlit as st

from chrome import setup_page
from guides_content import APPROVED_ADDITIONS, GUIDE_VIP_FRIENDLY, GUIDE_VIP_SHORT_90S
from ui_theme import render_page_header


def _render_guide_items(items: list[dict]) -> None:
    for item in items:
        title = str(item.get("title") or "")
        max_pts = str(item.get("max_points") or "").strip()
        show_max = bool(max_pts and max_pts not in {"—", "-", "–"})
        expander_label = f"{title} — макс. {max_pts}" if show_max else title
        with st.expander(expander_label, expanded=False):
            h4 = html.escape(title)
            if show_max:
                h4 = f'{h4} <span class="guide-max">{html.escape(max_pts)}</span>'
            st.markdown(
                f"""
                <div class="guide-block guide-criterion">
                  <h4>{h4}</h4>
                  <div class="guide-body">{html.escape(str(item.get("description") or ""))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if item.get("gradation"):
                st.markdown("**Градація балів**")
                st.markdown(str(item["gradation"]))
            if item.get("scale"):
                st.markdown("**Шкала**")
                st.markdown(str(item["scale"]))
            if item.get("notes"):
                st.markdown("**Примітки / виключення**")
                st.markdown(str(item["notes"]))


def _render_approved_additions(items: list[dict]) -> None:
    st.markdown("### Затверджені доповнення")
    for item in items:
        code = str(item.get("code") or "")
        title = str(item.get("title") or "")
        label = f"{code}: {title}" if code else title
        with st.expander(label, expanded=False):
            st.markdown(str(item.get("text") or ""))


setup_page("Гайди", active="guides")
render_page_header("Гайди")

tab_short, tab_friendly, tab_additions = st.tabs(
    ["Короткий 90 сек", "VIP Friendly", "Затверджені доповнення"]
)

with tab_short:
    _render_guide_items(GUIDE_VIP_SHORT_90S)

with tab_friendly:
    _render_guide_items(GUIDE_VIP_FRIENDLY)

with tab_additions:
    _render_approved_additions(APPROVED_ADDITIONS)
