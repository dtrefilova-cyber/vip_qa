"""Спільний сайдбар AI Quality для multipage VIP-застосунку."""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from ui_theme import (
    NAV_ITEMS,
    QA_MANAGERS,
    avatar_initial,
    inject_app_css,
    render_theme_toggle,
    reset_stale_session,
    sync_select_state,
)

_SIDEBAR_TOGGLE_JS = """
<script>
(function() {
  const doc = window.parent.document;
  function sidebarExpanded() {
    const sidebar = doc.querySelector('[data-testid="stSidebar"]');
    return sidebar && sidebar.getAttribute('aria-expanded') === 'true';
  }
  function toggleSidebar() {
    if (sidebarExpanded()) {
      const wrap = doc.querySelector('[data-testid="stSidebarCollapseButton"]');
      const collapse = wrap && (wrap.querySelector('button') || wrap);
      if (collapse) { collapse.click(); return; }
    }
    const expand = doc.querySelector('[data-testid="stExpandSidebarButton"]');
    if (expand) { expand.click(); return; }
    const fallback = doc.querySelector('[data-testid="stSidebarCollapseButton"] button');
    if (fallback) fallback.click();
  }
  let btn = doc.getElementById('aiq-sidebar-toggle');
  if (!btn) {
    btn = doc.createElement('button');
    btn.id = 'aiq-sidebar-toggle';
    btn.type = 'button';
    btn.setAttribute('aria-label', 'Показати або сховати меню');
    btn.title = 'Меню';
    btn.textContent = '☰';
    doc.body.appendChild(btn);
  }
  btn.onclick = toggleSidebar;
})();
</script>
"""


def home_page_path() -> str:
    """Файл головної сторінки = той скрипт, який реально запустив Streamlit.

    Cloud у цьому репо стартує з streamlit_app.py, локально часто з app.py.
    st.page_link('app.py') падає, якщо main file path інший.
    """
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import (
            get_script_run_ctx,
        )

        ctx = get_script_run_ctx()
        if ctx and getattr(ctx, "main_script_path", None):
            name = Path(ctx.main_script_path).name
            if name:
                return name
    except Exception:
        pass
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        if ctx and getattr(ctx, "main_script_path", None):
            name = Path(ctx.main_script_path).name
            if name:
                return name
    except Exception:
        pass
    return "streamlit_app.py"


def _page_link_target(item: dict) -> str:
    page = str(item.get("page") or "")
    if item.get("id") == "short" or page in {"__home__", "app.py", "streamlit_app.py"}:
        return home_page_path()
    return page


def setup_page(title: str, *, active: str) -> str:
    st.set_page_config(
        page_title=f"VIP QA — {title}",
        page_icon="🎧",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    reset_stale_session()
    inject_app_css()
    components.html(_SIDEBAR_TOGGLE_JS, height=1, width=1)
    qa_manager = render_sidebar(active=active)
    render_supabase_connection_warning()
    return qa_manager


def render_supabase_connection_warning() -> bool:
    from supabase_logger import SUPABASE_UNAVAILABLE_MESSAGE, get_supabase_health

    ok, err = get_supabase_health()
    if ok:
        return True
    st.warning(SUPABASE_UNAVAILABLE_MESSAGE)
    if err:
        st.caption(str(err))
    return False


def render_sidebar(*, active: str) -> str:
    with st.sidebar:
        st.markdown(
            '<div class="qa-logo"><div class="ico">🎧</div>AI Quality VIP</div>',
            unsafe_allow_html=True,
        )
        render_theme_toggle()
        for item in NAV_ITEMS:
            label = f"{item['icon']} {item['label']}"
            st.page_link(_page_link_target(item), label=label, use_container_width=True)
        st.caption("QA менеджер")
        sync_select_state("qa_manager_global", QA_MANAGERS)
        qa_manager = st.selectbox(
            "QA менеджер",
            QA_MANAGERS,
            key="qa_manager_global",
            label_visibility="collapsed",
        )
        initial = html.escape(avatar_initial(qa_manager))
        st.markdown(
            f'<div class="qa-profile"><div class="qa-avatar">{initial}</div>'
            f'<div><div class="name">{html.escape(str(qa_manager))}</div>'
            f'<div class="role">QA менеджер · VIP</div></div></div>',
            unsafe_allow_html=True,
        )
    return str(qa_manager)
