"""Тести AI-екстракції фактів VIP (без реальних GPT-викликів)."""

import pytest

from vip_short_ai_assistant import VipFactsExtractionError, _call_gpt_json, _extract_json_object


def test_extract_json_object_nested_and_plain():
    assert _extract_json_object('{"a": 1}') == {"a": 1}
    assert _extract_json_object('prefix {"facts": {"x": true}} suffix') == {
        "facts": {"x": True}
    }
    assert _extract_json_object("not json") is None


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, contents):
        self._contents = list(contents)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if not self._contents:
            raise RuntimeError("no more responses")
        return _FakeResponse(self._contents.pop(0))


class _FakeChat:
    def __init__(self, contents):
        self.completions = _FakeCompletions(contents)


class _FakeClient:
    def __init__(self, contents):
        self.chat = _FakeChat(contents)


def test_call_gpt_json_returns_facts_payload():
    client = _FakeClient(['{"facts": {"contact": {"greeted": true}}}'])
    out = _call_gpt_json(client, "model", "prompt", "dialogue", 100)
    assert out == {"contact": {"greeted": True}}


def test_call_gpt_json_raises_after_retries():
    client = _FakeClient(["not-json", "still-bad"])
    with pytest.raises(VipFactsExtractionError):
        _call_gpt_json(client, "model", "prompt", "dialogue", 100)
    assert client.chat.completions.calls == 2
