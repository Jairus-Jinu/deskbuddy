"""Provider selection.

`DESKBUDDY_PROVIDER` picks the backend:

    groq   (default) Groq Whisper STT + Groq LLM + local Piper TTS
    gemini           Gemini STT/LLM/TTS through the Interactions API

Both expose the same three methods, so nothing downstream cares which is live.
"""

from __future__ import annotations

import os

from .brain import Brain, BrainConfig
from .groq_brain import GroqBrain, GroqConfig
from .piper_tts import PiperError, PiperTTS

DEFAULT_PROVIDER = "groq"


def selected_provider() -> str:
    return os.environ.get("DESKBUDDY_PROVIDER", DEFAULT_PROVIDER).strip().lower()


def build_brain(provider: str | None = None):
    """Construct the configured brain. Raises whatever the provider raises."""
    name = (provider or selected_provider()).lower()

    if name == "gemini":
        return Brain(BrainConfig.from_env())
    if name == "groq":
        return GroqBrain(GroqConfig.from_env())

    raise ValueError(f"unknown provider '{name}' (use 'groq' or 'gemini')")


__all__ = [
    "DEFAULT_PROVIDER",
    "GroqBrain",
    "GroqConfig",
    "PiperError",
    "PiperTTS",
    "build_brain",
    "selected_provider",
]
