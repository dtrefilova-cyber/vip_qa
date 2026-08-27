"""Лічильники та архів проаналізованих VIP-дзвінків (vip_short_call_logs)."""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

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


def _call_meta(row: dict) -> dict:
    debug = row.get("debug_data") or {}
    if isinstance(debug, str):
        try:
            import json

            debug = json.loads(debug)
        except Exception:
            debug = {}
    call = debug.get("call") if isinstance(debug, dict) else {}
    return call if isinstance(call, dict) else {}


@st.cache_data(ttl=120, show_spinner=False)
def fetch_vip_summary(check_date_iso: str, today_iso: str) -> tuple[dict, int, str | None]:
    client, err = get_supabase_client()
    if client is None:
        return {"total": 0, "green": 0, "red": 0}, 0, err
    try:
        day_res = (
            client.table("vip_short_call_logs")
            .select("verdict")
            .eq("call_date", check_date_iso)
            .execute()
        )
        rows = day_res.data or []
        total = len(rows)
        green = sum(1 for r in rows if str(r.get("verdict") or "").lower() == "green")
        red = sum(1 for r in rows if str(r.get("verdict") or "").lower() == "red")
        today_res = (
            client.table("vip_short_call_logs")
            .select("id")
            .eq("call_date", today_iso)
            .execute()
        )
        today_count = len(today_res.data or [])
        return {"total": total, "green": green, "red": red}, today_count, None
    except Exception as exc:
        return {"total": 0, "green": 0, "red": 0}, 0, str(exc)


@st.cache_data(ttl=120, show_spinner=False)
def fetch_vip_page(check_date_iso: str, offset: int, limit: int) -> tuple[list[dict], str | None]:
    client, err = get_supabase_client()
    if client is None:
        return [], err
    try:
        res = (
            client.table("vip_short_call_logs")
            .select("*")
            .eq("call_date", check_date_iso)
            .order("id", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return list(res.data or []), None
    except Exception as exc:
        return [], str(exc)


def archive_page_count(total: int, page_size: int = ARCHIVE_PAGE_SIZE) -> int:
    if total <= 0:
        return 1
    return (total + page_size - 1) // page_size


def clamp_archive_page(page: int, n_pages: int) -> int:
    return max(1, min(int(page or 1), n_pages))


def _pct(part: int, total: int) -> str:
    if not total:
        return "0.0%"
    return f"{part / total * 100:.1f}%"


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
    verdict = str(row.get("verdict") or "").lower()
    tone = "ok" if verdict == "green" else ("bad" if verdict == "red" else "wait")
    reasons = row.get("verdict_reasons") or []
    reason_text = reasons[0] if reasons else ""
    ctx_rows = []
    if reason_text:
        ctx_rows.append({"icon": "📌", "label": "Вердикт", "value": str(reason_text), "ok": verdict == "green"})
    return {
        "id": row.get("id"),
        "call_type": "Короткий",
        "title": f"Дзвінок #{int(index + 1):04d}",
        "status": "АНАЛІЗОВАНО",
        "tone": tone,
        "analyzed": True,
        "score": 100 if verdict == "green" else (0 if verdict == "red" else None),
        "time": format_archive_time(row.get("call_date")),
        "client": row.get("client_id") or "—",
        "project": meta.get("project") or "—",
        "manager": meta.get("ret_manager") or "—",
        "audio_url": row.get("call_url") or "",
        "result_badge": "GREEN" if verdict == "green" else ("RED" if verdict == "red" else "—"),
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
    green = int(counts.get("green") or 0)
    red = int(counts.get("red") or 0)
    date_label = check_date.strftime("%d.%m.%Y") if hasattr(check_date, "strftime") else "—"
    today_label = today_kyiv().strftime("%d.%m.%Y")

    render_stat_cards(
        [
            ("📞", "primary", str(total), "Всього дзвінків", date_label),
            ("🟢", "green", str(green), "GREEN", _pct(green, total)),
            ("🔴", "rose", str(red), "RED", _pct(red, total)),
            ("★", "primary", str(today_count), "Опрацьовано сьогодні", today_label),
            ("🎧", "primary", call_type, "Тип дзвінка", "VIP Short"),
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

    page_key, day_key = _archive_keys(slug)
    if st.session_state.get(day_key) != check_iso:
        st.session_state[page_key] = 1
        st.session_state[day_key] = check_iso

    summary, _, summary_err = fetch_vip_summary(check_iso, today_kyiv().isoformat())
    archive_total = int(summary.get("total") or 0)
    n_pages = archive_page_count(archive_total)
    page = clamp_archive_page(st.session_state.get(page_key, 1), n_pages)
    st.session_state[page_key] = page

    offset = (page - 1) * ARCHIVE_PAGE_SIZE
    rows, archive_error = fetch_vip_page(check_iso, offset, ARCHIVE_PAGE_SIZE)
    cards = [row_to_archive_card(row, offset + idx) for idx, row in enumerate(rows)]

    st.markdown("### Архів")
    day_label = check_date.strftime("%d.%m.%Y") if hasattr(check_date, "strftime") else check_iso
    green = int(summary.get("green") or 0)
    red = int(summary.get("red") or 0)
    st.markdown(
        f"""
        <div class="archive-summary">
          <div>
            <h4>Аналізи за {day_label}</h4>
            <p>{archive_total} дзвінків · {green} GREEN · {red} RED</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Усі VIP-аналізи за {day_label}. На сторінці — три останні, далі можна гортати.")

    err = archive_error or summary_err
    if err:
        ok, _ = get_supabase_health()
        if ok:
            st.warning(SUPABASE_UNAVAILABLE_MESSAGE)
        st.caption(f"Архів vip_short_call_logs: {err}")

    if not cards:
        st.caption(f"За {day_label} ще немає проаналізованих дзвінків.")
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
    summary, today_count, err = fetch_vip_summary(check_iso, today_iso)
    render_kpi_row(
        call_type=call_type,
        check_date=check_date,
        counts=summary,
        today_count=today_count,
        counts_error=err,
    )
