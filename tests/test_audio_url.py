"""Нормалізація посилань на аудіо для Deepgram."""

from audio_url import friendly_transcribe_error, normalize_audio_url


def test_normalize_strips_quotes_and_whitespace():
    raw = '  "https://cdn.example.com/call.mp3"  \n'
    assert normalize_audio_url(raw) == "https://cdn.example.com/call.mp3"


def test_normalize_extracts_url_from_pasted_text():
    raw = "запис: https://cdn.example.com/a.wav будь ласка"
    assert normalize_audio_url(raw) == "https://cdn.example.com/a.wav"


def test_normalize_google_drive_view_to_direct():
    raw = "https://drive.google.com/file/d/AbC123_-x/view?usp=sharing"
    assert normalize_audio_url(raw) == "https://drive.google.com/uc?export=download&id=AbC123_-x"


def test_normalize_encodes_cyrillic_path():
    raw = "https://cdn.example.com/записи/дзвінок.mp3"
    out = normalize_audio_url(raw)
    assert " " not in out
    assert out.startswith("https://cdn.example.com/")
    assert "дзвінок" not in out
    assert "%D0%" in out


def test_normalize_rejects_non_url():
    assert normalize_audio_url("просто текст") == ""
    assert normalize_audio_url("") == ""


def test_friendly_error_hides_deepgram_json():
    raw = (
        'Deepgram error: {"err_code":"PAYLOAD_ERROR","err_msg":'
        '"Failed to parse URL in JSON body.","request_id":"abc"}'
    )
    msg = friendly_transcribe_error(raw)
    assert "PAYLOAD_ERROR" not in msg
    assert "request_id" not in msg
    assert "посилання" in msg.lower()
