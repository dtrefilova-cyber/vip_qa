"""Лічильники та архів проаналізованих VIP-дзвінків (vip_short_call_logs)."""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from constants import (
    CALL_TYPE_FRIENDLY,
    CALL_TYPE_KEY_FRIENDLY,
    CALL_TYPE_KEY_SHORT,
    CALL_TYPE_MAX_SCORE,
    CALL_TYPE_SHORT_90S,
    resolve_call_type_key,
)
from core.vip_scoring_common import CRITERION_LABELS
from supabase_logger import SUPABASE_UNAVAILABLE_MESSAGE, get_supabase_client, get_supabase_health

ARCHIVE_PAGE_SIZE = 3


def today_kyiv() -> date:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Europe/Kyiv")).date()
    except Exception:
        return date.today()


def iso_check_date(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value).strip()
    if len(text) == 10 and text[2] == "." and text[5] == ".":
        try:
            day, month, year = text.split(".")
            return f"{year}-{month}-{day}"
        except ValueError:
            return None
    if len(text) == 10 and text[4] == "-":
        return text
    return None


def _parse_debug(row: dict) -> dict:
    debug = row.get("debug_data") or {}
    if isinstance(debug, str):
        try:
            import json

            debug = json.loads(debug)
        except Exception:
            debug = {}
    return debug if isinstance(debug, dict) else {}


def _call_meta(row: dict) -> dict:
    debug = _parse_debug(row)
    call = debug.get("call") if isinstance(debug, dict) else {}
    return call if isinstance(call, dict) else {}


def _row_type_key(row: dict) -> str | None:
    meta = _call_meta(row)
    debug = _parse_debug(row)
    score = debug.get("score") if isinstance(debug, dict) else {}
    if not isinstance(score, dict):
        score = {}
    raw = (
        row.get("call_type")
        or score.get("call_type")
        or meta.get("vip_call_type")
        or ""
    )
    key = resolve_call_type_key(str(raw))
    if key:
        return key
    # Legacy GREEN/RED rows → short
    verdict = str(row.get("verdict") or "").lower()
    if verdict in {"green", "red"}:
        return CALL_TYPE_KEY_SHORT
    return None


def _filter_rows(rows: list[dict], type_key: str | None) -> list[dict]:
    if not type_key:
        return list(rows)
    wanted = resolve_call_type_key(type_key) or type_key
    out = []
    for row in rows:
        rk = _row_type_key(row)
        if wanted == CALL_TYPE_KEY_SHORT:
            # short page: new short + legacy without type
            if rk in {None, CALL_TYPE_KEY_SHORT}:
                out.append(row)
        elif rk == wanted:
            out.append(row)
    return out


def _score_blob(row: dict) -> dict:
    debug = _parse_debug(row)
    score = debug.get("score") if isinstance(debug, dict) else {}
    return score if isinstance(score, dict) else {}


def _worst_criterion(score: dict, row: dict) -> str | None:
    criteria = score.get("criteria") or row.get("criteria_scores") or []
    if isinstance(criteria, str):
        try:
            import json

            criteria = json.loads(criteria)
        except Exception:
            criteria = []
    if not isinstance(criteria, list) or not criteria:
        return None
    worst = None
    worst_ratio = 2.0
    for item in criteria:
        if not isinstance(item, dict):
            continue
        try:
            pts = float(item.get("points") or 0)
            mx = float(item.get("max_points") or 0)
        except (TypeError, ValueError):
            continue
        if mx <= 0:
            continue
        ratio = pts / mx
        if ratio < worst_ratio:
            worst_ratio = ratio
            label = item.get("label") or CRITERION_LABELS.get(item.get("key"), item.get("key"))
            reasons = [str(r).strip() for r in (item.get("reasons") or []) if str(r).strip()]
            reason = reasons[0] if reasons else ""
            worst = f"{label}" + (f" — {reason}" if reason else f" ({pts:g}/{mx:g})")
    return worst


@st.cache_data(ttl=120, show_spinner=False)
def fetch_vip_day_rows(check_date_iso: str) -> tuple[list[dict], str | None]:
    client, err = get_supabase_client()
    if client is None:
        return [], err
    try:
        day_res = (
            client.table("vip_short_call_logs")
            .select("*")
            .eq("call_date", check_date_iso)
            .order("id", desc=True)
            .execute()
        )
        return list(day_res.data or []), None
    except Exception as exc:
        return [], str(exc)


