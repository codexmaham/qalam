"""Local transcription and the homework-from-voice path."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qalam.main import create_app
from qalam.models import RenderRequest
from qalam.notebook import NotebookRenderer
from qalam.voice import Transcript, VoiceError, WhisperTranscriber, app_language_for, whisper_language_for

FIXTURE = Path(__file__).parent / "fixtures" / "hello.wav"
KNOWN = {"en", "ur", "hi", "ar", "zh-hans", "pa-guru", "pa-arab", "fil"}


def test_whisper_codes_map_onto_app_languages():
    assert app_language_for("en", KNOWN) == "en"
    assert app_language_for("ur", KNOWN) == "ur"
    assert app_language_for("hi", KNOWN) == "hi"
    assert app_language_for("ar", KNOWN) == "ar"
    assert app_language_for("zh", KNOWN) == "zh-hans"
    assert app_language_for("pa", KNOWN) == "pa-guru"
    assert app_language_for("tl", KNOWN) == "fil"
    assert app_language_for("xx", KNOWN) == ""
    assert whisper_language_for("zh-hans") == "zh"
    assert whisper_language_for("pa-guru") == "pa"
    assert whisper_language_for("pa-arab") == "pa"
    assert whisper_language_for("fil") == "tl"
    assert whisper_language_for(None) is None


def test_english_only_weights_are_refused(monkeypatch):
    monkeypatch.setenv("QALAM_WHISPER_MODEL", "base.en")
    status = WhisperTranscriber().status()
    assert status["ready"] is False
    assert status["private"] is True
    assert "English-only" in status["error"]
    with pytest.raises(VoiceError):
        WhisperTranscriber(model="tiny.en")


def test_fixture_is_a_short_wav():
    data = FIXTURE.read_bytes()
    assert data[:4] == b"RIFF"
    assert len(data) < 200_000
    with wave.open(str(FIXTURE)) as audio:
        assert audio.getnchannels() == 1
        assert audio.getframerate() == 16000
        seconds = audio.getnframes() / audio.getframerate()
    assert 0.5 < seconds < 5


class _FakeVoice:
    def status(self) -> dict:
        return {"ready": True, "private": True, "model": "fake", "device": "cpu"}

    def transcribe(self, data: bytes, suffix: str, language_id: str | None, known_ids: set[str]) -> Transcript:
        assert data[:4] == b"RIFF"
        assert suffix == ".wav"
        assert language_id in (None, "")
        assert "en" in known_ids
        return Transcript(
            text="Hello from the notebook.",
            whisper_language="en",
            language_id="en",
            model="fake",
        )


def test_voice_api_writes_the_transcript_into_the_notebook():
    client = TestClient(create_app(_FakeVoice()))
    status = client.get("/api/voice")
    assert status.status_code == 200
    assert status.json()["private"] is True
    spoken = client.post(
        "/api/transcribe",
        files={"file": ("hello.wav", FIXTURE.read_bytes(), "audio/wav")},
        data={"language": ""},
    )
    assert spoken.status_code == 200
    body = spoken.json()
    assert body["text"] == "Hello from the notebook."
    assert body["language_id"] == "en"
    assert body["template"] == "four-line"
    preview = client.post(
        "/api/preview",
        json={
            "text": body["text"],
            "language": body["language_id"],
            "template": body["template"],
            "ink": "sample",
            "style": "school-neat",
        },
    )
    assert preview.status_code == 200
    assert preview.json()["page_count"] == 1
    page = NotebookRenderer().render(
        RenderRequest(
            text=body["text"],
            language_id="en",
            template_id="four-line",
            style_id="school-neat",
            ink_id="sample",
            dpi=72,
        )
    )
    assert page.width > 100
    assert page.pages


def test_tiny_model_hears_the_fixture():
    transcriber = WhisperTranscriber(model="tiny")
    heard = []
    try:
        for _ in range(2):
            heard.append(transcriber.transcribe(FIXTURE.read_bytes(), ".wav", None, KNOWN))
    except VoiceError as exc:
        message = str(exc).lower()
        if any(word in message for word in ("install", "download", "open", "whisper", "connect", "network")):
            pytest.skip(str(exc))
        raise
    for result in heard:
        assert result.language_id == "en"
        assert result.model == "tiny"
        lowered = result.text.lower()
        assert "hello" in lowered or "notebook" in lowered
