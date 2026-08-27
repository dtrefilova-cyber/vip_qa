"""Спільна ініціалізація сторінки внесення VIP-дзвінків (аналог retention_ui.py)."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from app_vip import run_call_type_page
from chrome import setup_page
from constants import VIP_SHORT_SHEET_ID
from google_sheets import connect_google, load_vip_short_managers
from presence import start_presence_heartbeat
from utils import transcribe_audio_cached

CALL_PAGE_META = {
    "Короткий": {
        "active": "short",
        "title": "Короткі дзвінки",
        "heading": "Короткі дзвінки",
        "caption": "Завантаження та аналіз коротких дзвінків VIP",
    },
}


@st.cache_data(ttl=600, show_spinner=False)
def load_vip_managers_cached():
    try:
        gclient = connect_google()
        return load_vip_short_managers(gclient, VIP_SHORT_SHEET_ID)
    except Exception as e:
        st.error(f"Не вдалось завантажити менеджерів VIP: {e}")
        return []


def load_managers_context() -> tuple[list, list[str], dict]:
    managers_config = load_vip_managers_cached()
    projects_list = sorted({item.get("project") for item in managers_config if item.get("project")})
    if not managers_config:
        st.warning(
            "Список VIP-менеджерів не завантажився з таблиці MANAGERS. "
            "Перевірте, що аркуш заповнений і доступ надано сервісному акаунту."
        )
    return managers_config, projects_list, {}


def render_call_entry_page(call_type: str) -> None:
    meta = CALL_PAGE_META[call_type]
    qa_manager = setup_page(meta["title"], active=meta["active"])

    from ui_theme import render_page_header

    head_l, head_r = st.columns([3.2, 1.0], vertical_alignment="center")
    with head_l:
        render_page_header(meta["heading"], meta["caption"])
    with head_r:
        check_date = st.date_input(
            "Дата перевірки",
            datetime.today(),
            format="DD.MM.YYYY",
            key=f"check_date_{meta['active']}",
        )

    if st.session_state.pop("_clear_transcript_cache", False):
        transcribe_audio_cached.clear()
        st.success("Кеш транскрипцій очищено")

    managers_config, projects_list, _ = load_managers_context()

    run_call_type_page(
        call_type,
        check_date,
        qa_manager,
        managers_config,
        projects_list,
        "VIP",
    )

    start_presence_heartbeat(
        qa_manager,
        dept="VIP",
        call_type=call_type,
    )
