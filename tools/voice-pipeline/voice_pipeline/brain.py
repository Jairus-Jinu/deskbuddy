"""Gemini-backed STT / LLM / TTS via the Interactions API.

One `genai.Client` serves all three stages. Models are configurable so a cost or
availability change is an env edit, not a code change:

    STT   gemini-3.5-flash          (audio in -> transcript out)
    LLM   gemini-flash-latest       (text in  -> reply out)
    TTS   gemini-3.8-flash-lite-tts (text in  -> WAV audio out)
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

from google import genai

from .audio import STT_RATE
from .providers import Turn

DEFAULT_STT_MODEL = "gemini-3.5-flash"
DEFAULT_LLM_MODEL = "gemini-flash-latest"
DEFAULT_TTS_MODEL = "gemini-3.8-flash-lite-tts"
DEFAULT_TTS_VOICE = "Achird"

# How many past turns to replay into the model. Shared by every provider.
MAX_TURNS_REMEMBERED = 12

# Keeps replies short enough to stay snappy on an ESP32 speaker and cheap per turn.
DEFAULT_SYSTEM_PROMPT = (
    "You are DeskBuddy, a small friendly desktop companion robot. "
    "You are warm, a little playful, and genuinely helpful. "
    "You speak naturally and concisely: one to three short sentences, "
    "the way a person talks out loud — no markdown, no lists, no emoji. "
    "If the person is just chatting, chat back. Match their language, "
    "including Hinglish if they use it."
)


class BrainError(RuntimeError):
    """Raised when a Gemini call fails or the key is missing."""


@dataclass(frozen=True)
class BrainConfig:
    api_key: str
    stt_model: str = DEFAULT_STT_MODEL
    llm_model: str = DEFAULT_LLM_MODEL
    tts_model: str = DEFAULT_TTS_MODEL
    tts_voice: str = DEFAULT_TTS_VOICE
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    @classmethod
    def from_env(cls) -> "BrainConfig":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise BrainError(
                "no API key: set GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment "
                "or in tools/voice-pipeline/.env"
            )
        return cls(
            api_key=key,
            stt_model=os.environ.get("DESKBUDDY_STT_MODEL", DEFAULT_STT_MODEL),
            llm_model=os.environ.get("DESKBUDDY_LLM_MODEL", DEFAULT_LLM_MODEL),
            tts_model=os.environ.get("DESKBUDDY_TTS_MODEL", DEFAULT_TTS_MODEL),
            tts_voice=os.environ.get("DESKBUDDY_TTS_VOICE", DEFAULT_TTS_VOICE),
            system_prompt=os.environ.get("DESKBUDDY_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
        )


class Brain:
    """Thin wrapper over the three Gemini stages DeskBuddy needs."""

    def __init__(self, config: BrainConfig) -> None:
        self.config = config
        self._client = genai.Client(api_key=config.api_key)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Brain":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def transcribe(self, wav_path: Path) -> str:
        """Audio file -> text transcript."""
        audio = base64.b64encode(wav_path.read_bytes()).decode("ascii")
        try:
            interaction = self._client.interactions.create(
                model=self.config.stt_model,
                input=[{
                    "type": "user_input",
                    "content": [
                        {"type": "text", "text": "Transcribe this audio verbatim. Return only the transcript."},
                        {"type": "audio", "data": audio, "mime_type": "audio/wav", "sample_rate": STT_RATE},
                    ],
                }],
            )
        except Exception as exc:  # SDK raises several error types; surface them plainly
            raise BrainError(f"transcribe failed ({self.config.stt_model}): {exc}") from exc
        return self._last_text(interaction).strip()

    def reply(self, user_text: str, history: list[Turn] | None = None) -> str:
        """Text -> assistant text, carrying prior turns for multi-turn memory."""
        content: list[dict[str, str]] = []
        for turn in history or []:
            content.append({"type": "text", "text": turn.user})
            content.append({"type": "text", "text": turn.reply})
        content.append({"type": "text", "text": user_text})
        try:
            interaction = self._client.interactions.create(
                model=self.config.llm_model,
                input=[{"type": "user_input", "content": content}],
                system_instruction=self.config.system_prompt,
            )
        except Exception as exc:
            raise BrainError(f"reply failed ({self.config.llm_model}): {exc}") from exc
        return self._last_text(interaction).strip()

    def speak(self, text: str, out_path: Path) -> Path:
        """Text -> WAV file at 24 kHz, ready for the speaker."""
        try:
            interaction = self._client.interactions.create(
                model=self.config.tts_model,
                input=[{
                    "type": "user_input",
                    "content": [{"type": "text", "text": text}],
                }],
                response_format={"type": "audio"},
                generation_config={"speech_config": [{"voice": self.config.tts_voice}]},
            )
        except Exception as exc:
            raise BrainError(f"speak failed ({self.config.tts_model}): {exc}") from exc

        data = self._last_audio(interaction)
        if not data:
            raise BrainError("tts returned no audio")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return out_path

    @staticmethod
    def _last_text(interaction: object) -> str:
        """Pull the final text block out of an interaction response."""
        outputs = getattr(interaction, "outputs", None) or []
        for output in reversed(outputs):
            text = getattr(output, "text", None)
            if text:
                return text
        legacy = getattr(interaction, "output_text", None)
        return legacy or ""

    @staticmethod
    def _last_audio(interaction: object) -> bytes:
        """Pull the final audio block out of an interaction response."""
        audio = getattr(interaction, "output_audio", None)
        encoded = getattr(audio, "data", None) if audio else None
        if encoded:
            return base64.b64decode(encoded)

        for output in reversed(getattr(interaction, "outputs", None) or []):
            encoded = getattr(output, "data", None)
            if encoded and getattr(output, "type", None) == "audio":
                return base64.b64decode(encoded)
            if encoded and getattr(output, "mime_type", "").startswith("audio"):
                return base64.b64decode(encoded)
        return b""
