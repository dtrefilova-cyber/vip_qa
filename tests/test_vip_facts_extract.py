"""Тести AI-екстракції фактів VIP (без реальних GPT-викликів)."""

import json

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


# Репрезентативні хибнопозитивні короткі дзвінки 14–16.09.2026 (critical=так без «зливу»).
_FP_TRANSCRIPTS = {
    "1239106": """
Менеджер: Добрий день, Віктор. Вадим з Betking. Буде хвилинка.
Клієнт: Алло. Да, да.
Менеджер: Як там? Як справи? Бережіть себе обов'язково.
Клієнт: Так себе.
Менеджер: Є слот, як Бананос. Там 45 бонусок буде. Сьогодні ж будете грати так на депозит.
Клієнт: Не знаєш.
Менеджер: Раджу якраз саме сьогодні завітати. Можливо, є додатково питання до мене.
Клієнт: Не, не,
Менеджер: Тут будуть проблеми. Звертайтесь. Дякую вам.
Клієнт: До побачення.
Менеджер: До побачення.
""".strip(),
    "8140682": """
Клієнт: Аллоло.
Менеджер: Добрий день, Богдане. Це Нікіта. Як завжди на півтори хвилинки нарахувати бонуси. Добре?
Менеджер: Ой так, Богдане, як я розумію, так і не змогли ви вивести гроші.
Клієнт: В мене і більші були, на вашому в рази більші були, і ніхто ж не просили.
Менеджер: Так. Ну, а тут фінвідділ просто вирішив, ну, перевірити вас ще раз.
Клієнт: Просто вирішив, щоб це не зробити. Ви ж розумієте, ні на що це робиться. Давайте не будемо про це. Не вийшло, то не вийшло.
Клієнт: Я ні від кого такого не чув, тільки від вас.
Менеджер: Так, ви сьогодні будете грати на сайті?
Клієнт: Добренько. Дякую. Немає відсутній. Ви так і нічого не зробили?
Клієнт: Я відправив і нічого не сталося. Добре. Дякую, Нікіта. На зв'язку.
""".strip(),
    "3960004": """
Менеджер: Алло, Іван. Доброго ранку. То ваш Микола. Підключуємо сьогодні всі види бонусів.
Клієнт: Та нормально. Все гаразд. Все встигаєте. До речі, якась спека вже прийшла.
Клієнт: У нас хмарно, вітер, сьогодні дощ, напевно, буде. Думали, що буде тривога, але не було.
Клієнт: Добре. Нема. Хорошого дня вам. Дякую.
Менеджер: Супер. Класного дня. Дякую.
""".strip(),
    "9487342": """
Клієнт: Алло.
Менеджер: Алло, доброго дня, Назаре. Це Надія, ваш менеджер. Як ви?
Клієнт: Відпустці я.
Клієнт: Ні, це погано.
Клієнт: Ні, я потрапив у відпустку через машину, нам у реанімації лежить.
Клієнт: Біда.
Менеджер: Боже, тримайтеся. Я просто не знала. Я вибачаюсь.
Менеджер: Тоді давайте так, щоб я вас все не напрягала зараз своїми розмовами, вам не до цього.
Менеджер: Якщо захочете пограти, ви мені напишіть. Все, бережіть себе. Гарного вам дня.
Клієнт: Поняв.
""".strip(),
}


def _hallucinated_critical_payload(quote: str = "") -> dict:
    return {
        "contact": {
            "greeted": True,
            "used_client_name": True,
            "named_project": True,
            "availability_check_relevant": False,
            "availability_check_done": False,
        },
        "slip_handling": {"client_attempted_to_end_call": False},
        "slip_critical": {
            "continued_pitch_after_client_said_cannot_talk": True,
            "asked_irrelevant_questions": True,
            "artificially_extended_call": True,
            "ended_without_using_available_retention_options": True,
            "critical_evidence_quote": quote,
        },
        "prep": {"objections_present": False, "objections": []},
        "closing": {
            "asked_if_more_questions": True,
            "said_goodbye": True,
            "thanked_and_left_contact_open": True,
        },
        "shared_context": {},
    }


@pytest.mark.parametrize("client_id", list(_FP_TRANSCRIPTS))
def test_false_positive_critical_calls_stay_non_critical_without_leak_quote(client_id):
    from core.vip_short_scoring import score_vip_short_call
    from vip_short_ai_assistant import extract_vip_short_90s_facts

    dialogue = _FP_TRANSCRIPTS[client_id]
    payload = _hallucinated_critical_payload("")
    client = _FakeClient([json.dumps({"facts": payload}, ensure_ascii=False)])
    facts = extract_vip_short_90s_facts(client, "model", dialogue, "", "", 200)
    result = score_vip_short_call(facts, dialogue=dialogue)
    assert result["is_critical_fail"] is False, client_id
    assert result["total_score"] > 0, client_id


