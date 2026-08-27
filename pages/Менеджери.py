import streamlit as st

from analytics_data import load_vip_logs
from analytics_ui import render_analytics_filters
from chrome import setup_page
from dashboard_theme import table_card
from ui_theme import render_page_header
from vip_ui import load_managers_context

setup_page("Менеджери", active="managers")
render_page_header(
    "Менеджери",
    "Довідник VIP-менеджерів з окремого Google Sheet VIP_SHORT_SHEET_ID",
)

managers_config, _, _ = load_managers_context()
if managers_config:
    st.dataframe(
        [
            {
                "Проєкт": item.get("project") or "—",
                "Тімлід": item.get("tl") or "—",
                "Менеджер": item.get("manager") or "—",
            }
            for item in managers_config
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Довідник менеджерів порожній або не завантажився з аркуша MANAGERS.")

df_all = load_vip_logs()
df, _, _, _ = render_analytics_filters(df_all)
if df.empty:
    st.caption("Немає записів у vip_short_call_logs за обраний період.")
    st.stop()


def _render_manager_stats():
    stats = (
        df.groupby(["ret_manager", "project", "tl_name"], dropna=False)
        .agg(
            кількість=("verdict", "size"),
            green=("is_green", "sum"),
            red=("is_red", "sum"),
        )
        .reset_index()
        .sort_values("кількість", ascending=False)
    )
    st.dataframe(stats, use_container_width=True, hide_index=True)


table_card("Вердикти по менеджерах за період", _render_manager_stats)
