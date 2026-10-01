"""Groq (cloud STT + LLM) paired with a local TTS engine.

Groq has no project-approval gate and a real free tier, and its Whisper
endpoint is very fast. TTS stays local (Piper) so the only cloud calls are the
small ones — which is also what keeps the ESP32 version cheap to run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .brain import DEFAULT_SYSTEM_PROMPT, MAX_TURNS_REMEMBERED
from .providers import LanguageModel, SpeechToText, TextToSpeech, Turn

DEFAULT_STT_MODEL = "whisper-large-v3-turbo"
# NOTE: llama-3.3-70b-versatile is Enterprise-only on Groq; gpt-oss-20b has a
# free-tier rate limit and is very fast (1000 t/s), so it is the safer default.
DEFAULT_LLM_MODEL = "openai/gpt-oss-20b"
# Groq-hosted TTS (only used when DESKBUDDY_TTS_ENGINE=groq)
DEFAULT_GROQ_TTS_MODEL = "canopylabs/orpheus-v1-english"
DEFAULT_GROQ_TTS_VOICE = "troy"


class GroqError(RuntimeError):
    """Raised when a Groq call fails or configuration is missing."""


@dataclass(frozen=True)
class GroqConfig:
    api_key: str
    stt_model: str = DEFAULT_STT_MODEL
    llm_model: str = DEFAULT_LLM_MODEL
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    @classmethod
    def from_env(cls) -> "GroqConfig":
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise GroqError("no GROQ_API_KEY — get one free at https://console.groq.com/keys")
        return cls(
            api_key=key,
            stt_model=os.environ.get("DESKBUDDY_STT_MODEL", DEFAULT_STT_MODEL),
            llm_model=os.environ.get("DESKBUDDY_LLM_MODEL", DEFAULT_LLM_MODEL),
            system_prompt=os.environ.get("DESKBUDDY_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
        )


class GroqSpeechToText(SpeechToText):
    def __init__(self, client: object, model: str) -> None:
        self._client = client
        self._model = model

    def transcribe(self, wav_path: Path) -> str:
        try:
            with open(wav_path, "rb") as audio:
                result = self._client.audio.transcriptions.create(
                    file=(wav_path.name, audio.read()),
                    model=self._model,
                    language="en",
                )
        except Exception as exc:
            raise GroqError(f"transcribe failed ({self._model}): {exc}") from exc
        return (getattr(result, "text", "") or "").strip()


class GroqLanguageModel(LanguageModel):
    def __init__(self, client: object, model: str, system_prompt: str) -> None:
        self._client = client
        self._model = model
        self._system_prompt = system_prompt

    def reply(self, user_text: str, history: list[Turn] | None = None) -> str:
        messages: list[dict[str, str]] = [{"role": "system", "content": self._system_prompt}]
        for turn in history or []:
            messages.append({"role": "user", "content": turn.user})
            messages.append({"role": "assistant", "content": turn.reply})
        messages.append({"role": "user", "content": user_text})
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.7,
                # gpt-oss reasons before answering and bills those tokens against
                # max_tokens, so the budget is deliberately generous; `low` keeps
                # the thinking short enough to stay conversational.
                max_tokens=1200,
                reasoning_effort="low",
            )
        except Exception as exc:
            raise GroqError(f"reply failed ({self._model}): {exc}") from exc
        return (completion.choices[0].message.content or "").strip()


class GroqTTS(TextToSpeech):
    """Optional Groq-hosted voice — simpler than Piper, but not local."""

    def __init__(self, client: object, model: str, voice: str) -> None:
        self._client = client
        self._model = model
        self._voice = voice

    def speak(self, text: str, out_path: Path) -> Path:
        try:
            response = self._client.audio.speech.create(
                model=self._model, voice=self._voice, input=text, response_format="wav"
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(response.read())
        except Exception as exc:
            raise GroqError(f"tts failed ({self._model}): {exc}") from exc
        return out_path


class GroqBrain:
    """Combines the three stages behind the same surface `Conversation` expects."""

    def __init__(self, config: GroqConfig, tts: TextToSpeech | None = None) -> None:
        try:
            from groq import Groq  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise GroqError("groq SDK is not installed (pip install groq)") from exc

        self.config = config
        self._client = Groq(api_key=config.api_key)
        self._stt = GroqSpeechToText(self._client, config.stt_model)
        self._llm = GroqLanguageModel(self._client, config.llm_model, config.system_prompt)
        self._tts = tts if tts is not None else self._default_tts()
        self._history: list[Turn] = []

    def _default_tts(self) -> TextToSpeech:
        """Local Piper by default; Groq-hosted voice only if explicitly asked for."""
        engine = os.environ.get("DESKBUDDY_TTS_ENGINE", "piper").strip().lower()
        if engine == "groq":
            return GroqTTS(
                client=self._client,
                model=os.environ.get("DESKBUDDY_TTS_MODEL", DEFAULT_GROQ_TTS_MODEL),
                voice=os.environ.get("DESKBUDDY_TTS_VOICE", DEFAULT_GROQ_TTS_VOICE),
            )
        if engine != "piper":
            raise GroqError(f"unknown TTS engine '{engine}' (use 'piper' or 'groq')")

        from .piper_tts import PiperTTS  # imported lazily: piper is optional

        return PiperTTS(os.environ.get("DESKBUDDY_TTS_VOICE", "en_US-lessac-medium"))

    def transcribe(self, wav_path: Path) -> str:
        return self._stt.transcribe(wav_path)

    def reply(self, user_text: str, history: list[Turn] | None = None) -> str:
        context = self._history if history is None else history
        answer = self._llm.reply(user_text, context)
        self._history.append(Turn(user=user_text, reply=answer))
        del self._history[:-MAX_TURNS_REMEMBERED]
        return answer

    def speak(self, text: str, out_path: Path) -> Path:
        return self._tts.speak(text, out_path)

    def close(self) -> None:
        closer = getattr(self._client, "close", None)
        if callable(closer):
            closer()

    def __enter__(self) -> "GroqBrain":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
