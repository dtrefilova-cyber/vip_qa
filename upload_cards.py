"""Сітка карток внесення VIP-дзвінка (окрема сторінка на кожен call_type)."""

from __future__ import annotations

import html

import streamlit as st

from constants import (
    CALL_TYPE_FRIENDLY,
    CALL_TYPE_SHORT_90S,
    page_slug,
)
from ui_theme import clean_select_options, status_pill_html, sync_select_state

GRID_COLUMNS = 3


def _slug(call_type: str) -> str:
    return page_slug(call_type)


def _keys(slug: str) -> dict[str, str]:
    return {
        "cards": f"vip_upload_cards_{slug}",
        "next_id": f"vip_upload_next_id_{slug}",
        "errors": f"vip_upload_errors_{slug}",
        "pending": f"vip_upload_pending_{slug}",
        "visible": f"vip_upload_visible_{slug}",
        "body": f"vip_upload_body_{slug}",
    }


def _fk(slug: str, name: str, card_id: int) -> str:
    return f"{name}_{slug}_{card_id}"


def initial_cards() -> list[dict]:
    return [
        {"id": 1, "number": 1, "expanded": True},
        {"id": 2, "number": 2, "expanded": True},
        {"id": 3, "number": 3, "expanded": True},
    ]


def ensure_card_state(call_type: str) -> list[dict]:
    keys = _keys(_slug(call_type))
    if keys["cards"] not in st.session_state:
        st.session_state[keys["cards"]] = initial_cards()
        st.session_state[keys["next_id"]] = 4
    if keys["errors"] not in st.session_state:
        st.session_state[keys["errors"]] = {}
    if keys["pending"] not in st.session_state:
        st.session_state[keys["pending"]] = []
    if keys["visible"] not in st.session_state:
        st.session_state[keys["visible"]] = True
    cards = st.session_state[keys["cards"]]
    for card in cards:
        if not isinstance(card, dict):
            continue
        card.setdefault("id", card.get("number", 1))
        card.setdefault("number", card.get("id", 1))
    return cards


def card_title(number: int) -> str:
    return f"Дзвінок #{int(number):04d}"


def card_rows(cards: list[dict], per_row: int = GRID_COLUMNS) -> list[list[dict]]:
    return [cards[i : i + per_row] for i in range(0, len(cards), per_row)]


def _field_label(icon: str, text: str, *, tall: bool = False) -> None:
    cls = "uf-lab tall" if tall else "uf-lab"
    st.markdown(
        f'<div class="{cls}"><span class="uf-ico">{icon}</span>'
        f"<span>{html.escape(text)}</span></div>",
        unsafe_allow_html=True,
    )


def _field_cols(*, tall: bool = False):
    align = "top" if tall else "center"
    return st.columns([1.12, 1.28], vertical_alignment=align)


def _url_key(call_type: str, card_id: int) -> str:
    return _fk(_slug(call_type), "url", card_id)


def _date_key(call_type: str, card_id: int) -> str:
    return _fk(_slug(call_type), "calldate", card_id)


def _has_url(call_type: str, card_id: int) -> bool:
    return bool(str(st.session_state.get(_url_key(call_type, card_id)) or "").strip())


def required_errors(call_type: str, card_id: int, projects_list: list) -> dict[str, str]:
    _ = projects_list
    slug = _slug(call_type)
    errors = {}
    if not _has_url(call_type, card_id):
        errors["url"] = "Вкажіть посилання на дзвінок"
    if not str(st.session_state.get(_fk(slug, "manager", card_id)) or "").strip():
        errors["ret_manager"] = "Оберіть менеджера"
    if not str(st.session_state.get(_fk(slug, "client", card_id)) or "").strip():
        errors["client_id"] = "Введіть ID клієнта"
    if not st.session_state.get(_date_key(call_type, card_id)):
        errors["call_date"] = "Оберіть дату дзвінка"
    return errors


