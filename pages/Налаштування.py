import streamlit as st

from chrome import setup_page
from presence import render_presence_monitor
from ui_theme import render_page_header
from utils import transcribe_audio_cached

qa_manager = setup_page("Налаштування", active="settings")
_ = qa_manager

render_page_header("Налаштування", "Службові інструменти AI Quality · VIP")

if st.session_state.pop("_clear_transcript_cache", False):
    transcribe_audio_cached.clear()
    st.success("Кеш транскрипцій очищено")

st.markdown(
    """
<div class="guide-note">
<strong>Тема:</strong> перемикач ☀ Light / 🌙 Dark у сайдбарі. Вибір зберігається під час сесії між усіма сторінками.
</div>
""",
    unsafe_allow_html=True,
)

c1, c2, c3 = st.columns(3)
with c1:
    if st.button("Скинути весь кеш", key="clear_all_cache"):
        st.cache_data.clear()
        st.success("Весь кеш очищено")
with c2:
    if st.button("Скинути кеш транскрипцій", key="clear_transcript_cache"):
        st.session_state["_clear_transcript_cache"] = True
        st.rerun()
with c3:
    st.toggle("Debug mode", value=False, key="debug_mode")

st.toggle(
    "Моніторинг активності",
    value=False,
    key="presence_monitoring",
    help="Показує, хто зараз працює в VIP QA (онлайн за останні 3 хв)",
)
render_presence_monitor()
