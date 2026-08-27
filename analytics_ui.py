"""Спільні фільтри для сторінок VIP-аналітики."""

from __future__ import annotations

from datetime import date

import streamlit as st

from analytics_data import clear_cache, default_period, filter_frame
from ui_theme import clean_select_options, sync_select_state


def render_analytics_filters(df_all) -> tuple:
    date_min, date_max = default_period(df_all)
    if "analytics_period" not in st.session_state:
        st.session_state["analytics_period"] = [date_min, date_max]

    c1, c2, c3 = st.columns([2, 1.2, 1])
    with c1:
        period = st.date_input(
            "Період (дата дзвінка)",
            min_value=date_min,
            max_value=date.today(),
            key="analytics_period",
        )
        if isinstance(period, (list, tuple)) and len(period) == 2:
            d_from, d_to = period
        else:
            d_from = d_to = period if isinstance(period, date) else date.today()
    with c2:
        projects = ["Всі"]
        if not df_all.empty and "project" in df_all.columns:
            projects += sorted(clean_select_options(df_all["project"].dropna().unique().tolist()))
        sync_select_state("analytics_project", projects)
        sel_project = st.selectbox("Проєкт", projects, key="analytics_project")
    with c3:
        st.write("")
        if st.button("Оновити дані", key="analytics_refresh", type="primary"):
            clear_cache()
            st.session_state.pop("analytics_period", None)
            st.rerun()

    df = filter_frame(df_all, d_from, d_to, sel_project)
    return df, d_from, d_to, sel_project
