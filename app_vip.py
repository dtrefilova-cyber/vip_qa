"""VIP — головна сторінка з картками (Короткий 90 сек / VIP Friendly)."""

from __future__ import annotations

import json as _json

import streamlit as st

from constants import CALL_TYPE_FRIENDLY, CALL_TYPE_SHORT_90S, VIP_SHORT_SHEET_ID
from core.vip_friendly_scoring import score_vip_friendly_call
from core.vip_short_scoring import score_vip_short_call
from google_sheets import (
    append_vip_short_result,
    connect_google,
    format_vip_score_comment_for_sheet,
)
from supabase_logger import log_vip_short_call_to_supabase
from upload_cards import (
    GRID_COLUMNS,
    _keys,
    _slug,
    card_rows,
    collect_card_call,
    ensure_card_state,
    handle_add_card,
    queue_all_ready,
    render_add_calls_button,
    render_upload_toolbar,
    render_vip_card,
)
from utils import (
    ANALYSIS_CACHE_VERSION,
    OPENAI_ANALYSIS_MODEL,
    OPENAI_MAX_OUTPUT_TOKENS,
    _load_persisted_cleaned_transcript,
    _save_persisted_cleaned_transcript,
    _transcript_cache_key,
    apply_replacements,
    clean_transcript_cached,
    client,
    init_call_results_state,
    merge_short_fragments,
    render_analysis_run_summary,
    set_analysis_run_summary,
    store_analysis_failure,
    transcribe_call_audio,
)
from vip_archive import render_archive_section, render_call_type_stats
from vip_short_ai_assistant import (
    VIP_FRIENDLY_FACTS_CACHE_TAG,
    VIP_SHORT_FACTS_CACHE_TAG,
    extract_vip_friendly_facts,
    extract_vip_short_90s_facts,
)


def _facts_cache_key(tag, dialogue, qa_comment, important_note, cache_version, extra=""):
    payload = "|".join(
        [tag, cache_version, qa_comment or "", important_note or "", extra or "", dialogue or ""]
    )
    return _transcript_cache_key(payload, cache_version, "", "", False)


@st.cache_data(ttl=172800, show_spinner=False)
def analyze_vip_short_90s_cached(url, call_date, dialogue, qa_comment, important_note, cache_version):
    _ = (url, call_date)
    cache_key = _facts_cache_key(
        VIP_SHORT_FACTS_CACHE_TAG, dialogue, qa_comment, important_note, cache_version
    )
    persisted = _load_persisted_cleaned_transcript(cache_key)
    if persisted is not None:
        try:
            return _json.loads(persisted)
        except Exception:
            pass
    facts = extract_vip_short_90s_facts(
        client,
        OPENAI_ANALYSIS_MODEL,
        dialogue,
        qa_comment,
        important_note,
        OPENAI_MAX_OUTPUT_TOKENS,
    )
    try:
        _save_persisted_cleaned_transcript(cache_key, _json.dumps(facts, ensure_ascii=False))
    except Exception:
        pass
    return facts


@st.cache_data(ttl=172800, show_spinner=False)
def analyze_vip_friendly_cached(
    url,
    call_date,
    dialogue,
    qa_comment,
    important_note,
    cache_version,
    client_is_military,
    betking_x2_applicable,
):
    _ = (url, call_date)
    extra = f"mil={client_is_military}|bk={betking_x2_applicable}"
    cache_key = _facts_cache_key(
        VIP_FRIENDLY_FACTS_CACHE_TAG,
        dialogue,
        qa_comment,
        important_note,
        cache_version,
        extra,
    )
    persisted = _load_persisted_cleaned_transcript(cache_key)
    if persisted is not None:
        try:
            return _json.loads(persisted)
        except Exception:
            pass
    facts = extract_vip_friendly_facts(
        client,
        OPENAI_ANALYSIS_MODEL,
        dialogue,
        qa_comment,
        important_note,
        OPENAI_MAX_OUTPUT_TOKENS,
        client_is_military=client_is_military,
        betking_x2_applicable=betking_x2_applicable,
    )
    try:
        _save_persisted_cleaned_transcript(cache_key, _json.dumps(facts, ensure_ascii=False))
    except Exception:
        pass
    return facts


