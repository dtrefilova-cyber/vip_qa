"""Tests for Supabase verdict normalization / allowed values."""

from supabase_logger import ALLOWED_VERDICTS, _normalize_verdict


def test_allowed_verdicts_match_migration_contract():
    assert ALLOWED_VERDICTS == frozenset({"GREEN", "RED", "green", "red", "scored"})


def test_normalize_verdict_passthrough():
    for value in ("scored", "GREEN", "RED", "green", "red"):
        assert _normalize_verdict(value) == value


def test_normalize_verdict_defaults_and_unknown():
    assert _normalize_verdict(None) == "scored"
    assert _normalize_verdict("") == "scored"
    assert _normalize_verdict("YELLOW") == "scored"
