"""Завантаження vip_short_call_logs для аналітики."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from supabase_logger import get_supabase_client


def _flatten_row(row: dict) -> dict:
    debug = row.get("debug_data") or {}
    if isinstance(debug, str):
        try:
            debug = json.loads(debug)
        except Exception:
            debug = {}
    call = debug.get("call") if isinstance(debug, dict) else {}
    if not isinstance(call, dict):
        call = {}
    out = dict(row)
    out["project"] = call.get("project") or out.get("project") or ""
    out["ret_manager"] = call.get("ret_manager") or out.get("ret_manager") or ""
    out["tl_name"] = call.get("tl") or out.get("tl_name") or ""
    out["qa_manager"] = call.get("qa_manager") or out.get("qa_manager") or ""
    out["verdict"] = str(out.get("verdict") or "").lower()
    score = debug.get("score") if isinstance(debug, dict) else {}
    if not isinstance(score, dict):
        score = {}
    out["percent"] = out.get("percent") if out.get("percent") is not None else score.get("percent")
    out["total_score"] = (
        out.get("total_score") if out.get("total_score") is not None else score.get("total_score")
    )
    out["max_score"] = (
        out.get("max_score") if out.get("max_score") is not None else score.get("max_score")
    )
    out["rubric_call_type"] = (
        out.get("call_type")
        or score.get("call_type")
        or call.get("vip_call_type")
        or ""
    )
    if out.get("is_critical_fail") is None:
        out["is_critical_fail"] = bool(score.get("is_critical_fail"))
    else:
        out["is_critical_fail"] = bool(out.get("is_critical_fail"))
    return out


@st.cache_data(ttl=300, show_spinner=False)
def load_vip_logs() -> pd.DataFrame:
    client, err = get_supabase_client()
    if client is None:
        if err:
            st.caption(str(err))
        return pd.DataFrame()
    rows = []
    offset = 0
    try:
        while True:
            res = (
                client.table("vip_short_call_logs")
                .select("*")
                .range(offset, offset + 999)
                .execute()
            )
            chunk = res.data or []
            rows.extend(chunk)
            if len(chunk) < 1000:
                break
            offset += 1000
    except Exception as exc:
        st.caption(f"Не вдалось завантажити vip_short_call_logs: {exc}")
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()
    flat = [_flatten_row(row) for row in rows]
    df = pd.DataFrame(flat)
    df["call_date"] = pd.to_datetime(df["call_date"], errors="coerce")
    df["period_date"] = df["call_date"]
    df["is_green"] = df["verdict"].eq("green")
    df["is_red"] = df["verdict"].eq("red")
    df["percent"] = pd.to_numeric(df.get("percent"), errors="coerce")
    return df


def default_period(df: pd.DataFrame) -> tuple[date, date]:
    if df.empty or "period_date" not in df.columns:
        today = date.today()
        return today - timedelta(days=30), today
    period_series = df["period_date"].dropna()
    if period_series.empty:
        today = date.today()
        return today - timedelta(days=30), today
    date_min = period_series.min().date()
    date_max = max(period_series.max().date(), date.today())
    return date_min, date_max


def filter_frame(
    df: pd.DataFrame,
    d_from: date,
    d_to: date,
    project: str = "Всі",
) -> pd.DataFrame:
    out = df.copy()
    out = out[
        out["period_date"].notna()
        & (out["period_date"].dt.date >= d_from)
        & (out["period_date"].dt.date <= d_to)
    ]
    if project != "Всі":
        out = out[out["project"] == project]
    return out


def clear_cache() -> None:
    load_vip_logs.clear()
