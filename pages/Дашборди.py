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
render_page_header("Дашборди", "VIP бальна аналітика (Короткий 90 сек / Friendly) + історичні scored/green/red")

df_all = load_vip_logs()
df, _, _, _ = render_analytics_filters(df_all)

total = len(df)
scored = df[df["percent"].notna()] if not df.empty and "percent" in df.columns else df.iloc[0:0]
avg_pct = float(scored["percent"].mean()) if len(scored) else None
critical = int(df["is_critical_fail"].sum()) if not df.empty and "is_critical_fail" in df.columns else 0
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
render_kpi_row(
    [
        ("Всього аналізів", f"{total:,}".replace(",", " ")),
        ("Середній %", f"{avg_pct:.1f}%" if avg_pct is not None else "—"),
        ("Критичні", str(critical)),
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
        if "rubric_call_type" in work.columns and work["rubric_call_type"].astype(str).str.len().gt(0).any():
            work["rubric_call_type"] = _label_series(work["rubric_call_type"])
            counts = work.groupby("rubric_call_type").size().reset_index(name="кількість")
            fig = px.pie(counts, names="rubric_call_type", values="кількість")
            style_figure(fig, showlegend=True)
            render_plotly(fig, height=340, key="dash_type")
        else:
            work["verdict"] = _label_series(work["verdict"]).str.upper()
            counts = work.groupby("verdict").size().reset_index(name="кількість")
            fig = px.pie(counts, names="verdict", values="кількість")
            style_figure(fig, showlegend=True)
            render_plotly(fig, height=340, key="dash_verdict")

    chart_card("Розподіл по типах / статусах", _render_verdict_pie)

with col2:

    def _render_mgr_chart():
        work = df.copy()
        work["ret_manager"] = _label_series(work["ret_manager"])
        work = work[(work["ret_manager"] != "—") & work["percent"].notna()]
        if work.empty:
            st.caption("Немає бальних записів для менеджерів.")
            return
        grouped = (
            work.groupby("ret_manager")
            .agg(avg_percent=("percent", "mean"), total=("percent", "size"))
            .reset_index()
            .sort_values("avg_percent", ascending=False)
            .head(20)
        )
        fig = px.bar(
            grouped,
            x="ret_manager",
            y="avg_percent",
            color_discrete_sequence=[colors[2]],
        )
        style_figure(fig, showlegend=False, xaxis_title="", yaxis_title="Середній %")
        render_plotly(fig, height=340, key="dash_mgr")

    chart_card("Середній % по менеджерах", _render_mgr_chart)


def _render_proj_chart():
    work = df.copy()
    work["project"] = _label_series(work["project"])
    work = work[(work["project"] != "—") & work["percent"].notna()]
    if work.empty:
        st.caption("Немає бальних записів для проєктів.")
        return
    grouped = (
        work.groupby("project")
        .agg(avg_percent=("percent", "mean"), total=("percent", "size"))
        .reset_index()
        .sort_values("avg_percent", ascending=False)
    )
    fig = px.bar(
        grouped,
        x="project",
        y="avg_percent",
        color_discrete_sequence=[colors[0]],
    )
    style_figure(fig, showlegend=False, xaxis_title="", yaxis_title="Середній %")
    render_plotly(fig, height=340, key="dash_proj")


chart_card("Середній % по проєктах", _render_proj_chart)
