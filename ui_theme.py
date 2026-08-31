"""Operational QA theme layer: tokens, Light/Dark toggle, shared UI helpers."""

from __future__ import annotations

import html
import re
from pathlib import Path

import streamlit as st

NAV_ITEMS = [
    {"id": "short", "label": "Короткі дзвінки", "icon": "📞", "page": "__home__"},
    {
        "id": "friendly",
        "label": "VIP Friendly (2-й дзвінок)",
        "icon": "🤝",
        "page": "pages/VIP_Friendly.py",
    },
    {"id": "dashboards", "label": "Дашборди", "icon": "📊", "page": "pages/Дашборди.py"},
    {"id": "managers", "label": "Менеджери", "icon": "👥", "page": "pages/Менеджери.py"},
    {"id": "guides", "label": "Гайди", "icon": "📘", "page": "pages/Гайди.py"},
    {"id": "glossary", "label": "Глосарій", "icon": "🗂", "page": "pages/Глосарій.py"},
    {"id": "settings", "label": "Налаштування", "icon": "⚙", "page": "pages/Налаштування.py"},
    {"id": "help", "label": "Довідка", "icon": "❓", "page": "pages/Довідка.py"},
]

QA_MANAGERS = [
    "Дар'я", "Надя", "Настя", "Владимира", "Діана", "Савелій", "Олексій", "Катерина", "Ірина",
]

_TOKENS_PATH = Path(__file__).resolve().parent / "aiq_tokens.css"
THEME_KEY = "aiq_theme_mode"
UI_BUILD = "vip-select-session-0827"
SESSION_BUILD_KEY = "_ui_build"

SCORE_TONE_LABEL = {"ok": "GOOD", "mid": "ATTENTION", "bad": "ATTENTION", "wait": "NOT ANALYZED"}

STATUS_META = {
    "new": ("new", "НОВИЙ"),
    "ready": ("ready", "ГОТОВИЙ"),
    "run": ("run", "АНАЛІЗУЄТЬСЯ"),
    "done": ("done", "ПРОАНАЛІЗОВАНО"),
    "err": ("err", "ПОМИЛКА"),
}


def ensure_theme_state() -> str:
    mode = st.session_state.get(THEME_KEY)
    if mode not in ("light", "dark"):
        # Seed from Streamlit config once
        seed = "light"
        try:
            if str(st.get_option("theme.base") or "").lower() == "dark":
                seed = "dark"
        except Exception:
            pass
        st.session_state[THEME_KEY] = seed
        mode = seed
    return mode


def theme_mode() -> str:
    return ensure_theme_state()


def render_theme_toggle() -> None:
    """Sidebar Light/Dark switch — persists in session_state across pages."""
    mode = ensure_theme_state()
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "☀ Light",
            key="aiq_theme_light_btn",
            use_container_width=True,
            type="primary" if mode == "light" else "secondary",
        ):
            st.session_state[THEME_KEY] = "light"
            st.rerun()
    with c2:
        if st.button(
            "🌙 Dark",
            key="aiq_theme_dark_btn",
            use_container_width=True,
            type="primary" if mode == "dark" else "secondary",
        ):
            st.session_state[THEME_KEY] = "dark"
            st.rerun()


def inject_app_css() -> None:
    mode = ensure_theme_state()
    tokens = _TOKENS_PATH.read_text(encoding="utf-8") if _TOKENS_PATH.exists() else ""
    tokens = re.sub(r"@import\s+url\([^)]+\)\s*;", "", tokens)
    css = (
        f"{tokens}\n"
        f"html,body,.stApp,[data-testid='stAppViewContainer']{{"
        f"background:var(--bg-page)!important;}}\n"
    )
    payload = f"<style id='aiq-tokens'>{css}</style>"
    try:
        st.html(payload)
    except Exception:
        st.markdown(payload, unsafe_allow_html=True)
    try:
        import streamlit.components.v1 as components

        components.html(
            f"""
            <script>
            (function() {{
              var mode = {mode!r};
              var doc = window.parent.document;
              doc.documentElement.setAttribute('data-aiq-theme', mode);
              if (doc.body) doc.body.setAttribute('data-aiq-theme', mode);
              var app = doc.querySelector('.stApp');
              if (app) app.setAttribute('data-aiq-theme', mode);
            }})();
            </script>
            """,
            height=0,
            width=0,
        )
    except Exception:
        pass


def render_page_header(
    title: str,
    subtitle: str = "",
    *,
    date_label: str | None = None,
) -> None:
    """Заголовок сторінки. Плоский HTML — Streamlit інакше може «виплюнути» зайві </div>."""
    blocks = [f'<h1 class="page-header__title">{html.escape(title)}</h1>']
    if subtitle:
        blocks.append(f'<p class="page-header__subtitle">{html.escape(subtitle)}</p>')
    if date_label:
        blocks.append(
            f'<div class="page-header__meta">'
            f"<span>📅 {html.escape(str(date_label))}</span></div>"
        )
    st.markdown(
        f'<div class="page-header">{"".join(blocks)}</div>',
        unsafe_allow_html=True,
    )