def fetch_vip_summary(
    check_date_iso: str,
    today_iso: str,
    *,
    type_key: str | None = None,
) -> tuple[dict, int, str | None]:
    rows, err = fetch_vip_day_rows(check_date_iso)
    empty = {
        "total": 0,
        "avg_percent": None,
        "avg_score": None,
        "max_score": None,
        "high": 0,
        "mid": 0,
        "low": 0,
        "critical": 0,
    }
    if err and not rows:
        return empty, 0, err
    rows = _filter_rows(rows, type_key)
    total = len(rows)
    percents: list[float] = []
    scores: list[float] = []
    high = mid = low = critical = 0
    type_max = CALL_TYPE_MAX_SCORE.get(type_key or "", None)
    for row in rows:
        pct = row.get("percent")
        is_crit = row.get("is_critical_fail")
        score = _score_blob(row)
        if is_crit is None:
            is_crit = score.get("is_critical_fail")
        if pct is None:
            pct = score.get("percent")
        raw_score = row.get("total_score")
        if raw_score is None:
            raw_score = score.get("total_score")
        row_max = row.get("max_score")
        if row_max is None:
            row_max = score.get("max_score")
        if row_max is not None:
            try:
                type_max = float(row_max)
            except (TypeError, ValueError):
                pass
        if is_crit:
            critical += 1
        pct_f = None
        if pct is not None:
            try:
                pct_f = float(pct)
            except (TypeError, ValueError):
                pct_f = None
        score_f = None
        if raw_score is not None:
            try:
                score_f = float(raw_score)
            except (TypeError, ValueError):
                score_f = None
        if pct_f is None and score_f is None:
            verdict = str(row.get("verdict") or "").lower()
            if verdict == "green":
                pct_f = 100.0
                if type_max is not None:
                    score_f = float(type_max)
            elif verdict == "red":
                pct_f = 0.0
                score_f = 0.0
        if score_f is None and pct_f is not None and type_max is not None:
            score_f = round(pct_f / 100.0 * float(type_max), 1)
        if pct_f is None and score_f is not None and type_max:
            pct_f = round(score_f / float(type_max) * 100, 1)
        if pct_f is not None:
            percents.append(pct_f)
            if is_crit or pct_f < 50:
                low += 1
            elif pct_f >= 80:
                high += 1
            else:
                mid += 1
        if score_f is not None:
            scores.append(score_f)
    avg_percent = round(sum(percents) / len(percents), 1) if percents else None
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    today_rows, today_err = fetch_vip_day_rows(today_iso)
    today_rows = _filter_rows(today_rows, type_key)
    today_count = len(today_rows)
    return {
        "total": total,
        "avg_percent": avg_percent,
        "avg_score": avg_score,
        "max_score": type_max,
        "high": high,
        "mid": mid,
        "low": low,
        "critical": critical,
    }, today_count, err or today_err


def fetch_vip_page(
    check_date_iso: str,
    offset: int,
    limit: int,
    *,
    type_key: str | None = None,
) -> tuple[list[dict], str | None]:
    rows, err = fetch_vip_day_rows(check_date_iso)
    if err and not rows:
        return [], err
    rows = _filter_rows(rows, type_key)
    return rows[offset : offset + limit], err


def archive_page_count(total: int, page_size: int = ARCHIVE_PAGE_SIZE) -> int:
    if total <= 0:
        return 1
    return (total + page_size - 1) // page_size


def clamp_archive_page(page: int, n_pages: int) -> int:
    return max(1, min(int(page or 1), n_pages))


