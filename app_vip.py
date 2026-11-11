"""VIP — головна сторінка з картками (Короткий 120 сек / VIP Friendly)."""

from __future__ import annotations

import json as _json
import logging

import streamlit as st

logger = logging.getLogger(__name__)

from constants import CALL_TYPE_FRIENDLY, CALL_TYPE_SHORT_90S, VIP_SHORT_SHEET_ID
from core.vip_friendly_scoring import score_vip_friendly_call
from core.vip_short_scoring import score_vip_short_call
from google_sheets import (
    append_vip_short_result,
    connect_google,
    format_vip_score_comment_for_sheet,
)
from supabase_logger import log_vip_short_call_to_supabase
from vip_journal_sheets import make_analysis_id, resolve_journal_call_type, write_vip_journal_result
from upload_cards import (
    GRID_COLUMNS,
    _keys,
    _slug,
    card_rows,
    collect_card_call,
    ensure_card_state,
    format_check_date,
    handle_add_card,
    pending_progress,
    pop_queued_call,
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
from vip_archive import clear_vip_day_cache, render_archive_section, render_call_type_stats
from vip_short_ai_assistant import (
    VIP_FRIENDLY_FACTS_CACHE_TAG,
    VIP_SHORT_FACTS_CACHE_TAG,
    extract_vip_friendly_facts,
    extract_vip_short_90s_facts,
    user_safe_analysis_error,
)


def _facts_cache_key(tag, dialogue, qa_comment, important_note, cache_version, extra=""):
    payload = "|".join(
        [tag, cache_version, qa_comment or "", important_note or "", extra or "", dialogue or ""]
    )
    return _transcript_cache_key(payload, cache_version, "", "", False)


@st.cache_data(ttl=172800, show_spinner=False)
def analyze_vip_short_90s_cached(
    url,
    call_date,
    dialogue,
    qa_comment,
    important_note,
    cache_version,
    number_signed=False,
    client_is_military=False,
    manager_name="",
    project="",
):
    _ = (url, call_date)
    extra = (
        f"signed={bool(number_signed)}|mil={bool(client_is_military)}"
        f"|mgr={manager_name}|proj={project}"
    )
    cache_key = _facts_cache_key(
        VIP_SHORT_FACTS_CACHE_TAG,
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
    facts = extract_vip_short_90s_facts(
        client,
        OPENAI_ANALYSIS_MODEL,
        dialogue,
        qa_comment,
        important_note,
        OPENAI_MAX_OUTPUT_TOKENS,
        manager_name=str(manager_name or ""),
        project=str(project or ""),
        number_signed=bool(number_signed),
        client_is_military=bool(client_is_military),
        dialogue_for_context=dialogue,
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
        try:
            pts_txt = f"{float(pts):g}" if pts is not None else "—"
            mx_txt = f"{float(mx):g}" if mx is not None else "—"
        except (TypeError, ValueError):
            pts_txt, mx_txt = str(pts), str(mx)
        st.write(f"**{label}:** {pts_txt} / {mx_txt}")
        for reason in item.get("reasons") or []:
            st.caption(f"— {reason}")

    for flag in verdict_data.get("review_flags") or []:
        st.warning(str(flag))

    # Neutral UX only — never surface raw exception / secret details
    if verdict_data.get("supabase_write_failed"):
        st.warning("Результат оцінено, але не залогований у Supabase. Повідомте розробника.")
    if verdict_data.get("sheet_write_failed"):
        st.warning("Результат оцінено, але не записаний у RESULTS. Повідомте розробника.")
    journal_status = str(verdict_data.get("journal_status") or "").strip()
    if verdict_data.get("journal_write_ok"):
        st.success(journal_status or "Записано")
    elif verdict_data.get("journal_write_failed"):
        err = str(verdict_data.get("journal_write_error") or "").strip()
        st.warning(
            "Результат оцінено, але не записаний у журнал проєкту."
            + (f" {err}" if err else " Повідомте розробника.")
        )
    if verdict_data.get("analysis_error"):
        st.error("Аналіз не завершився. Повідомте розробника.")


# legacy name
render_verdict_badge = render_score_badge


def _write_result_to_sheet(call, verdict_data) -> bool:
    """Операційний RESULTS. True = ok. Деталі помилок лише в лог."""
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
            "result": "",  # заповнює format_vip_result_cell з total/max
            "comment": format_vip_score_comment_for_sheet(verdict_data),
        }
        res = append_vip_short_result(gclient, VIP_SHORT_SHEET_ID, row_data)
        if res is not True:
            logger.error("Sheets RESULTS write returned non-True: %s", res)
            return False
        return True
    except Exception:
        logger.exception("Sheets RESULTS write failed")
        return False


def _write_journal_safe(call, verdict_data) -> dict:
    """Запис у журнал Betking/777/Vegas (A:L або N:AC). Один повтор при збої API."""
    last: dict = {"ok": False, "status": "Помилка запису"}
    for attempt in range(2):
        try:
            gclient = connect_google()
            result = write_vip_journal_result(gclient, call, verdict_data)
            if result.get("ok"):
                return result
            last = result
            logger.error(
                "VIP journal write failed attempt=%s: %s",
                attempt + 1,
                result.get("error"),
            )
        except Exception as exc:
            logger.exception("VIP journal write failed attempt=%s", attempt + 1)
            last = {"ok": False, "error": str(exc), "status": "Помилка запису"}
    return last


def _user_safe_analysis_error(exc: BaseException) -> str:
    """Коротке повідомлення для QA без сирих stack/secret деталей."""
    return user_safe_analysis_error(exc)


def _analyze_single_call(i, call, results_state, spinner_label=None):
    try:
        label = spinner_label or f"Аналіз VIP-дзвінка {i + 1}..."
        with st.spinner(label):
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
            journal_type = resolve_journal_call_type(selected) or (
                "friendly" if selected == CALL_TYPE_FRIENDLY else "short"
            )
            call["journal_call_type"] = journal_type
            call["analysis_id"] = make_analysis_id(call, journal_type)

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
                # Портал: dialogue = cleaned transcript для цитат/grounding
                verdict_data = score_vip_friendly_call(facts, call, transcript)
            else:
                facts = analyze_vip_short_90s_cached(
                    call.get("url", ""),
                    call.get("call_date", ""),
                    timed_for_gpt,
                    call.get("qa_comment", ""),
                    call.get("important_note", ""),
                    ANALYSIS_CACHE_VERSION,
                    bool(call.get("number_signed")),
                    bool(call.get("client_is_military")),
                    str(call.get("ret_manager") or ""),
                    str(call.get("project") or ""),
                )
                # dialogue = timed cleaned; source_text = raw timed (для edge flags)
                verdict_data = score_vip_short_call(
                    facts,
                    call,
                    timed_for_gpt,
                    str(timed_transcript or raw_transcript or ""),
                )

            # Критична помилка: ознака/обґрунтування в verdict; критерії не обнуляємо для журналу.
            verdict_data["analysis_id"] = call["analysis_id"]

            # Isolate each sink so one failure does not block the others
            supabase_ok = False
            try:
                supabase_ok = bool(
                    log_vip_short_call_to_supabase(
                        call,
                        facts,
                        verdict_data,
                        deepgram_transcript=raw_transcript,
                        gpt_transcript=transcript,
                    )
                )
                if supabase_ok:
                    clear_vip_day_cache()
            except Exception:
                logger.exception("Supabase insert failed")

            sheet_ok = False
            try:
                sheet_ok = _write_result_to_sheet(call, verdict_data)
            except Exception:
                logger.exception("Sheets RESULTS write failed")

            journal_result = {"ok": False, "status": "Помилка запису"}
            try:
                journal_result = _write_journal_safe(call, verdict_data)
            except Exception:
                logger.exception("VIP journal write failed")
                journal_result = {"ok": False, "error": "exception", "status": "Помилка запису"}

            results_state[i] = {
                "verdict_data": {
                    **verdict_data,
                    "supabase_write_failed": not supabase_ok,
                    "sheet_write_failed": not sheet_ok,
                    "journal_write_ok": bool(journal_result.get("ok")),
                    "journal_write_failed": not bool(journal_result.get("ok")),
                    "journal_status": journal_result.get("status") or "",
                    "journal_write_error": journal_result.get("error") or "",
                    "journal_row": journal_result.get("row"),
                    "journal_sheet": journal_result.get("sheet_title"),
                },
                "facts": facts,
                "analysis_done": True,
                "client_id": call.get("client_id", ""),
            }
            return True
    except Exception as exc:
        logger.exception(
            "VIP analysis failed card=%s client_id=%s call_type=%s err_type=%s",
            i + 1,
            call.get("client_id", ""),
            call.get("vip_call_type", ""),
            type(exc).__name__,
        )
        store_analysis_failure(
            results_state,
            i,
            _user_safe_analysis_error(exc),
            client_id=call.get("client_id", ""),
        )
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


def _record_batch_progress(call_type: str, card_id: int, ok: bool) -> None:
    keys = _keys(_slug(call_type))
    if ok:
        st.session_state[keys["batch_ok"]] = int(st.session_state.get(keys["batch_ok"]) or 0) + 1
    else:
        st.session_state[keys["batch_fail"]] = int(st.session_state.get(keys["batch_fail"]) or 0) + 1

    remaining = len(st.session_state.get(keys["pending"]) or [])
    total = int(st.session_state.get(keys["batch_total"]) or 1)
    done_ok = int(st.session_state.get(keys["batch_ok"]) or 0)
    done_fail = int(st.session_state.get(keys["batch_fail"]) or 0)

    if remaining:
        status = "проаналізовано" if ok else "не проаналізовано"
        set_analysis_run_summary(
            f"Дзвінок {card_id} {status}. Далі ще {remaining} — аналіз по черзі.",
            level="success" if ok else "warning",
        )
        return

    if done_fail and done_ok:
        set_analysis_run_summary(
            f"Оброблено {total}: {done_ok} успішно, {done_fail} з помилкою.",
            level="warning",
        )
    elif done_fail:
        message = (
            f"Дзвінок {card_id} не проаналізовано."
            if total == 1
            else f"Не вдалося проаналізувати {done_fail} дзвінки."
        )
        set_analysis_run_summary(message, level="error")
    elif total > 1:
        set_analysis_run_summary(f"Проаналізовано {total} дзвінки.", level="success")
    else:
        set_analysis_run_summary(f"Дзвінок {card_id} проаналізовано.", level="success")


def _process_pending(
    call_type: str,
    qa_manager,
    managers_config,
    check_date=None,
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
    try:
        call = pop_queued_call(call_type, card_id)
        if not call:
            call = collect_card_call(card_id, managers_config, qa_manager, call_type=call_type)
        call["card_id"] = int(card_id)
        if check_date is not None:
            call["check_date"] = format_check_date(check_date)
        results_state.pop(card_id - 1, None)
        current, total = pending_progress(call_type)
        spinner = (
            f"Аналіз VIP-дзвінка {card_id} ({current} з {total})..."
            if total > 1
            else f"Аналіз VIP-дзвінка {card_id}..."
        )
        ok = _analyze_single_call(card_id - 1, call, results_state, spinner_label=spinner)
        _record_batch_progress(call_type, card_id, ok)
    except Exception as exc:
        logger.exception(
            "VIP queue card failed card=%s type=%s remaining=%s err_type=%s",
            card_id,
            call_type,
            len(st.session_state.get(keys["pending"]) or []),
            type(exc).__name__,
        )
        store_analysis_failure(
            results_state,
            card_id - 1,
            _user_safe_analysis_error(exc),
            client_id="",
        )
        _record_batch_progress(call_type, card_id, False)


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
    processed = False

    if pending:
        try:
            _process_pending(call_type, qa_manager, managers_config, check_date=check_date)
            processed = True
        except Exception as exc:
            logger.exception(
                "VIP pending queue failed type=%s remaining=%s err_type=%s",
                call_type,
                len(st.session_state.get(keys["pending"]) or []),
                type(exc).__name__,
            )
            set_analysis_run_summary(
                "Дзвінок не проаналізовано. Наступні в черзі продовжаться автоматично.",
                level="warning",
            )
            processed = True

    # Після обробки картки кнопки блокуємо лише якщо черга ще не порожня.
    analyzing = bool(st.session_state.get(keys["pending"]) or [])

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
                            qa_manager=qa_manager,
                            check_date=check_date,
                        )
                        _render_vip_results(call_type, card["id"])

            if render_add_calls_button(call_type, analyzing=analyzing):
                handle_add_card(call_type)

            if action == "run":
                queue_all_ready(
                    call_type,
                    cards,
                    projects_list,
                    managers_config=managers_config,
                    qa_manager=qa_manager,
                    check_date=check_date,
                )
                st.rerun()

    render_archive_section(call_type=call_type, slug=slug, check_date=check_date)

    # Один дзвінок за скрипт: після UI запускаємо наступний rerun, щоб не паралелити GPT/Deepgram.
    if processed:
        st.rerun()


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