@pytest.mark.parametrize("client_id", list(_FP_TRANSCRIPTS))
def test_false_positive_critical_calls_reject_hallucinated_leak_quote(client_id):
    from core.vip_short_scoring import score_vip_short_call
    from vip_short_ai_assistant import extract_vip_short_90s_facts

    dialogue = _FP_TRANSCRIPTS[client_id]
    payload = _hallucinated_critical_payload("Я зараз не можу говорити, передзвоніть пізніше")
    client = _FakeClient([json.dumps({"facts": payload}, ensure_ascii=False)])
    facts = extract_vip_short_90s_facts(client, "model", dialogue, "", "", 200)
    result = score_vip_short_call(facts, dialogue=dialogue)
    assert result["is_critical_fail"] is False, client_id


def test_unrelated_in_transcript_quote_is_not_critical_for_8140682():
    from core.vip_short_scoring import score_vip_short_call
    from vip_short_ai_assistant import extract_vip_short_90s_facts

    dialogue = _FP_TRANSCRIPTS["8140682"]
    payload = _hallucinated_critical_payload("Давайте не будемо про це")
    client = _FakeClient([json.dumps({"facts": payload}, ensure_ascii=False)])
    facts = extract_vip_short_90s_facts(client, "model", dialogue, "", "", 200)
    result = score_vip_short_call(facts, dialogue=dialogue)
    assert result["is_critical_fail"] is False


def test_short_prompt_requires_evidence_quote_and_2_5_scale():
    from prompts_vip_short import get_vip_short_90s_analysis_prompt

    prompt = get_vip_short_90s_analysis_prompt()
    assert "critical_evidence_quote" in prompt
    assert "0 / 2,5 / 5 / 7,5 / 10" in prompt
    assert "formal=2.5" in prompt


def test_extract_friendly_retries_invalid_schema_then_succeeds(monkeypatch):
    from vip_short_ai_assistant import extract_vip_friendly_facts

    monkeypatch.setattr("vip_short_ai_assistant.time.sleep", lambda _s: None)
    bad = {
        "prep": {
            "objections_present": True,
            "objections": [{"type": "no_desire", "handling": "not-a-real-level"}],
        }
    }
    good = {"ease": {"level": "high", "signals": []}}
    client = _FakeClient(
        [
            json.dumps({"facts": bad}, ensure_ascii=False),
            json.dumps({"facts": good}, ensure_ascii=False),
        ]
    )
    facts = extract_vip_friendly_facts(client, "model", "dialogue", "", "", 100)
    assert facts["ease"]["level"] == "high"
    assert client.chat.completions.calls == 2


def test_extract_short_retries_invalid_schema_then_succeeds(monkeypatch):
    from vip_short_ai_assistant import extract_vip_short_90s_facts

    monkeypatch.setattr("vip_short_ai_assistant.time.sleep", lambda _s: None)
    bad = {
        "prep": {
            "objections_present": True,
            "objections": [{"type": "no_desire", "handling": "not-a-real-level"}],
        }
    }
    good = {"contact": {"greeted": True}}
    client = _FakeClient(
        [
            json.dumps({"facts": bad}, ensure_ascii=False),
            json.dumps({"facts": good}, ensure_ascii=False),
        ]
    )
    facts = extract_vip_short_90s_facts(client, "model", "dialogue", "", "", 100)
    assert facts["contact"]["greeted"] is True
    assert client.chat.completions.calls == 2


def test_user_safe_analysis_error_is_specific():
    from vip_short_ai_assistant import VipFactsExtractionError, user_safe_analysis_error

    assert "VIP Friendly" in user_safe_analysis_error(
        VipFactsExtractionError("Не вдалося розібрати факти VIP Friendly. Спробуйте ще раз.")
    )
    assert "таймаут" in user_safe_analysis_error(TimeoutError("read timed out")).lower()
    assert "аудіо" in user_safe_analysis_error(RuntimeError("Deepgram PAYLOAD_ERROR")).lower()
    assert "AI" in user_safe_analysis_error(RuntimeError("OpenAI 429 rate limit"))
    generic = user_safe_analysis_error(RuntimeError("boom"))
    assert "технічну помилку" in generic
    assert "повідомте розробника" in generic.lower()
