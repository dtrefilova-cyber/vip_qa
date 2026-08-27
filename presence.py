"""Heartbeat активних користувачів VIP QA."""

from __future__ import annotations

import time
import uuid

import streamlit as st

from google_sheets import connect_google, load_active_users, upsert_user_presence
from utils import LOG_SHEET_ID

PRESENCE_PING_INTERVAL = 45
PRESENCE_ACTIVE_TTL = 180


def ensure_presence_session_id():
    if "presence_session_id" not in st.session_state:
        st.session_state.presence_session_id = uuid.uuid4().hex[:12]


def ping_presence(qa_manager, dept="", call_type="", force=False):
    if not qa_manager:
        return
    ensure_presence_session_id()
    now = time.time()
    interval = 30 if force else PRESENCE_PING_INTERVAL
    last_ping = st.session_state.get("_presence_last_ping", 0)
    if now - last_ping < interval:
        return
    try:
        google_client = connect_google()
        upsert_user_presence(
            google_client,
            LOG_SHEET_ID,
            st.session_state.presence_session_id,
            qa_manager,
            dept=dept or "",
            call_type=call_type or "",
        )
        st.session_state._presence_last_ping = now
    except Exception:
        pass


@st.cache_data(ttl=20, show_spinner=False)
def get_active_users_cached(ttl_seconds=PRESENCE_ACTIVE_TTL):
    try:
        google_client = connect_google()
        return load_active_users(google_client, LOG_SHEET_ID, ttl_seconds=ttl_seconds)
    except Exception:
        return []


def render_presence_monitor():
    if not st.session_state.get("presence_monitoring"):
        return
    if hasattr(st, "fragment"):

        @st.fragment(run_every=20)
        def _presence_panel():
            _render_presence_table()

        _presence_panel()
    else:
        _render_presence_table()


def start_presence_heartbeat(qa_manager, dept="", call_type=""):
    ping_presence(qa_manager, dept=dept, call_type=call_type)


def _render_presence_table():
    active_users = get_active_users_cached()
    st.markdown("**👥 Активні користувачі зараз**")
    st.caption(
        f"Онлайн = активність за останні {PRESENCE_ACTIVE_TTL // 60} хв. "
        "Список оновлюється автоматично кожні ~20 с."
    )
    if not active_users:
        st.info("Зараз нікого активного не видно.")
        return
    rows = []
    for user in active_users:
        context = " · ".join(
            part for part in [user.get("dept"), user.get("call_type")] if part
        )
        label = user.get("qa_manager") or "Невідомий QA"
        if context:
            label = f"{label} ({context})"
        rows.append(
            {
                "QA": label,
                "Остання активність": user.get("last_seen", ""),
                "Сек тому": user.get("age_seconds", ""),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)