def render_score_badge(verdict_data: dict) -> None:
    label = verdict_data.get("score_label") or "—"
    if verdict_data.get("is_critical_fail"):
        reasons = "; ".join(verdict_data.get("critical_reasons") or []) or "критична помилка"
        st.error(f"Критична помилка: {reasons}. Бал {label}")
    else:
        st.success(f"Бал: {label}")

    for item in verdict_data.get("criteria") or []:
        label = item.get("label") or item.get("key") or "criterion"
        pts = item.get("points")
        mx = item.get("max_points")
        st.write(f"**{label}:** {pts:g} / {mx:g}")
        for reason in item.get("reasons") or []:
            st.caption(f"— {reason}")

    if verdict_data.get("supabase_error"):
        st.error(f"Supabase insert error: {verdict_data['supabase_error']}")
    if verdict_data.get("sheet_error"):
        st.error(f"Google Sheets write error: {verdict_data['sheet_error']}")
    if verdict_data.get("analysis_error"):
        st.error(verdict_data["analysis_error"])


# legacy name
render_verdict_badge = render_score_badge


def _write_result_to_sheet(call, verdict_data):
    try:
        gclient = connect_google()
        row_data = {
            "project": call.get("project", ""),
            "tl": call.get("tl", ""),
            "manager": call.get("ret_manager", ""),
            "client_id": call.get("client_id", ""),
            "call_date": call.get("call_date", ""),
            "call_type": call.get("vip_call_type", ""),
            "total_score": verdict_data.get("total_score"),
            "max_score": verdict_data.get("max_score"),
            "percent": verdict_data.get("percent"),
            "is_critical_fail": bool(verdict_data.get("is_critical_fail")),
            "critical_reasons": "; ".join(verdict_data.get("critical_reasons") or []),
            "criteria_scores": _json.dumps(verdict_data.get("criteria") or [], ensure_ascii=False),
            "result": verdict_data.get("score_label") or "scored",
            "comment": format_vip_score_comment_for_sheet(verdict_data),
        }
        res = append_vip_short_result(gclient, VIP_SHORT_SHEET_ID, row_data)
        if res is not True:
            return str(res)
    except Exception as e:
        return str(e)
    return ""


def _analyze_single_call(i, call, results_state):
    try:
        with st.spinner(f"Аналіз VIP-дзвінка {i + 1}..."):
            raw_transcript, _, _, transcribe_error, timed_transcript = transcribe_call_audio(call)
            if not raw_transcript:
                store_analysis_failure(
                    results_state,
                    i,
                    transcribe_error or "Транскрипт порожній.",
                    client_id=call.get("client_id", ""),
                )
                return False

            raw_transcript = apply_replacements(raw_transcript, {})
            raw_transcript = merge_short_fragments(raw_transcript)
            timed_transcript = apply_replacements(timed_transcript or raw_transcript, {})
            timed_transcript = merge_short_fragments(timed_transcript)
            transcript = clean_transcript_cached(
                raw_transcript,
                ANALYSIS_CACHE_VERSION,
                manager_name="",
                project_name="",
            )
            timed_for_gpt = clean_transcript_cached(
                timed_transcript,
                f"{ANALYSIS_CACHE_VERSION}-timed",
                manager_name="",
                project_name="",
            )

            selected = str(call.get("vip_call_type") or CALL_TYPE_SHORT_90S)
            if selected == CALL_TYPE_FRIENDLY:
                facts = analyze_vip_friendly_cached(
                    call.get("url", ""),
                    call.get("call_date", ""),
                    timed_for_gpt,
                    call.get("qa_comment", ""),
                    call.get("important_note", ""),
                    ANALYSIS_CACHE_VERSION,
                    bool(call.get("client_is_military")),
                    bool(call.get("betking_x2_applicable")),
                )
                verdict_data = score_vip_friendly_call(facts, call, transcript)
            else:
                facts = analyze_vip_short_90s_cached(
                    call.get("url", ""),
                    call.get("call_date", ""),
                    timed_for_gpt,
                    call.get("qa_comment", ""),
                    call.get("important_note", ""),
                    ANALYSIS_CACHE_VERSION,
                )
                verdict_data = score_vip_short_call(facts, call, transcript)

            supabase_error = ""
            sheet_error = ""

            try:
                supabase_ok = log_vip_short_call_to_supabase(
                    call,
                    facts,
                    verdict_data,
                    deepgram_transcript=raw_transcript,
                    gpt_transcript=transcript,
                )
                if not supabase_ok:
                    supabase_error = st.session_state.get(
                        "supabase_last_vip_log_error",
                        "Невідома помилка запису у Supabase",
                    )
            except Exception as e:
                supabase_error = str(e)

            sheet_error = _write_result_to_sheet(call, verdict_data)
            results_state[i] = {
                "verdict_data": {
                    **verdict_data,
                    "supabase_error": supabase_error,
                    "sheet_error": sheet_error,
                },
                "facts": facts,
                "analysis_done": True,
                "client_id": call.get("client_id", ""),
            }
            return True
    except Exception as e:
        store_analysis_failure(results_state, i, str(e), client_id=call.get("client_id", ""))
        return False