def format_archive_time(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    text = str(value).strip().replace("Z", "")
    if len(text) >= 10 and text[4] == "-":
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
        except ValueError:
            pass
    if len(text) >= 10 and text[2] == ".":
        return text[:10]
    return text


def row_to_archive_card(row: dict, index: int) -> dict:
    meta = _call_meta(row)
    score = _score_blob(row)

    total_score = row.get("total_score") if row.get("total_score") is not None else score.get("total_score")
    max_score = row.get("max_score") if row.get("max_score") is not None else score.get("max_score")
    percent = row.get("percent") if row.get("percent") is not None else score.get("percent")
    is_critical = bool(
        row.get("is_critical_fail")
        if row.get("is_critical_fail") is not None
        else score.get("is_critical_fail")
    )
    type_key = _row_type_key(row)
    call_type_label = (
        CALL_TYPE_FRIENDLY
        if type_key == CALL_TYPE_KEY_FRIENDLY
        else CALL_TYPE_SHORT_90S
        if type_key == CALL_TYPE_KEY_SHORT
        else (row.get("call_type") or score.get("call_type") or meta.get("vip_call_type") or "VIP")
    )

    if percent is not None:
        try:
            pct_f = float(percent)
            tone = "ok" if pct_f >= 80 else ("mid" if pct_f >= 50 else "bad")
            if is_critical:
                tone = "bad"
            badge = f"{float(total_score):g}/{float(max_score):g} ({pct_f:g}%)"
            display_score = pct_f
        except (TypeError, ValueError):
            tone, badge, display_score = "wait", "—", None
    else:
        verdict = str(row.get("verdict") or "").lower()
        tone = "ok" if verdict == "green" else ("bad" if verdict == "red" else "wait")
        badge = "GREEN" if verdict == "green" else ("RED" if verdict == "red" else "—")
        display_score = 100 if verdict == "green" else (0 if verdict == "red" else None)

    ctx_rows = []
    if is_critical:
        crit = "; ".join(score.get("critical_reasons") or row.get("verdict_reasons") or [])
        ctx_rows.append({"icon": "⛔", "label": "Критична помилка", "value": crit or "так", "ok": False})
    else:
        worst = _worst_criterion(score, row)
        if worst:
            ctx_rows.append({"icon": "📌", "label": "Найслабший критерій", "value": worst, "ok": False})
        elif badge and badge not in {"GREEN", "RED", "—"}:
            ctx_rows.append({"icon": "📌", "label": "Бал", "value": badge, "ok": tone == "ok"})

    return {
        "id": row.get("id"),
        "call_type": call_type_label,
        "title": f"Дзвінок #{int(index + 1):04d}",
        "status": "АНАЛІЗОВАНО",
        "tone": tone,
        "analyzed": True,
        "score": display_score,
        "time": format_archive_time(row.get("call_date")),
        "client": row.get("client_id") or "—",
        "project": meta.get("project") or "—",
        "manager": meta.get("ret_manager") or "—",
        "audio_url": row.get("call_url") or "",
        "result_badge": badge,
        "ctx_rows": ctx_rows,
        "url": row.get("call_url") or "",
        "call_date": row.get("call_date"),
    }


def _archive_keys(slug: str) -> tuple[str, str]:
    return f"vip_archive_page_{slug}", f"vip_archive_day_{slug}"


def render_kpi_row(
    *,
    call_type: str,
    check_date,
    counts: dict,
    today_count: int,
    counts_error: str | None,
) -> None:
    from ui_theme import render_stat_cards

    total = int(counts.get("total") or 0)
    avg_score = counts.get("avg_score")
    max_score = counts.get("max_score")
    if max_score is None:
        max_score = CALL_TYPE_MAX_SCORE.get(resolve_call_type_key(call_type) or call_type)
    date_label = check_date.strftime("%d.%m.%Y") if hasattr(check_date, "strftime") else "—"
    today_label = today_kyiv().strftime("%d.%m.%Y")
    if avg_score is not None and max_score is not None:
        avg_label = f"{avg_score:g} / {float(max_score):g}"
        avg_sub = "середній бал"
    elif avg_score is not None:
        avg_label = f"{avg_score:g}"
        avg_sub = "середній бал"
    else:
        avg_label = "—"
        avg_sub = "середній бал"
    render_stat_cards(
        [
            ("📞", "primary", str(total), "Всього дзвінків", date_label),
            ("★", "green", avg_label, "Середній бал", avg_sub),
            ("★", "primary", str(today_count), "Опрацьовано сьогодні", today_label),
        ]
    )
    if counts_error:
        ok, _ = get_supabase_health()
        if ok:
            st.warning(SUPABASE_UNAVAILABLE_MESSAGE)
        st.caption(f"Лічильники vip_short_call_logs: {counts_error}")
    st.write("")


def _render_archive_pager(*, page: int, n_pages: int, total: int, page_size: int, page_key: str) -> None:
    start = (page - 1) * page_size
    shown_from = start + 1 if total else 0
    shown_to = min(start + page_size, total)
    info_col, nav_col = st.columns([2.2, 3.2], vertical_alignment="center")
    with info_col:
        st.markdown(
            f'<div class="pg-info">Показано {shown_from}–{shown_to} з {total} дзвінків</div>',
            unsafe_allow_html=True,
        )
    if n_pages <= 1:
        return
    with nav_col:
        window = min(n_pages, 7)
        half = window // 2
        first = max(1, page - half)
        last = min(n_pages, first + window - 1)
        first = max(1, last - window + 1)
        numbers = list(range(first, last + 1))
        cols = st.columns(len(numbers) + 2)
        if cols[0].button("‹", key=f"{page_key}_prev", disabled=page <= 1):
            st.session_state[page_key] = page - 1
            st.rerun()
        for col, num in zip(cols[1:-1], numbers):
            with col:
                if st.button(
                    str(num),
                    key=f"{page_key}_pg_{num}",
                    type="primary" if num == page else "secondary",
                ):
                    st.session_state[page_key] = num
                    st.rerun()
        if cols[-1].button("›", key=f"{page_key}_next", disabled=page >= n_pages):
            st.session_state[page_key] = page + 1
            st.rerun()


def render_archive_section(*, call_type: str, slug: str, check_date) -> None:
    from ui_theme import render_result_card_html

    check_iso = iso_check_date(check_date)
    if not check_iso:
        return

    type_key = resolve_call_type_key(call_type)
    page_key, day_key = _archive_keys(slug)
    day_stamp = f"{check_iso}:{type_key or 'all'}"
    if st.session_state.get(day_key) != day_stamp:
        st.session_state[page_key] = 1
        st.session_state[day_key] = day_stamp

    summary, _, summary_err = fetch_vip_summary(
        check_iso, today_kyiv().isoformat(), type_key=type_key
    )
    archive_total = int(summary.get("total") or 0)
    n_pages = archive_page_count(archive_total)
    page = clamp_archive_page(st.session_state.get(page_key, 1), n_pages)
    st.session_state[page_key] = page

    offset = (page - 1) * ARCHIVE_PAGE_SIZE
    rows, archive_error = fetch_vip_page(
        check_iso, offset, ARCHIVE_PAGE_SIZE, type_key=type_key
    )
    cards = [row_to_archive_card(row, offset + idx) for idx, row in enumerate(rows)]

    st.markdown("### Архів")
    day_label = check_date.strftime("%d.%m.%Y") if hasattr(check_date, "strftime") else check_iso
    avg = summary.get("avg_score")
    max_score = summary.get("max_score")
    if avg is not None and max_score is not None:
        avg_txt = f"середній бал {avg:g}/{float(max_score):g}"
    elif avg is not None:
        avg_txt = f"середній бал {avg:g}"
    else:
        avg_txt = "—"
    type_note = call_type
    st.markdown(
        f"""
        <div class="archive-summary">
          <div>
            <h4>Аналізи за {day_label}</h4>
            <p>{archive_total} дзвінків · {avg_txt} · {type_note}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Архів «{type_note}» за {day_label}. На сторінці — три останні, далі можна гортати.")

    err = archive_error or summary_err
    if err:
        ok, _ = get_supabase_health()
        if ok:
            st.warning(SUPABASE_UNAVAILABLE_MESSAGE)
        st.caption(f"Архів vip_short_call_logs: {err}")

    if not cards:
        st.caption(f"За {day_label} ще немає проаналізованих дзвінків цього типу.")
        return

    cols = st.columns(3)
    for col, card in zip(cols, cards[:ARCHIVE_PAGE_SIZE]):
        with col:
            card = dict(card)
            card["status_kind"] = "done"
            st.markdown(render_result_card_html(card), unsafe_allow_html=True)
            if card.get("audio_url"):
                st.link_button("▶", card["audio_url"], use_container_width=True)

    if archive_total:
        _render_archive_pager(
            page=page,
            n_pages=n_pages,
            total=archive_total,
            page_size=ARCHIVE_PAGE_SIZE,
            page_key=page_key,
        )


def render_call_type_stats(call_type: str, slug: str, check_date) -> None:
    _ = slug
    check_iso = iso_check_date(check_date) or ""
    today_iso = today_kyiv().isoformat()
    type_key = resolve_call_type_key(call_type)
    summary, today_count, err = fetch_vip_summary(check_iso, today_iso, type_key=type_key)
    render_kpi_row(
        call_type=call_type,
        check_date=check_date,
        counts=summary,
        today_count=today_count,
        counts_error=err,
    )
