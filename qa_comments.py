"""Перевірка заборонених слів у репліках менеджера."""

from __future__ import annotations

import re

from constants import FORBIDDEN_WORDS


def _normalize_forbidden_phrase(text):
    normalized = str(text or "").strip().lower()
    normalized = normalized.replace("’", "'").replace("`", "'").replace("ё", "е")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


# Артефакти транскрипції Deepgram, які схожі на заборонені слова — ігноруємо
_TRANSCRIPT_ARTIFACTS = re.compile(
    r"(?<!\w)бездем(?!\w)|(?<!\w)бездень(?!\w)"
)


def detect_forbidden_phrases_in_dialogue(dialogue):
    if not dialogue:
        return []

    manager_lines = []
    for line in str(dialogue).splitlines():
        stripped = line.strip()
        if stripped.startswith("Менеджер:") or stripped.startswith("ch_0:"):
            manager_lines.append(stripped.split(":", 1)[1].strip())

    manager_text = " ".join(manager_lines)
    if not manager_text:
        return []

    normalized_text = _normalize_forbidden_phrase(manager_text)
    cleaned_text = _TRANSCRIPT_ARTIFACTS.sub("", normalized_text)

    detected = []
    for phrase in FORBIDDEN_WORDS:
        normalized_phrase = _normalize_forbidden_phrase(phrase)
        if not normalized_phrase:
            continue
        if " " in normalized_phrase:
            matched = normalized_phrase in cleaned_text
        else:
            matched = (
                re.search(
                    rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)",
                    cleaned_text,
                )
                is not None
            )
        if matched:
            detected.append(phrase)
    return detected
