"""Сітка карток внесення VIP-дзвінка (тільки тип «Короткий»)."""

from __future__ import annotations


def _slug(call_type: str) -> str:
    return "short"


def _keys(slug: str) -> dict[str, str]:
    return {}


def ensure_card_state(call_type: str) -> list[dict]:
    return []
