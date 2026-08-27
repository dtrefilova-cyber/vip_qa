"""Секрети, OpenAI/Deepgram, транскрипція і кеш очищеного тексту."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess

import requests
import streamlit as st
from openai import OpenAI


def get_build_sha() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


BUILD_SHA = get_build_sha()


def init_call_results_state(results_key: str) -> dict:
    state = st.session_state.get(results_key)
    if not isinstance(state, dict):
        state = {}
        st.session_state[results_key] = state
    return state


def set_analysis_run_summary(message: str, level: str = "info") -> None:
    st.session_state["analysis_run_summary"] = {
        "message": str(message or "").strip(),
        "level": level if level in {"info", "warning", "error", "success"} else "info",
    }


def render_analysis_run_summary() -> None:
    summary = st.session_state.get("analysis_run_summary")
    if not summary or not summary.get("message"):
        return
    message = summary["message"]
    level = summary.get("level", "info")
    if level == "error":
        st.error(message)
    elif level == "warning":
        st.warning(message)
    elif level == "success":
        st.success(message)
    else:
        st.info(message)


def store_analysis_failure(
    results: dict,
    slot_index: int,
    error: str,
    *,
    client_id: str = "",
) -> None:
    results[slot_index] = {
        "scores": {},
        "comment": "",
        "total_score": 0.0,
        "critical": False,
        "client_id": client_id,
        "analysis_done": False,
        "comment_done": False,
        "sheet_saved": False,
        "analysis_error": str(error or "Невідома помилка аналізу"),
    }


def read_secret(name, default=None):
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    if value is None or str(value).strip() == "":
        env_value = os.getenv(name)
        if env_value is not None and str(env_value).strip() != "":
            return env_value
        return default
    return value


DEEPGRAM_API_KEY = read_secret("DEEPGRAM_API_KEY")
OPENAI_API_KEY = read_secret("OPENAI_API_KEY")

missing_required = []
if not DEEPGRAM_API_KEY:
    missing_required.append("DEEPGRAM_API_KEY")
if not OPENAI_API_KEY:
    missing_required.append("OPENAI_API_KEY")

if missing_required:
    st.error(
        "Відсутні обов'язкові секрети: "
        + ", ".join(missing_required)
        + ". Додайте їх у Streamlit Secrets (або environment variables) і перезапустіть застосунок."
    )
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

LOG_SHEET_ID = "1LTje88l2rnirwHn-4WuVlP6Ue0ndJUWIGleWA8Wrk3k"
OPENAI_ANALYSIS_MODEL = read_secret("OPENAI_MODEL", "gpt-5.4-mini")
ANALYSIS_CACHE_VERSION = f"v3.8-{OPENAI_ANALYSIS_MODEL}"
OPENAI_TRANSCRIPT_MODEL = read_secret("OPENAI_TRANSCRIPT_MODEL", "gpt-4.1-mini")
OPENAI_MAX_OUTPUT_TOKENS = int(read_secret("OPENAI_MAX_OUTPUT_TOKENS", 3500))
DEEPGRAM_MODEL = "nova-3"


def normalize_deepgram_model(model: str) -> str:
    _ = model
    return DEEPGRAM_MODEL


def get_deepgram_model() -> str:
    return DEEPGRAM_MODEL


def _log_deepgram_debug(label: str, **fields) -> None:
    if not st.session_state.get("debug_mode"):
        return
    parts = [f"{key}={value}" for key, value in fields.items()]
    st.caption(f"🔍 Deepgram · {label}: " + ", ".join(parts))


INCOMPLETE_TAIL_TOKENS = {
    "від", "для", "про", "на", "до", "з", "зі", "у", "в",
    "по", "за", "без", "над", "під", "між", "через", "серед", "біля",
    "і", "та", "й", "або", "чи", "але", "бо", "що", "щоб", "аби",
    "якщо", "коли", "тому", "проте", "однак",
}

CLIENT_BACKCHANNEL_TOKENS = {
    "так", "угу", "ага", "добре", "дякую", "да", "ок", "окей",
    "зрозумів", "зрозуміла", "зрозуміло", "ясно", "аха", "еге",
    "м", "мм", "ммм", "хм", "ага-ага",
}

GARBAGE_TOKENS = {
    "шокамінь", "шокамень",
    "бездезрозум", "бездезрозуміло",
}


def _clean_token(token: str) -> str:
    return token.strip(".,!?:;—–-()[]«»\"'`").lower()


def _last_token(content: str) -> str:
    words = content.split()
    for word in reversed(words):
        cleaned = _clean_token(word)
        if cleaned:
            return cleaned
    return ""


def _ends_with_incomplete_tail(content: str) -> bool:
    return _last_token(content) in INCOMPLETE_TAIL_TOKENS


def _is_client_backchannel(content: str, max_words: int = 3) -> bool:
    words = [_clean_token(w) for w in content.split()]
    words = [w for w in words if w]
    if not words or len(words) > max_words:
        return False
    return all(w in CLIENT_BACKCHANNEL_TOKENS for w in words)


def _strip_garbage_tokens(content: str) -> str:
    kept = []
    for word in content.split():
        if _clean_token(word) in GARBAGE_TOKENS:
            continue
        kept.append(word)
    return " ".join(kept)


def _parse_line(line: str):
    stripped = line.strip()
    if not stripped:
        return None
    if ":" not in stripped:
        return ("", stripped)
    speaker, content = stripped.split(":", 1)
    speaker = speaker.strip()
    content = content.strip()
    if not content:
        return None
    return (speaker, content)


def _format_line(speaker: str, content: str) -> str:
    return f"{speaker}: {content}" if speaker else content


def merge_short_fragments(text: str, max_fragment_words: int = 4) -> str:
    if not text:
        return text

    parsed = []
    for raw_line in text.splitlines():
        item = _parse_line(raw_line)
        if item is None:
            continue
        speaker, content = item
        if speaker:
            content = _strip_garbage_tokens(content)
            if not content:
                continue
        parsed.append((speaker, content))

    merged_same_speaker = []
    for speaker, content in parsed:
        if merged_same_speaker and speaker:
            prev_speaker, prev_content = merged_same_speaker[-1]
            if prev_speaker == speaker:
                prev_word_count = len(prev_content.split())
                if (
                    prev_word_count <= max_fragment_words
                    or _ends_with_incomplete_tail(prev_content)
                ):
                    merged_same_speaker[-1] = (
                        speaker,
                        f"{prev_content} {content}".strip(),
                    )
                    continue
        merged_same_speaker.append((speaker, content))

    result = []
    i = 0
    while i < len(merged_same_speaker):
        if i + 2 < len(merged_same_speaker):
            sp0, ct0 = merged_same_speaker[i]
            sp1, ct1 = merged_same_speaker[i + 1]
            sp2, ct2 = merged_same_speaker[i + 2]
            if (
                sp0
                and sp0 == sp2
                and sp1
                and sp1 != sp0
                and _ends_with_incomplete_tail(ct0)
                and _is_client_backchannel(ct1)
            ):
                result.append((sp0, f"{ct0} {ct2}".strip()))
                result.append((sp1, ct1))
                i += 3
                continue
        result.append(merged_same_speaker[i])
        i += 1

    return "\n".join(_format_line(sp, ct) for sp, ct in result)


def post_process_transcript(text: str) -> str:
    if not text:
        return text
    text = re.sub(r" {2,}", " ", text)
    negation_fixes = [
        (r"\bненайд", "не найд"),
        (r"\bнемож", "не мож"),
        (r"\bнехоч", "не хоч"),
        (r"\bнезруч", "не зруч"),
        (r"\bнепотріб", "не потріб"),
    ]
    for pattern, replacement in negation_fixes:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def render_call_url_input(idx: int, form_key: str) -> str:
    return str(st.text_input("🔗 Посилання", key=f"url_{form_key}_{idx}") or "").strip()


def has_call_url(call: dict) -> bool:
    return bool(str(call.get("url") or "").strip())


def format_transcript_timing(seconds) -> str:
    try:
        total = max(0, int(float(seconds or 0)))
    except (TypeError, ValueError):
        total = 0
    return f"{total // 60}:{total % 60:02d}"


def _format_timed_speaker_line(speaker: str, text: str, start_seconds=None) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if start_seconds is None:
        return f"{speaker}: {text}"
    return f"{speaker}: [{format_transcript_timing(start_seconds)}] {text}"


def _join_transcript_lines(lines) -> str:
    return post_process_transcript("\n".join(line for line in lines if line))


def _count_manager_long_pauses(all_words, manager_channel="ch_0", threshold=3.0):
    manager_words = [w for w in all_words if w.get("speaker") == manager_channel]
    if len(manager_words) < 2:
        return 0
    count = 0
    for i in range(1, len(manager_words)):
        prev_end = manager_words[i - 1]["end"]
        curr_start = manager_words[i]["start"]
        gap = curr_start - prev_end
        if gap >= threshold:
            has_client_between = any(
                w.get("speaker") != manager_channel
                and prev_end <= w["start"] <= curr_start
                for w in all_words
            )
            if not has_client_between:
                count += 1
    return count


def _parse_deepgram_response(data: dict) -> dict:
    duration = data.get("metadata", {}).get("duration", 0.0)
    results = data.get("results", {})
    channels = results.get("channels", [])
    utterances = results.get("utterances", [])

    if utterances:
        plain_lines = []
        timed_lines = []
        for utterance in utterances:
            channel = utterance.get("channel")
            speaker_id = utterance.get("speaker", 0)
            if channel is not None:
                speaker = f"ch_{channel}"
            else:
                speaker = f"ch_{speaker_id}"
            text = (utterance.get("transcript", "") or "").strip()
            if not text:
                continue
            plain_lines.append(f"{speaker}: {text}")
            timed_lines.append(
                _format_timed_speaker_line(speaker, text, utterance.get("start"))
            )
        if plain_lines:
            transcript_text = _join_transcript_lines(plain_lines)
            return {
                "ok": True,
                "error": "",
                "transcript": transcript_text,
                "timestamped_transcript": _join_transcript_lines(timed_lines),
                "duration": duration,
                "long_pause_count": 0,
            }

    all_words = []
    for ch_index, ch in enumerate(channels):
        alternatives = ch.get("alternatives", [])
        if not alternatives:
            continue
        for word in alternatives[0].get("words", []):
            all_words.append(
                {
                    "word": word.get("word", ""),
                    "start": word.get("start", 0),
                    "end": word.get("end", 0),
                    "speaker": f"ch_{ch_index}",
                }
            )

    if not all_words:
        fallback_lines = []
        for ch_index, ch in enumerate(channels):
            alternatives = ch.get("alternatives") or []
            if not alternatives:
                continue
            text = (alternatives[0].get("transcript") or "").strip()
            if text:
                fallback_lines.append(f"ch_{ch_index}: {text}")
        if fallback_lines:
            transcript_text = post_process_transcript("\n".join(fallback_lines))
            return {
                "ok": True,
                "error": "",
                "transcript": transcript_text,
                "timestamped_transcript": transcript_text,
                "duration": duration,
                "long_pause_count": 0,
            }
        if duration and duration > 0:
            error = (
                f"Deepgram не знайшов мовлення в аудіо "
                f"(тривалість {float(duration):.1f} с, каналів {len(channels)})"
            )
        else:
            error = (
                "Deepgram не розпізнав аудіо — перевірте формат файлу "
                f"(каналів {len(channels)})"
            )
        return {"ok": False, "error": error, "transcript": None, "duration": duration}

    all_words.sort(key=lambda x: x["start"])
    plain_lines = []
    timed_lines = []
    current_speaker = all_words[0]["speaker"]
    current_phrase = []
    phrase_start = all_words[0]["start"]
    last_end = all_words[0]["end"]

    for word in all_words:
        speaker = word["speaker"]
        pause = word["start"] - last_end
        if speaker != current_speaker or pause > 1.0:
            if current_phrase:
                phrase = " ".join(current_phrase)
                plain_lines.append(f"{current_speaker}: {phrase}")
                timed_lines.append(
                    _format_timed_speaker_line(current_speaker, phrase, phrase_start)
                )
            current_phrase = []
            current_speaker = speaker
            phrase_start = word["start"]
        current_phrase.append(word["word"])
        last_end = word["end"]

    if current_phrase:
        phrase = " ".join(current_phrase)
        plain_lines.append(f"{current_speaker}: {phrase}")
        timed_lines.append(
            _format_timed_speaker_line(current_speaker, phrase, phrase_start)
        )

    transcript_text = _join_transcript_lines(plain_lines)
    long_pause_count = _count_manager_long_pauses(
        all_words,
        manager_channel="ch_0",
        threshold=3.0,
    )
    return {
        "ok": True,
        "error": "",
        "transcript": transcript_text,
        "timestamped_transcript": _join_transcript_lines(timed_lines),
        "duration": duration,
        "long_pause_count": long_pause_count,
    }


def _build_deepgram_params(model, keyterms=()):
    model = normalize_deepgram_model(model)
    base_params = {
        "model": model,
        "smart_format": "true",
        "punctuate": "true",
        "utterances": "true",
        "multichannel": "true",
        "language": "multi",
        "detect_language": "true",
        "language_hints": ["uk", "ru", "en"],
    }
    keyterm_params = [("keyterm", term) for term in (keyterms or ())]
    return list(base_params.items()) + keyterm_params


def _request_deepgram(*, url, keyterms=(), model="nova-3"):
    model = normalize_deepgram_model(model)
    params = _build_deepgram_params(model, keyterms)
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
    response = requests.post(
        "https://api.deepgram.com/v1/listen",
        headers=headers,
        params=params,
        json={"url": url},
        timeout=60,
    )
    if response.status_code != 200:
        return {
            "ok": False,
            "error": f"Deepgram error: {response.text}",
            "transcript": None,
            "duration": 0.0,
        }
    return _parse_deepgram_response(response.json())


def _transcribe_audio_impl(url, keyterms=(), model="nova-3"):
    if not url:
        return {"ok": False, "error": "empty url", "transcript": None, "duration": 0.0}
    try:
        return _request_deepgram(url=url, keyterms=keyterms, model=model)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Transcription exception: {str(exc)}",
            "transcript": None,
            "duration": 0.0,
            "long_pause_count": 0,
        }


class TranscriptionFailed(RuntimeError):
    """Помилка транскрипції — не кешується."""


@st.cache_data(ttl=86400, show_spinner=False)
def transcribe_audio_cached(url, keyterms=(), model="nova-3"):
    result = _transcribe_audio_impl(url, keyterms, model=model)
    if not result.get("ok"):
        raise TranscriptionFailed(result.get("error") or "Невідома помилка транскрипції")
    return result


if st.session_state.pop("_clear_transcript_cache", False):
    transcribe_audio_cached.clear()
    st.success("Кеш транскрипцій очищено")


def transcribe_audio(url, keyterms=(), model=None):
    if not str(url or "").strip():
        return None, 0.0, 0, "empty url", ""
    model = model or get_deepgram_model()
    try:
        result = transcribe_audio_cached(url, keyterms=tuple(keyterms), model=model)
    except TranscriptionFailed as exc:
        error = str(exc)
        st.error(error)
        _log_deepgram_debug("url", model=model, url=url, error=error)
        return None, 0.0, 0, error, ""
    _log_deepgram_debug(
        "url",
        model=model,
        url=url,
        duration=result.get("duration", 0.0),
        chars=len(result.get("transcript") or ""),
    )
    transcript = result.get("transcript") or ""
    timestamped = result.get("timestamped_transcript") or transcript
    return (
        transcript,
        result.get("duration", 0.0),
        result.get("long_pause_count", 0),
        None,
        timestamped,
    )


def transcribe_call_audio(call, keyterms=(), model=None):
    url = str(call.get("url") or "").strip()
    if not url:
        error = "Не вказано посилання на аудіо"
        st.error(error)
        return None, 0.0, 0, error, ""
    return transcribe_audio(url, keyterms=keyterms, model=model)


def _transcript_cache_key(raw_transcript, cache_version, manager_name, project_name, preserve_literal_names):
    payload = "|".join(
        [
            str(cache_version),
            str(manager_name),
            str(project_name),
            str(preserve_literal_names),
            str(raw_transcript),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_persisted_cleaned_transcript(cache_key):
    try:
        from supabase_logger import get_supabase_client

        client_sb, _err = get_supabase_client()
        if client_sb is None:
            return None
        res = (
            client_sb.table("cleaned_transcripts")
            .select("cleaned_text")
            .eq("cache_key", cache_key)
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        if rows:
            return rows[0].get("cleaned_text")
    except Exception:
        pass
    return None


def _save_persisted_cleaned_transcript(cache_key, cleaned_text):
    try:
        from supabase_logger import get_supabase_client

        client_sb, _err = get_supabase_client()
        if client_sb is None:
            return
        client_sb.table("cleaned_transcripts").upsert(
            {"cache_key": cache_key, "cleaned_text": cleaned_text}
        ).execute()
    except Exception:
        pass


@st.cache_data(ttl=86400, show_spinner=False)
def clean_transcript_cached(
    raw_transcript,
    cache_version,
    manager_name="",
    project_name="",
    preserve_literal_names=False,
):
    if not raw_transcript:
        return raw_transcript

    cache_key = _transcript_cache_key(
        raw_transcript, cache_version, manager_name, project_name, preserve_literal_names
    )
    persisted = _load_persisted_cleaned_transcript(cache_key)
    if persisted is not None:
        return persisted

    try:
        res = client.chat.completions.create(
            model=OPENAI_TRANSCRIPT_MODEL,
            temperature=0,
            max_completion_tokens=3000,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ти — редактор транскриптів телефонних дзвінків. "
                        "Твоє завдання — виправити транскрипт не змінюючи змісту розмови.\n\n"
                        "При форматуванні транскрипту:\n"
                        "- Виправляй очевидні помилки узгодження: неправильний відмінок, рід, число "
                        "якщо з контексту однозначно зрозуміло правильний варіант "
                        "('ваші менеджер' → 'ваш менеджер', 'сайтом Вегас' → 'сайту Вегас', "
                        "'Мене Віктор звати' → 'Мене звати Віктор', 'я ваші менеджер' → 'я ваш менеджер')\n"
                        "- НЕ виправляй: сенс фраз, не додавай слова, не міняй порядок речень\n"
                        "- НЕ виправляй: навмисні паузи, повторення (вони важливі для аналізу)\n\n"
                        "Правила:\n"
                        "1. Виправ очевидні помилки розпізнавання: злипання слів, спотворені слова, фонетичні заміни\n"
                        "2. Перейменуй спікерів: ch_0 → Менеджер, ch_1 → Клієнт. "
                        "КРИТИЧНО: ch_0 і ch_1 — це РІЗНІ люди. ch_0 завжди Менеджер, ch_1 завжди Клієнт. "
                        "Ніколи не міняй цей порядок. Якщо репліка починається з ch_1: — це завжди Клієнт, навіть якщо там коротка відповідь.\n"
                        "3. Збережи формат діалогу: кожна репліка з нового рядка у форматі "
                        "'Спікер: текст' або 'Спікер: [M:SS] текст'. "
                        "Якщо у вхідному рядку є маркер таймінгу [M:SS] / [MM:SS] — обов'язково збережи його "
                        "одразу після імені спікера (приклад: 'Менеджер: [0:42] Добрий день'). "
                        "Не вигадуй і не змінюй таймінги.\n"
                        "4. Не додавай, не прибирай і не перефразовуй репліки — тільки виправляй помилки\n"
                        "5. Поверни тільки виправлений транскрипт без коментарів\n"
                        "6. Якщо одна думка ОДНОГО І ТОГО САМОГО спікера розбита на декілька коротких рядків підряд — склей їх в одну репліку. "
                        "КРИТИЧНО: ніколи не склеюй репліки РІЗНИХ спікерів. "
                        "Менеджер: текст і Клієнт: текст — це завжди окремі рядки навіть якщо вони короткі. "
                        "Наприклад: 'Менеджер: мене\\nМенеджер: звати\\nМенеджер: Ольга' → 'Менеджер: мене звати Ольга'\n"
                        "7. Числа пиши цифрами: 'двісті п'ятдесят' → '250', 'сорок вісім годин' → '48 годин'\n"
                        "8. Часові вирази: 'о п'ятій' → 'о 17:00', 'після шостої' → 'після 18:00', 'з дванадцяти до тринадцяти' → 'з 12:00 до 13:00'\n"
                        + (
                            "9. Не замінюй імена менеджерів і назви сайту/проєктів — залиш як у транскрипті.\n"
                            if preserve_literal_names
                            else (
                                "9. Назви проєктів — тільки ці три варіанти: '777', 'Betking', 'Vegas'. "
                                "Якщо чуєш схоже — виправляй: '777-сім', '777 сім', 'три сімки' → '777'; "
                                "'беткінг', 'бетінг', 'веткінг', 'бетківг' → 'Betking'; "
                                "'вегас', 'веджас', 'Zegas', 'Vegy' → 'Vegas'. "
                                "УВАГА: слово 'вейджер' у значенні умови бонусу ('без вейджера', 'вейджер x30', 'відіграш') — НЕ замінювати на 'Vegas'. "
                                "'вейджер' замінювати на 'Vegas' тільки якщо це назва сайту або проєкту ('менеджер Vegas', 'сайт Vegas').\n"
                            )
                        )
                        + "10. Репліки коротше 3 слів ('так', 'а', 'угу', 'о') — приєднуй до попередньої репліки того ж спікера якщо вона є\n"
                        + (
                            ""
                            if preserve_literal_names
                            else (
                                "11. Імена менеджерів: правильне ім'я менеджера цього дзвінка: "
                                + (manager_name if manager_name else "невідомо")
                                + ". Менеджер — це завжди ch_0. "
                                "У перших 5 репліках ch_0 менеджер може називати своє ім'я — воно майже завжди спотворене ASR. "
                                "Знайди у цих репліках будь-яке слово або звукосполучення яке стоїть після 'мене звати', 'я — ', 'це — ', 'я з', 'менеджер', або стоїть окремо як ім'я — "
                                "і заміни його на зазначене ім'я. "
                                + "Навіть якщо спотворений варіант зовсім не схожий фонетично — все одно заміняй: ASR може спотворювати імена до невпізнання. "
                                "Якщо ім'я не знайдено у перших 5 репліках — не додавай його самостійно.\n"
                            )
                        )
                        + (
                            ""
                            if preserve_literal_names or not project_name
                            else (
                                f"12. Назва сайту/казино цього дзвінка: {project_name}. "
                                "Якщо в транскрипті зустрічається спотворена назва сайту — виправляй до цієї назви. "
                                "Наприклад: 'сайту вейджер' → 'сайту Vegas', 'беткінг' → 'Betking', 'три сімки' → '777'.\n"
                            )
                        )
                        + (
                            "12. Виправляй фонетичні помилки ASR: слова, що звучать близько до розпізнаного, але за змістом фрази очевидно інші "
                            "('бонас' → 'бонус', 'деп ступ' → 'депозит', 'фрі спин' → 'фріспін')\n"
                        )
                        + (
                            "13. Реконструюй спотворені слова по контексту: якщо слово виглядає як ASR-сміття, але сусідні слова дають однозначне значення — "
                            "відновлюй правильну форму (не вгадуй, якщо контекст неоднозначний)\n"
                        )
                        + (
                            "14. Видаляй беззмістовні ASR-артефакти: одиночні склади/літери, що не утворюють слів ('ммм', 'еее', 'шш', обірвані буквосполучення "
                            "без змісту типу 'кр', 'пр', 'зв') — якщо вони стоять окремо і не є частиною слова\n"
                            "15. Склеюй обірвані фрази в одну завершену репліку, якщо за змістом видно, що це одна думка одного спікера, навіть якщо "
                            "між ними була пауза\n"
                            "16. Виправляй контекстно абсурдні слова: якщо слово граматично існує, але за контекстом очевидно інше — "
                            "заміняй на контекстно коректну форму. "
                            "Приклади: 'телефонуй' (наказова) у репліці менеджера 'я телефонуй з приводу бонусу' → 'я телефоную з приводу бонусу'; "
                            "'лімітований бонус' у контексті 'діє 48 годин' часто означає 'лімітований у часі бонус' або '48-годинний бонус' — "
                            "обирай контекстно коректний варіант. Не заміняй, якщо контекст неоднозначний\n"
                            "17. Якщо слово виглядає як спотворений іменник або дієслово у контексті "
                            "телефонного дзвінка казино — реконструюй по контексту речення. "
                            "Приклади типових спотворень Deepgram для змішаного укр/рос мовлення: "
                            "'картук' → 'карток', 'оборонена' → 'заборонена', 'непризивной спины' → 'безкоштовних спінів', "
                            "'отжиграшу' → 'відіграшу', 'ФС' → 'фріспінів'. "
                            "Загальне правило: якщо слово фонетично схоже на терміни казино/бонусів — відновлюй коректну форму.\n"
                        )
                    ),
                },
                {"role": "user", "content": raw_transcript},
            ],
        )
        cleaned_text = res.choices[0].message.content.strip()
        _save_persisted_cleaned_transcript(cache_key, cleaned_text)
        return cleaned_text
    except Exception as e:
        st.warning(f"Помилка обробки транскрипту: {e}")
        return raw_transcript


def apply_replacements(text, replacements):
    if not text:
        return text
    for k, v in replacements.items():
        pattern = re.compile(rf"(?<!\w){re.escape(k)}(?!\w)", re.IGNORECASE)
        if pattern.search(text):
            text = pattern.sub(v, text)
    return text
