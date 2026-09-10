"""Нормалізація посилань на аудіо перед Deepgram."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit, quote

_URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_DRIVE_FILE_RE = re.compile(
    r"(?:drive\.google\.com/file/d/|drive\.google\.com/open\?(?:.*&)?id=)"
    r"([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
_DRIVE_UC_ID_RE = re.compile(
    r"drive\.google\.com/uc\?(?:.*&)?id=([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


def friendly_transcribe_error(raw: str) -> str:
    text = str(raw or "")
    low = text.lower()
    if "empty url" in low or "не вказано" in low:
        return "Не вказано посилання на аудіо."
    if "payload_error" in low or "failed to parse url" in low:
        return (
            "Не вдалося прочитати посилання на аудіо. "
            "Вставте пряме http/https посилання на файл запису."
        )
    if "deepgram" in low or "err_code" in low or "transcription exception" in low:
        return "Не вдалося розпізнати аудіо. Перевірте посилання і спробуйте ще раз."
    if text.strip():
        return "Не вдалося розпізнати аудіо. Перевірте посилання і спробуйте ще раз."
    return "Не вдалося розпізнати аудіо."


def _clean_cell(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return text.replace("\ufeff", "").strip()


def _drive_file_id(url: str) -> str | None:
    for pattern in (_DRIVE_FILE_RE, _DRIVE_UC_ID_RE):
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def _to_drive_direct(url: str) -> str:
    file_id = _drive_file_id(url)
    if not file_id:
        return url
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def _to_dropbox_direct(url: str) -> str:
    if "dropbox.com" not in url.lower():
        return url
    if "dl=0" in url:
        return url.replace("dl=0", "dl=1")
    if "dl=1" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}dl=1"


def _encode_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc
    try:
        netloc = netloc.encode("idna").decode("ascii")
    except Exception:
        pass
    path = quote(unquote(parts.path), safe="/-_.~:@")
    query = urlencode(parse_qsl(parts.query, keep_blank_values=True), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_audio_url(raw: str) -> str:
    """Прибирає сміття з вставленого лінка і робить URL придатним для Deepgram."""
    text = _clean_cell(raw).strip("<>\"'`")
    text = text.replace("\r", "").replace("\n", "").replace("\t", "")
    text = text.strip()
    if not text:
        return ""

    match = _URL_RE.search(text)
    if match:
        text = match.group(0)
    elif re.match(r"(?i)^(www\.|drive\.google\.com|dropbox\.com)", text):
        text = "https://" + text.lstrip()
        match = _URL_RE.search(text)
        text = match.group(0) if match else text
    else:
        return ""

    text = text.rstrip(".,;)]}>\"'")
    text = text.replace(" ", "")
    text = _to_drive_direct(text)
    text = _to_dropbox_direct(text)
    encoded = _encode_url(text)
    parts = urlsplit(encoded)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return encoded
