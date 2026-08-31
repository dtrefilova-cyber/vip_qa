"""UI helpers for analytics dashboards (theme-aware Plotly)."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from ui_theme import render_page_header, render_simple_kpi_cards, theme_mode

CHART_LIGHT = ["#6D4AFF", "#3B82F6", "#10B981", "#F59E0B", "#A78BFA"]
CHART_DARK = ["#8B74FF", "#60A5FA", "#34D399", "#FBBF24", "#C4B5FD"]

COLOR_BLUE = "#6D4AFF"
COLOR_CYAN = "#3B82F6"
COLOR_TEAL = "#10B981"
COLOR_PURPLE = "#A78BFA"
COLOR_AMBER = "#F59E0B"
COLOR_ROSE = "#F472B6"
PASTEL_SEQUENCE = CHART_LIGHT

_PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}


def chart_sequence() -> list[str]:
    return list(CHART_DARK if theme_mode() == "dark" else CHART_LIGHT)


def _theme_colors() -> dict[str, str]:
    dark = theme_mode() == "dark"
    return {
        "paper": "rgba(0,0,0,0)",
        "text": "#E5E7EB" if dark else "#1F2937",
        "heading": "#F9FAFB" if dark else "#111827",
        "grid": "rgba(148,163,184,0.18)" if dark else "rgba(148,163,184,0.28)",
        "muted": "#94A3B8" if dark else "#64748B",
        "hover_bg": "#1A2438" if dark else "#FFFFFF",
        "hover_border": "#273149" if dark else "#E4E7EF",
        "donut_gap": "#172033" if dark else "#FFFFFF",
    }


def rgba(hex_color: str, alpha: float) -> str:
    raw = str(hex_color).lstrip("#")
    if len(raw) != 6:
        return f"rgba(109,74,255,{alpha})"
    red, green, blue = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    return f"rgba({red},{green},{blue},{alpha})"


def _plotly_layout() -> dict:
    """Layout tokens compatible with Plotly 5+ and 6+ (no removed titlefont)."""
    c = _theme_colors()
    axis = dict(
        gridcolor=c["grid"],
        gridwidth=1,
        linecolor="rgba(0,0,0,0)",
        zeroline=False,
        tickfont=dict(color=c["muted"], size=12),
        # Plotly 6 removed axis.titlefont — use nested title.font
        title=dict(font=dict(color=c["muted"], size=12)),
        showline=False,
        automargin=True,
        ticks="",
        color=c["muted"],
        showticklabels=True,
    )
    return dict(
        paper_bgcolor=c["paper"],
        plot_bgcolor=c["paper"],
        font=dict(family="Inter, system-ui, sans-serif", color=c["text"], size=13),
        title=dict(font=dict(size=14, color=c["heading"])),
        xaxis=axis,
        yaxis=dict(**axis, showgrid=True),
        hoverlabel=dict(
            bgcolor=c["hover_bg"],
            bordercolor=c["hover_border"],
            font=dict(color=c["text"], size=13, family="Inter, system-ui, sans-serif"),
            align="left",
        ),
        legend=dict(
            font=dict(color=c["text"], size=12),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            orientation="h",
            yanchor="bottom",
            y=1.08,
            x=0,
        ),
        margin=dict(l=8, r=16, t=36, b=8),
        bargap=0.32,
        bargroupgap=0.14,
    )


def _safe_update_layout(fig, **kwargs) -> None:
    """Apply layout kwargs without crashing on Plotly 5/6 validator differences."""
    cleaned: dict = {}
    for key, value in kwargs.items():
        if key in {"xaxis_title", "yaxis_title", "title"}:
            if value in ("", None):
                continue
            if isinstance(value, dict) and not str(value.get("text") or "").strip():
                continue
            cleaned[key] = value
            continue
        cleaned[key] = value
    if not cleaned:
        return
    try:
        fig.update_layout(**cleaned)
        return
    except Exception:
        pass
    for key, value in cleaned.items():
        try:
            fig.update_layout(**{key: value})
        except Exception:
            continue


def style_figure(fig, *, orientation: str = "v", **layout_kwargs):
    colors = _theme_colors()
    try:
        fig.update_layout(template="plotly_white")
    except Exception:
        pass
    _safe_update_layout(fig, **_plotly_layout())
    hover_v = "<b>%{x}</b><br>%{y}<extra></extra>"
    hover_h = "<b>%{y}</b><br>%{x}<extra></extra>"
    bar_kwargs = dict(
        marker_line_width=0,
        textfont=dict(
            size=12,
            family="Inter, system-ui, sans-serif",
            color=colors["heading"],
        ),
        textposition="outside",
        cliponaxis=False,
        hovertemplate=hover_h if orientation == "h" else hover_v,
        opacity=0.96,
    )
    try:
        fig.update_traces(selector=dict(type="bar"), **bar_kwargs)
    except Exception:
        pass
    try:
        fig.update_traces(
            selector=dict(type="pie"),
            textinfo="percent",
            textposition="outside",
            textfont=dict(size=12, color=colors["text"], family="Inter, system-ui, sans-serif"),
            hole=0.62,
            sort=False,
            direction="clockwise",
            marker=dict(line=dict(color=colors["donut_gap"], width=3)),
            hovertemplate="<b>%{label}</b><br>%{value:,}<br>%{percent}<extra></extra>",
            pull=0,
        )
    except Exception:
        pass
    try:
        fig.update_traces(
            selector=dict(type="scatter"),
            line=dict(width=3, shape="spline"),
            marker=dict(size=8, line=dict(width=2, color=colors["hover_bg"])),
            hovertemplate="<b>%{x}</b><br>%{y}<extra></extra>",
        )
    except Exception:
        pass
    try:
        fig.update_xaxes(showgrid=orientation == "h")
        fig.update_yaxes(showgrid=orientation != "h")
    except Exception:
        pass
    if layout_kwargs:
        # Plotly 6 prefers title as {text: ...}; keep string kwargs working.
        for key in ("xaxis_title", "yaxis_title", "title"):
            if key in layout_kwargs and not isinstance(layout_kwargs[key], dict):
                if layout_kwargs[key] in ("", None):
                    layout_kwargs.pop(key, None)
                else:
                    layout_kwargs[key] = {"text": layout_kwargs[key]}
        _safe_update_layout(fig, **layout_kwargs)
    return fig


def render_plotly(fig, *, height: int | None = None, key: str | None = None) -> None:
    """Render a Plotly figure with the app Light/Dark palette (not Streamlit's default)."""
    if height:
        _safe_update_layout(fig, height=height)
    kwargs = {
        "use_container_width": True,
        "config": _PLOTLY_CONFIG,
    }
    if key:
        kwargs["key"] = f"{key}_plotly6_{theme_mode()}"
    try:
        st.plotly_chart(fig, theme=None, **kwargs)
    except TypeError:
        st.plotly_chart(fig, **kwargs)


def inject_dashboard_styles() -> None:
    return


def kpi_from_dataframe(df) -> list[tuple[str, str]]:
    if df.empty:
        return [
            ("Всього аналізів", "0"),
            ("Середній бал", "—"),
            ("Проєктів", "0"),
            ("QA", "0"),
            ("Менеджерів", "0"),
        ]
    avg = df["total_score"].mean()
    projects = {
        str(p).strip()
        for p in df["project"].dropna().tolist()
        if str(p).strip() and str(p).strip().lower() not in {"nan", "none"}
    }
    qa = {
        str(p).strip()
        for p in df["qa_manager"].dropna().tolist()
        if str(p).strip() and str(p).strip().lower() not in {"nan", "none"}
    }
    mgr = {
        str(p).strip()
        for p in df["ret_manager"].dropna().tolist()
        if str(p).strip() and str(p).strip().lower() not in {"nan", "none"}
    }
    return [
        ("Всього аналізів", f"{len(df):,}".replace(",", " ")),
        ("Середній бал", f"{avg:.1f}" if avg == avg else "—"),
        ("Проєктів", str(len(projects))),
        ("QA", str(len(qa))),
        ("Менеджерів", str(len(mgr))),
    ]


def render_kpi_row(items: list[tuple[str, str]]) -> None:
    render_simple_kpi_cards(items)


_CARD_TITLE_STYLE = (
    "font-size:12px;font-weight:600;color:var(--text-muted);"
    "text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px"
)


def chart_card(title: str, render_fn: Callable[[], None]) -> None:
    with st.container(border=True):
        st.markdown(f'<p style="{_CARD_TITLE_STYLE}">{title}</p>', unsafe_allow_html=True)
        try:
            render_fn()
        except Exception as exc:
            name = type(exc).__name__
            if name in {"RerunException", "StopException"}:
                raise
            st.info("Не вдалося побудувати діаграму. Спробуйте оновити сторінку.")


def table_card(title: str, render_fn: Callable[[], None]) -> None:
    with st.container(border=True):
        st.markdown(f'<p style="{_CARD_TITLE_STYLE}">{title}</p>', unsafe_allow_html=True)
        render_fn()


def filter_card(render_fn: Callable[[], None]) -> None:
    with st.container(border=True):
        render_fn()