def _render_vip_results(call_type: str, card_id: int) -> None:
    result = (st.session_state.get(f"results_{call_type}") or {}).get(card_id - 1)
    if not result:
        return
    if result.get("analysis_error"):
        st.error(result["analysis_error"])
        return
    verdict_data = result.get("verdict_data") or {}
    render_score_badge(verdict_data)


def _process_pending(
    call_type: str,
    qa_manager,
    managers_config,
) -> None:
    slug = _slug(call_type)
    keys = _keys(slug)
    pending = list(st.session_state.get(keys["pending"]) or [])
    if not pending:
        return
    card_id = pending.pop(0)
    st.session_state[keys["pending"]] = pending
    results_key = f"results_{call_type}"
    results_state = init_call_results_state(results_key)
    call = collect_card_call(card_id, managers_config, qa_manager, call_type=call_type)
    results_state.pop(card_id - 1, None)
    ok = _analyze_single_call(card_id - 1, call, results_state)
    if ok:
        set_analysis_run_summary(f"Дзвінок {card_id} проаналізовано.", level="success")
    else:
        set_analysis_run_summary(f"Дзвінок {card_id} не проаналізовано.", level="error")


def _render_call_type_tab(
    call_type: str,
    check_date,
    qa_manager,
    managers_config,
    projects_list,
    manager_dept: str,
) -> None:
    _ = manager_dept
    slug = _slug(call_type)
    keys = _keys(slug)
    cards = ensure_card_state(call_type)
    results_key = f"results_{call_type}"
    init_call_results_state(results_key)
    pending = st.session_state.get(keys["pending"]) or []
    analyzing = bool(pending)

    if pending:
        try:
            _process_pending(call_type, qa_manager, managers_config)
        except Exception as exc:
            st.session_state[keys["pending"]] = []
            st.error(f"Не вдалося запустити аналіз VIP-дзвінка: {exc}")

    render_call_type_stats(call_type, slug, check_date)
    render_analysis_run_summary()

    with st.container(border=True, key="upload_block_shell"):
        action = render_upload_toolbar(call_type, cards, projects_list)
        with st.container(key=keys["body"]):
            for row in card_rows(list(cards)):
                cols = st.columns(GRID_COLUMNS)
                for col, card in zip(cols, row):
                    with col:
                        render_vip_card(
                            card,
                            call_type=call_type,
                            projects_list=projects_list,
                            managers_config=managers_config,
                            analyzing=analyzing,
                        )
                        _render_vip_results(call_type, card["id"])

            if render_add_calls_button(call_type, analyzing=analyzing):
                handle_add_card(call_type)

            if action == "run":
                queue_all_ready(call_type, cards, projects_list)
                st.rerun()

    render_archive_section(call_type=call_type, slug=slug, check_date=check_date)


def run_call_type_page(
    call_type: str,
    check_date,
    qa_manager,
    managers_config,
    projects_list,
    manager_dept: str = "VIP",
) -> None:
    _render_call_type_tab(
        call_type, check_date, qa_manager, managers_config, projects_list, manager_dept
    )