def collect_card_call(
    card_id: int,
    managers_config: list,
    qa_manager: str,
    *,
    call_type: str,
) -> dict:
    slug = _slug(call_type)
    manager_lookup = {m.get("manager"): m for m in managers_config}
    ret_manager = str(st.session_state.get(_fk(slug, "manager", card_id)) or "").strip()
    manager_meta = manager_lookup.get(ret_manager, {})
    call_date_raw = st.session_state.get(_date_key(call_type, card_id))
    call_date = call_date_raw.strftime("%d.%m.%Y") if call_date_raw else ""
    project = str(manager_meta.get("project") or "").strip()
    betking_x2 = project.lower() == "betking"
    selected_type = CALL_TYPE_FRIENDLY if call_type == CALL_TYPE_FRIENDLY else CALL_TYPE_SHORT_90S
    return {
        "url": str(st.session_state.get(_url_key(call_type, card_id)) or "").strip(),
        "ret_manager": ret_manager,
        "project": project,
        "tl": manager_meta.get("tl", ""),
        "client_id": str(st.session_state.get(_fk(slug, "client", card_id)) or "").strip(),
        "call_date": call_date,
        "qa_comment": str(st.session_state.get(_fk(slug, "comment", card_id)) or "").strip(),
        "important_note": str(st.session_state.get(_fk(slug, "important", card_id)) or "").strip(),
        "vip_call_type": selected_type,
        "client_is_military": bool(st.session_state.get(_fk(slug, "military", card_id))),
        "betking_x2_applicable": betking_x2,
        "qa_manager": qa_manager,
    }


def render_upload_toolbar(call_type: str, cards: list[dict], projects_list: list) -> str | None:
    slug = _slug(call_type)
    keys = _keys(slug)
    opened = bool(st.session_state.get(keys["visible"], True))
    analyzing = bool(st.session_state.get(keys["pending"]) or [])
    ready = any(
        _has_url(call_type, c["id"]) and not required_errors(call_type, c["id"], projects_list)
        for c in cards
    )
    run_clicked = False
    type_label = call_type if call_type in {CALL_TYPE_SHORT_90S, CALL_TYPE_FRIENDLY} else "VIP"

    st.markdown(
        f'<div style="font-size:14px;font-weight:700;color:var(--text-heading);margin:2px 0 10px">'
        f"Завантажити дзвінки · {html.escape(type_label)}</div>",
        unsafe_allow_html=True,
    )

    left, right = st.columns([2.2, 1.8], vertical_alignment="center")
    with left:
        toggle_label = "▼  Сховати форми" if opened else "▶  Показати форми"
        if st.button(toggle_label, key=f"ret_upload_toggle_{slug}", type="tertiary"):
            st.session_state[keys["visible"]] = not opened
            st.rerun()
    with right:
        run_clicked = st.button(
            "Проаналізувати всі дзвінки",
            type="secondary",
            key=f"ret_run_all_{slug}",
            disabled=not ready or analyzing,
            use_container_width=True,
        )

    if not opened:
        st.markdown(
            f"<style>.st-key-{keys['body']}{{display:none!important;}}</style>",
            unsafe_allow_html=True,
        )

    if run_clicked:
        return "run"
    return None


def render_add_calls_button(call_type: str, *, analyzing: bool = False) -> bool:
    slug = _slug(call_type)
    return st.button(
        "+ Додати дзвінки",
        key=f"ret_add_{slug}",
        type="primary",
        use_container_width=False,
        disabled=analyzing,
    )


def _card_status_kind(
    *,
    call_type: str,
    card_id: int,
    projects_list: list,
    analyzing: bool,
    results: dict | None,
) -> str:
    slug = _slug(call_type)
    pending = st.session_state.get(_keys(slug)["pending"]) or []
    if card_id in pending:
        return "run"
    if results:
        if results.get("analysis_error") or results.get("analysis_done") is False:
            return "err"
        if results.get("analysis_done") or results.get("verdict_data"):
            return "done"
    if _has_url(call_type, card_id) and not required_errors(call_type, card_id, projects_list):
        return "ready"
    return "new"


def _delete_card(call_type: str, card_id: int) -> None:
    slug = _slug(call_type)
    keys = _keys(slug)
    st.session_state[keys["cards"]] = [
        c for c in st.session_state[keys["cards"]] if c["id"] != card_id
    ]
    st.session_state.get(keys["errors"], {}).pop(card_id, None)
    st.session_state[keys["pending"]] = [
        x for x in st.session_state.get(keys["pending"], []) if x != card_id
    ]


