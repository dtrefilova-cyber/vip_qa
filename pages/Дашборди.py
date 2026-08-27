import plotly.express as px
import streamlit as st

from analytics_data import load_vip_logs
from analytics_ui import render_analytics_filters
from chrome import setup_page
from dashboard_theme import (
    chart_card,
    chart_sequence,
    render_kpi_row,
    render_plotly,
    style_figure,
)
from ui_theme import render_page_header

setup_page("Дашборди", active="dashboards")
render_page_header("Дашборди", "VIP verdict-аналітика (red/green) за менеджерами та періодом")

df_all = load_vip_logs()
df, _, _, _ = render_analytics_filters(df_all)

total = len(df)
green = int(df["is_green"].sum()) if not df.empty and "is_green" in df.columns else 0
red = int(df["is_red"].sum()) if not df.empty and "is_red" in df.columns else 0
projects = (
    {
        str(p).strip()
        for p in df["project"].dropna().tolist()
        if str(p).strip() and str(p).strip().lower() not in {"nan", "none"}
    }
    if not df.empty
    else set()
)
mgrs = (
    {
        str(p).strip()
        for p in df["ret_manager"].dropna().tolist()
        if str(p).strip() and str(p).strip().lower() not in {"nan", "none"}
    }
    if not df.empty
    else set()
)
green_pct = f"{green / total * 100:.0f}%" if total else "—"
render_kpi_row(
    [
        ("Всього аналізів", f"{total:,}".replace(",", " ")),
        ("GREEN", str(green)),
        ("RED", str(red)),
        ("GREEN %", green_pct),
        ("Менеджерів", str(len(mgrs))),
        ("Проєктів", str(len(projects))),
    ]
)

if df.empty:
    st.info("За обраний період немає даних у vip_short_call_logs.")
    st.stop()

colors = chart_sequence()


def _label_series(series):
    cleaned = series.fillna("").astype(str).map(lambda x: x.strip())
    return cleaned.mask(cleaned.eq("") | cleaned.str.lower().isin(["nan", "none", "null"]), "—")


col1, col2 = st.columns(2)

with col1:

    def _render_verdict_pie():
        work = df.copy()
        work["verdict"] = _label_series(work["verdict"]).str.upper()
        counts = work.groupby("verdict").size().reset_index(name="кількість")
        fig = px.pie(counts, names="verdict", values="кількість")
        style_figure(fig, showlegend=True)
        render_plotly(fig, height=340, key="dash_verdict")

    chart_card("RED / GREEN", _render_verdict_pie)

with col2:

    def _render_mgr_chart():
        work = df.copy()
        work["ret_manager"] = _label_series(work["ret_manager"])
        work = work[work["ret_manager"] != "—"]
        grouped = (
            work.groupby("ret_manager")
            .agg(green=("is_green", "sum"), red=("is_red", "sum"), total=("verdict", "size"))
            .reset_index()
            .sort_values("total", ascending=False)
            .head(20)
        )
        fig = px.bar(
            grouped,
            x="ret_manager",
            y=["green", "red"],
            barmode="stack",
            color_discrete_sequence=[colors[2], colors[4] if len(colors) > 4 else colors[0]],
        )
        style_figure(fig, showlegend=True, xaxis_title="", yaxis_title="")
        render_plotly(fig, height=340, key="dash_mgr")

    chart_card("Вердикти по менеджерах", _render_mgr_chart)


def _render_proj_chart():
    work = df.copy()
    work["project"] = _label_series(work["project"])
    work = work[work["project"] != "—"]
    grouped = (
        work.groupby("project")
        .agg(green=("is_green", "sum"), red=("is_red", "sum"))
        .reset_index()
    )
    fig = px.bar(
        grouped,
        x="project",
        y=["green", "red"],
        barmode="stack",
        color_discrete_sequence=[colors[2], colors[0]],
    )
    style_figure(fig, showlegend=True, xaxis_title="", yaxis_title="")
    render_plotly(fig, height=340, key="dash_proj")


chart_card("Вердикти по проєктах", _render_proj_chart)
