"""Speech backend contracts.

A voice assistant needs exactly three capabilities. Keeping them as Protocols
means the ESP32 firmware can later consume the same shapes, and swapping a
cloud call for an on-device one is a new class, not a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class Turn:
    """One exchange to replay as context. Providers format it their own way."""

    user: str
    reply: str


@runtime_checkable
class SpeechToText(Protocol):
    def transcribe(self, wav_path: Path) -> str:
        """Audio file -> transcript."""
        ...


@runtime_checkable
class LanguageModel(Protocol):
    def reply(self, user_text: str, history: list[Turn] | None = None) -> str:
        """User text + prior turns -> assistant text."""
        ...


@runtime_checkable
class TextToSpeech(Protocol):
    def speak(self, text: str, out_path: Path) -> Path:
        """Text -> WAV file at `out_path`."""
        ...