def render_vip_card(
    card: dict,
    *,
    call_type: str,
    projects_list: list[str],
    managers_config: list,
    analyzing: bool,
) -> None:
    card_id = int(card.get("id") or card.get("number") or 1)
    number = int(card.get("number") or card_id)
    title = card_title(number)
    slug = _slug(call_type)
    errors = dict((st.session_state.get(_keys(slug)["errors"]) or {}).get(card_id) or {})
    manager_names = clean_select_options(m.get("manager") for m in managers_config)
    is_friendly = call_type == CALL_TYPE_FRIENDLY

    with st.container(border=True, key=f"ret_card_{slug}_{card_id}"):
        st.markdown('<div class="upload-call-card-marker"></div>', unsafe_allow_html=True)
        results = (st.session_state.get(f"results_{call_type}") or {}).get(card_id - 1)
        status_kind = _card_status_kind(
            call_type=call_type,
            card_id=card_id,
            projects_list=projects_list,
            analyzing=analyzing,
            results=results,
        )
        head_l, head_b, head_d = st.columns([4.2, 2.2, 0.8], vertical_alignment="center")
        with head_l:
            st.markdown(
                f'<div class="upload-card-title"><span class="phone">☎</span> {html.escape(title)}</div>',
                unsafe_allow_html=True,
            )
        with head_b:
            st.markdown(
                f'<div style="text-align:right">{status_pill_html(status_kind)}</div>',
                unsafe_allow_html=True,
            )
        with head_d:
            if st.button("🗑", key=f"ret_card_del_{slug}_{card_id}", disabled=analyzing, type="tertiary"):
                _delete_card(call_type, card_id)
                st.rerun()

        left, right = _field_cols()
        with left:
            _field_label("🔗", "Посилання на дзвінок")
        with right:
            st.text_input(
                "Посилання",
                key=_url_key(call_type, card_id),
                label_visibility="collapsed",
                disabled=analyzing,
            )

        left, right = _field_cols()
        with left:
            _field_label("👤", "Менеджер VIP")
        with right:
            mk = _fk(slug, "manager", card_id)
            sync_select_state(mk, manager_names)
            st.selectbox(
                "Менеджер",
                manager_names,
                index=None,
                placeholder="Оберіть менеджера",
                key=mk,
                disabled=analyzing or not manager_names,
                label_visibility="collapsed",
            )

        left, right = _field_cols()
        with left:
            _field_label("🆔", "ID клієнта")
        with right:
            st.text_input(
                "ID",
                key=_fk(slug, "client", card_id),
                label_visibility="collapsed",
                disabled=analyzing,
            )

        left, right = _field_cols()
        with left:
            _field_label("📅", "Дата дзвінка")
        with right:
            st.date_input(
                "Дата",
                value=None,
                format="DD.MM.YYYY",
                key=_date_key(call_type, card_id),
                disabled=analyzing,
                label_visibility="collapsed",
            )

        if is_friendly:
            st.checkbox(
                "Клієнт військовий",
                key=_fk(slug, "military", card_id),
                disabled=analyzing,
                help="Впливає на критерій «Заклик до гри» (не питаємо «чому» після відмови).",
            )

        left, right = _field_cols(tall=True)
        with left:
            label = (
                "Коментар попереднього контакту / Важливе"
                if is_friendly
                else "Важливе / попередній контакт"
            )
            _field_label("🚩", label, tall=True)
        with right:
            st.text_area(
                "Важливе",
                key=_fk(slug, "important", card_id),
                height=68,
                label_visibility="collapsed",
                disabled=analyzing,
            )

        left, right = _field_cols(tall=True)
        with left:
            _field_label("💬", "Коментар по цьому дзвінку", tall=True)
        with right:
            st.text_area(
                "Коментар",
                key=_fk(slug, "comment", card_id),
                height=68,
                label_visibility="collapsed",
                disabled=analyzing,
            )

        invalid = required_errors(call_type, card_id, projects_list)
        if errors:
            for msg in errors.values():
                st.markdown(
                    f'<div class="field-error">{html.escape(msg)}</div>',
                    unsafe_allow_html=True,
                )

        if st.button(
            "▶️ Аналіз цього дзвінка",
            key=f"run_single_{slug}_{card_id}",
            disabled=analyzing or bool(invalid),
            type="secondary",
        ):
            if invalid:
                st.session_state.setdefault(_keys(slug)["errors"], {})[card_id] = invalid
                st.rerun()
            pending = list(st.session_state.get(_keys(slug)["pending"]) or [])
            if card_id not in pending:
                pending.append(card_id)
            st.session_state[_keys(slug)["pending"]] = pending
            st.rerun()


def handle_add_card(call_type: str) -> None:
    slug = _slug(call_type)
    keys = _keys(slug)
    next_id = int(st.session_state.get(keys["next_id"]) or 4)
    cards = st.session_state[keys["cards"]]
    cards.append({"id": next_id, "number": next_id, "expanded": True})
    st.session_state[keys["next_id"]] = next_id + 1
    st.rerun()


def queue_all_ready(call_type: str, cards: list[dict], projects_list: list) -> None:
    slug = _slug(call_type)
    keys = _keys(slug)
    pending = list(st.session_state.get(keys["pending"]) or [])
    for card in cards:
        cid = card["id"]
        if _has_url(call_type, cid) and not required_errors(call_type, cid, projects_list):
            if cid not in pending:
                pending.append(cid)
    st.session_state[keys["pending"]] = pending
