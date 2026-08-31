"""Точка входу Streamlit Cloud (Main file path)."""

from constants import CALL_TYPE_SHORT_90S
from vip_ui import render_call_entry_page

render_call_entry_page(CALL_TYPE_SHORT_90S)
