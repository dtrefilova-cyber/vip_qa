"""Запис VIP-результатів і кешу транскриптів у Supabase."""

from __future__ import annotations

import importlib.metadata

from supabase import create_client

from utils import BUILD_SHA

SUPABASE_UNAVAILABLE_MESSAGE = (
    "Supabase тимчасово недоступний — нові записи можуть не зберегтися. "
    "Перевірте Secrets або спробуйте пізніше."
)


def _pick_supabase_credentials(secrets_mapping):
    if not secrets_mapping:
        return "", "", ""
    url = secrets_mapping.get("SUPABASE_URL") or secrets_mapping.get("supabase_url")
    candidates = (
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_SECRET_KEY",
        "SUPABASE_KEY",
        "SUPABASE_PUBLISHABLE_KEY",
    )
    picked_source = ""
    picked_key = ""
    for candidate in candidates:
        value = secrets_mapping.get(candidate)
        if value:
            picked_source = candidate
            picked_key = value
            break
    return str(url or "").strip(), str(picked_key or "").strip(), picked_source


def _mask_key_preview(key: str) -> str:
    key = str(key or "").strip()
    if not key:
        return "empty"
    if len(key) <= 10:
        return f"{key[:2]}...{key[-2:]}"
    return f"{key[:6]}...{key[-4:]}"


def _read_supabase_credentials():
    import streamlit as st

    secrets = st.secrets
    url, key, key_source = _pick_supabase_credentials(secrets)
    if not url or not key:
        nested_url, nested_key, nested_source = _pick_supabase_credentials(
            secrets.get("gcp_service_account")
        )
        url = url or nested_url
        if not key and nested_key:
            key = nested_key
            key_source = (
                f"gcp_service_account.{nested_source}" if nested_source else "gcp_service_account"
            )
    return url, key, key_source


def get_supabase_client():
    try:
        supabase_version = importlib.metadata.version("supabase")
    except importlib.metadata.PackageNotFoundError:
        supabase_version = "unknown"

    import streamlit as st

    try:
        url, key, key_source = _read_supabase_credentials()
    except Exception as e:
        return None, f"ERROR: не вдалось прочитати st.secrets: {e}"

    st.session_state["supabase_last_key_source"] = key_source or "unknown"
    st.session_state["supabase_last_key_preview"] = _mask_key_preview(key)

    if not url:
        return None, (
            "ERROR: SUPABASE_URL відсутній у Streamlit Secrets. "
            "Перевірте: ключ і значення на одному рядку, поза секцією [gcp_service_account]."
        )
    if not key:
        return None, (
            "ERROR: SUPABASE_KEY відсутній у Streamlit Secrets "
            "(очікується SUPABASE_KEY, SUPABASE_SECRET_KEY або SUPABASE_PUBLISHABLE_KEY)"
        )

    try:
        return create_client(url, key), None
    except Exception as e:
        return None, (
            f"ERROR: create_client failed (supabase {supabase_version}): {e}. "
            "Оновіть supabase>=2.10.0 для ключів sb_publishable_/sb_secret_."
        )


def get_supabase_health() -> tuple[bool, str | None]:
    client, err = get_supabase_client()
    if client is None:
        return False, err
    return True, None


def _safe_date(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    s = str(value).strip()
    if not s:
        return None
    if len(s) == 10 and s[2] == "." and s[5] == ".":
        try:
            day, month, year = s.split(".")
            return f"{year}-{month}-{day}"
        except ValueError:
            pass
    if len(s) == 5 and s[2] == ".":
        try:
            day, month = s.split(".")
            return f"2026-{month}-{day}"
        except ValueError:
            pass
    if len(s) == 10 and s[4] == "-":
        return s
    return None


def log_vip_short_call_to_supabase(
    call: dict,
    facts: dict,
    verdict_data: dict,
    deepgram_transcript: str = "",
    gpt_transcript: str = "",
) -> bool:
    client, connect_error = get_supabase_client()
    if client is None:
        if connect_error:
            raise RuntimeError(connect_error)
        return False

    row = {
        "call_url": call.get("url", ""),
        "client_id": str(call.get("client_id", "")),
        "call_date": _safe_date(call.get("call_date")),
        "qa_comment": call.get("qa_comment", ""),
        "important_note": call.get("important_note", ""),
        "bonus_status": call.get("bonus_status", ""),
        "previous_call_not_service": bool(call.get("previous_call_not_service")),
        "days_since_last_service_30plus": bool(call.get("days_since_last_service_30plus")),
        "has_tl_permission": bool(call.get("has_tl_permission")),
        "is_birthday_call": bool(facts.get("is_birthday_greeting")),
        "deepgram_transcript": deepgram_transcript,
        "gpt_transcript": gpt_transcript,
        "forbidden_words_found": [],
        "rudeness_detected": False,
        "rudeness_confidence": "low",
        # New rubric fields (nullable on DB; also mirrored into debug_data)
        "call_type": verdict_data.get("call_type") or call.get("vip_call_type"),
        "rubric_version": verdict_data.get("rubric_version"),
        "criteria_facts": dict(facts or {}),
        "criteria_scores": verdict_data.get("criteria") or [],
        "total_score": verdict_data.get("total_score"),
        "max_score": verdict_data.get("max_score"),
        "percent": verdict_data.get("percent"),
        "is_critical_fail": bool(verdict_data.get("is_critical_fail")),
        "verdict": verdict_data.get("verdict") or "scored",
        "verdict_reasons": verdict_data.get("verdict_reasons", []),
        "review_flags": verdict_data.get("review_flags", []),
        "debug_data": {
            "facts": dict(facts),
            "call": {k: v for k, v in call.items() if k not in ("qa_comment", "important_note")},
            "score": {
                "call_type": verdict_data.get("call_type") or call.get("vip_call_type"),
                "total_score": verdict_data.get("total_score"),
                "max_score": verdict_data.get("max_score"),
                "percent": verdict_data.get("percent"),
                "is_critical_fail": bool(verdict_data.get("is_critical_fail")),
                "critical_reasons": verdict_data.get("critical_reasons") or [],
                "criteria": verdict_data.get("criteria") or [],
                "rubric_version": verdict_data.get("rubric_version"),
                "score_label": verdict_data.get("score_label"),
            },
            "build_sha": BUILD_SHA,
        },
    }

    try:
        client.table("vip_short_call_logs").insert(row).execute()
        return True
    except Exception as e:
        # Fallback without new columns if migration not applied yet
        msg = str(e)
        if "column" in msg.lower() or "schema" in msg.lower() or "pgrst" in msg.lower():
            legacy = {
                k: v
                for k, v in row.items()
                if k
                not in {
                    "call_type",
                    "rubric_version",
                    "criteria_facts",
                    "criteria_scores",
                    "total_score",
                    "max_score",
                    "percent",
                    "is_critical_fail",
                }
            }
            try:
                client.table("vip_short_call_logs").insert(legacy).execute()
                return True
            except Exception as e2:
                e = e2
        import streamlit as st

        key_source = st.session_state.get("supabase_last_key_source", "unknown")
        key_preview = st.session_state.get("supabase_last_key_preview", "empty")
        st.session_state["supabase_last_vip_log_error"] = (
            f"{e} | ключ узято з: {key_source} ({key_preview})"
        )
        return False
