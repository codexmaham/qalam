"""Local speech-to-text for the Voice page.

Whisper runs on this computer through faster-whisper (CTranslate2, int8).
Audio is not sent anywhere. The default model is the multilingual base,
which fits an 8 GB Mac next to the browser. QALAM_WHISPER_MODEL can be
tiny, base, or small. English-only weights (names ending in .en) are refused.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Whisper's language code is not always the app's language id.
_WHISPER_TO_APP = {
    "zh": "zh-hans",
    "pa": "pa-guru",
    "tl": "fil",
}

_APP_TO_WHISPER = {
    "zh-hans": "zh",
    "pa-guru": "pa",
    "pa-arab": "pa",
    "fil": "tl",
}

DEFAULT_MODEL = "base"
ALLOWED_MODELS = {"tiny", "base", "small"}
_AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac", ".mp4", ".mpeg", ".mpga"}


class VoiceError(Exception):
    """The recording could not be transcribed on this computer."""


@dataclass
class Transcript:
    text: str
    whisper_language: str
    language_id: str
    model: str


def model_name() -> str:
    name = os.environ.get("QALAM_WHISPER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    if name.endswith(".en"):
        raise VoiceError(
            f"QALAM_WHISPER_MODEL={name} is English-only. "
            "Use tiny, base, or small so Urdu, Hindi, and Arabic still work."
        )
    if name not in ALLOWED_MODELS:
        raise VoiceError(f"QALAM_WHISPER_MODEL={name} is not one of tiny, base, small.")
    return name


def model_dir() -> Path:
    raw = os.environ.get("QALAM_WHISPER_DIR", "").strip()
    path = Path(raw).expanduser() if raw else Path.home() / ".cache" / "qalam" / "whisper"
    path.mkdir(parents=True, exist_ok=True)
    return path


def app_language_for(code: str, known_ids: set[str]) -> str:
    """Map a Whisper language code onto an app language id, or ''."""

    short = (code or "").lower().split("-")[0]
    mapped = _WHISPER_TO_APP.get(short, short)
    if mapped in known_ids:
        return mapped
    return ""


def whisper_language_for(language_id: str | None) -> str | None:
    if not language_id:
        return None
    return _APP_TO_WHISPER.get(language_id, language_id)


def setup_hint(name: str) -> str:
    return (
        f"Could not open the Whisper {name} model. "
        "The first transcription downloads it into ~/.cache/qalam/whisper "
        "(or QALAM_WHISPER_DIR). Check the network once, then it stays on this computer. "
        "Set QALAM_WHISPER_MODEL to tiny, base, or small."
    )


class WhisperTranscriber:
    """Lazy faster-whisper. Importing the app does not download weights."""

    def __init__(self, model: str | None = None) -> None:
        if model and model.endswith(".en"):
            raise VoiceError(
                f"Model {model} is English-only. Use tiny, base, or small so every notebook language still works."
            )
        self._explicit = model
        self._loaded = None
        self._loaded_name = ""

    def _name(self) -> str:
        if self._explicit:
            if self._explicit not in ALLOWED_MODELS:
                raise VoiceError(f"Model {self._explicit} is not one of tiny, base, small.")
            return self._explicit
        return model_name()

    def status(self) -> dict:
        try:
            name = self._name()
        except VoiceError as exc:
            return {"ready": False, "private": True, "model": "", "error": str(exc), "device": "cpu"}
        return {
            "ready": True,
            "private": True,
            "model": name,
            "device": "cpu",
            "compute": "int8",
            "note": "Audio stays on this computer.",
        }

    def transcribe(
        self,
        data: bytes,
        suffix: str,
        language_id: str | None,
        known_ids: set[str],
    ) -> Transcript:
        name = self._name()
        wav_path = _to_wav(data, suffix or ".webm")
        try:
            audio = _pcm(wav_path)
        finally:
            Path(wav_path).unlink(missing_ok=True)
        try:
            model = self._ensure(name)
            forced = whisper_language_for(language_id) if language_id else None
            segments, info = model.transcribe(
                audio,
                language=forced,
                beam_size=5,
                vad_filter=False,
                condition_on_previous_text=False,
            )
            parts: list[str] = []
            for segment in segments:
                if getattr(segment, "no_speech_prob", 0.0) > 0.6:
                    continue
                text = (segment.text or "").strip()
                if text:
                    parts.append(text)
        except VoiceError:
            raise
        except Exception as exc:
            message = str(exc).lower()
            if any(word in message for word in ("download", "connect", "network", "huggingface", "timed out")):
                raise VoiceError(setup_hint(name)) from exc
            raise VoiceError(f"Could not transcribe that recording: {exc}") from exc
        detected = getattr(info, "language", "") or ""
        if language_id and language_id in known_ids:
            app_id = language_id
        else:
            app_id = app_language_for(detected, known_ids)
        return Transcript(
            text=" ".join(parts).strip(),
            whisper_language=detected,
            language_id=app_id,
            model=name,
        )

    def _ensure(self, name: str):
        if self._loaded is not None and self._loaded_name == name:
            return self._loaded
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise VoiceError(
                "faster-whisper is not installed. From the backend folder run: pip install -r requirements.txt"
            ) from exc
        # One thread. int8 with several threads drops or repeats words on a short clip.
        try:
            model = WhisperModel(
                name,
                device="cpu",
                compute_type="int8",
                download_root=str(model_dir()),
                cpu_threads=1,
            )
        except Exception as exc:
            raise VoiceError(setup_hint(name)) from exc
        self._loaded = model
        self._loaded_name = name
        return model


def _pcm(path: str) -> np.ndarray:
    """16 kHz mono float32, already decoded by ffmpeg so PyAV is not involved."""

    with wave.open(path, "rb") as audio:
        channels = audio.getnchannels()
        width = audio.getsampwidth()
        frames = audio.readframes(audio.getnframes())
    if width != 2 or not frames:
        raise VoiceError("Could not read that audio. Use a wav, mp3, m4a, ogg, or webm recording.")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return np.ascontiguousarray(samples)


def _to_wav(data: bytes, suffix: str) -> str:
    if not suffix.startswith("."):
        suffix = f".{suffix}" if suffix else ".webm"
    suffix = suffix.lower()
    if suffix not in _AUDIO_SUFFIXES:
        suffix = ".webm"
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise VoiceError("ffmpeg is required to read recordings. Install it, then try again.")
    source = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    target = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        source.write(data)
        source.close()
        target.close()
        try:
            proc = subprocess.run(
                [ffmpeg, "-y", "-i", source.name, "-ac", "1", "-ar", "16000", "-f", "wav", target.name],
                capture_output=True,
                timeout=120,
            )
        except FileNotFoundError as exc:
            raise VoiceError("ffmpeg is required to read recordings. Install it, then try again.") from exc
        if proc.returncode != 0 or Path(target.name).stat().st_size < 44:
            raise VoiceError("Could not read that audio. Use a wav, mp3, m4a, ogg, or webm recording.")
        return target.name
    except Exception:
        Path(target.name).unlink(missing_ok=True)
        raise
    finally:
        Path(source.name).unlink(missing_ok=True)