def render_stat_cards(
    items: list[tuple[str, str, str, str, str]],
    *,
    simple: bool = False,
) -> None:
    cols = st.columns(len(items))
    simple_cls = " simple" if simple else ""
    for col, (ico, tone, num, label, sub) in zip(cols, items):
        with col:
            ico_html = ""
            if not simple:
                ico_html = (
                    f'<div class="stat-ico" style="background:var(--{html.escape(tone)}-bg,'
                    f' var(--accent-primary-soft));color:var(--{html.escape(tone)},'
                    f' var(--accent-primary));">{ico}</div>'
                )
            st.markdown(
                f"""
        <div class="stat-card{simple_cls}">
          {ico_html}
          <div class="stat-num">{html.escape(str(num))}</div>
          <div class="stat-label">{html.escape(label)}</div>
          <div class="stat-sub">{html.escape(sub)}</div>
        </div>""",
                unsafe_allow_html=True,
            )


def render_simple_kpi_cards(items: list[tuple[str, str]]) -> None:
    """Окремі колонки — Streamlit ламає великий HTML-блок із кількома картками."""
    if not items:
        return
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        with col:
            st.markdown(
                f"""
                <div class="kpi-card">
                  <div class="kpi-card__label">{html.escape(str(label))}</div>
                  <div class="kpi-card__value">{html.escape(str(value))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def clean_select_options(values) -> list[str]:
    """Прибирає порожні / NaN значення зі списків selectbox (без зміни порядку логіки)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        text = str(raw).strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def reset_stale_session() -> None:
    """Обнуляє session_state після оновлення застосунку.

    Інакше Streamlit лишає старий вибір у selectbox і падає з KeyError
    на сторінці, ще до карток.
    """
    if st.session_state.get(SESSION_BUILD_KEY) == UI_BUILD:
        return
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state[SESSION_BUILD_KEY] = UI_BUILD


def sync_select_state(key: str, options) -> None:
    """Скидає значення selectbox, якого вже немає в options.

    Streamlit кидає KeyError, якщо в session_state збережено вибір, якого
    немає в поточному списку (проєкт або менеджер змінилися в MANAGERS,
    список QA оновили, після деплою лишилася стара сесія).
    """
    if key not in st.session_state:
        return
    value = st.session_state.get(key)
    if value is None:
        return
    allowed = list(options or [])
    if value not in allowed:
        del st.session_state[key]


def status_pill_html(kind: str) -> str:
    cls, label = STATUS_META.get(kind, STATUS_META["new"])
    return (
        f'<span class="status-pill {html.escape(cls)}">'
        f'<span class="dot"></span>{html.escape(label)}</span>'
    )


def score_result_label(tone: str) -> str:
    return SCORE_TONE_LABEL.get(tone or "wait", "NOT ANALYZED")


def score_banner_html(score, *, tone: str | None = None) -> str:
    try:
        val = float(score)
        num = f"{val:.0f}"
    except (TypeError, ValueError):
        return ""
    if tone is None:
        if val >= 80:
            tone = "ok"
        elif val >= 60:
            tone = "mid"
        else:
            tone = "mid"  # TZ: don't use aggressive red for <80 unless error
    label = score_result_label(tone)
    return (
        f'<div class="score-banner {html.escape(tone)}">'
        f'<div class="num">{html.escape(num)} <span style="font-size:13px;font-weight:500;'
        f'color:var(--text-muted)">/ 100</span></div>'
        f'<div class="lbl" style="color:inherit">{html.escape(label)}</div></div>'
    )


def render_result_card_html(call: dict) -> str:
    tone = call.get("tone") or "wait"
    analyzed = call.get("analyzed")
    if analyzed is None:
        analyzed = tone != "wait" and call.get("score") not in (None, "", "—")
    status_kind = call.get("status_kind") or ("done" if analyzed else "new")
    badge = status_pill_html(status_kind)
    title = html.escape(str(call.get("title") or "Дзвінок"))
    when = html.escape(str(call.get("time") or "—"))
    client = html.escape(str(call.get("client") or "—"))
    project = html.escape(str(call.get("project") or "—"))
    manager = html.escape(str(call.get("manager") or "—"))
    ctx_rows = call.get("ctx_rows") or []

    ctx_html = ""
    for row in ctx_rows:
        icon = html.escape(str(row.get("icon") or "•"))
        label = html.escape(str(row.get("label") or ""))
        value = html.escape(str(row.get("value") or ""))
        ok = bool(row.get("ok", True))
        check = "✓" if ok else ""
        ctx_html += (
            f'<div class="call-ctx-row"><span>{icon}</span>'
            f"<span>{label}: {value}</span>"
            f'<span class="check">{check}</span></div>'
        )
    if ctx_html:
        ctx_html = f'<div class="call-ctx">{ctx_html}</div>'

    score = call.get("score")
    try:
        score_num = f"{float(score):.0f}"
        # <80 → ATTENTION (mid), not aggressive error red
        display_tone = "ok" if float(score) >= 80 else "mid"
        score_block = (
            f'<div class="call-score-num">{html.escape(score_num)}'
            f'<span class="slash">/100</span></div>'
            f'<div class="badge {html.escape(display_tone)}">'
            f"{html.escape(str(call.get('result_badge') or score_result_label(display_tone)))}</div>"
        )
    except (TypeError, ValueError):
        score_block = (
            f'<div class="call-score-num">—'
            f'<span class="slash">/100</span></div>'
            f'<div class="badge wait">NOT ANALYZED</div>'
        )

    return f"""
            <div class="call-card">
              <div class="call-head">
                <div class="call-title">{title}</div>
                {badge}
              </div>
              <div class="call-meta">{html.escape(project)} · {html.escape(manager)} · ID {client}</div>
              <div class="call-meta">{when}</div>
              {ctx_html}
              <div class="call-score-row">{score_block}</div>
            </div>
            """


def avatar_initial(name: str) -> str:
    text = str(name or "").strip()
    return text[:1].upper() if text else "?"
