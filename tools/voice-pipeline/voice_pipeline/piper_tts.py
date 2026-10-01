"""Local text-to-speech with Piper.

Piper is a fast neural TTS that runs entirely offline on CPU — no API, no
per-turn cost, which is what DeskBuddy wanted in the first place.

Voice models live in `~/.local/share/piper/voices/<name>.onnx` (+`.json`).
`ensure_voice()` fetches one from HuggingFace on first use (cached after that).
"""

from __future__ import annotations

import shutil
import urllib.request
import wave
from pathlib import Path

VOICE_CACHE = Path.home() / ".local" / "share" / "piper" / "voices"
BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

# name -> repo path without extension. `en_US-lessac-medium` is the friendly
# default; `en_GB-alba-medium` is a warmer read if you prefer it.
KNOWN_VOICES = {
    "en_US-lessac-medium": "en/en_US/lessac/medium/en_US-lessac-medium",
    "en_US-amy-medium": "en/en_US/amy/medium/en_US-amy-medium",
    "en_GB-alba-medium": "en/en_GB/alba/medium/en_GB-alba-medium",
}


class PiperError(RuntimeError):
    """Raised when Piper or a voice model is unavailable."""


def _download(url: str, target: Path, attempts: int = 3) -> None:
    """Fetch a URL to `target`, retrying transient DNS/network failures."""
    target.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=60) as response, open(target, "wb") as handle:
                shutil.copyfileobj(response, handle)
            return
        except Exception as exc:  # noqa: BLE001 - retried, then reported
            last_error = exc
            if target.exists():
                target.unlink()
    raise PiperError(f"could not download {url}: {last_error}")


def ensure_voice(name: str) -> tuple[Path, Path]:
    """Return (model, config) paths, downloading the voice if not cached."""
    model = VOICE_CACHE / f"{name}.onnx"
    # Piper ships the config as `<voice>.onnx.json` next to the model.
    config = VOICE_CACHE / f"{name}.onnx.json"

    if model.exists() and config.exists() and model.stat().st_size > 1000:
        return model, config

    slug = KNOWN_VOICES.get(name)
    if not slug:
        known = ", ".join(sorted(KNOWN_VOICES))
        raise PiperError(f"unknown voice '{name}'. Known: {known}")

    if not model.exists() or model.stat().st_size <= 1000:
        _download(f"{BASE_URL}/{slug}.onnx", model)
    if not config.exists():
        _download(f"{BASE_URL}/{slug}.onnx.json", config)
    return model, config


class PiperTTS:
    """TextToSpeech implementation backed by a local ONNX voice."""

    def __init__(self, voice_name: str = "en_US-lessac-medium") -> None:
        try:
            from piper import PiperVoice  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise PiperError("piper-tts is not installed (pip install piper-tts)") from exc

        model, config = ensure_voice(voice_name)
        self.voice_name = voice_name
        self._voice = PiperVoice.load(str(model), config_path=str(config))

    def speak(self, text: str, out_path: Path) -> Path:
        # Piper's own synthesize_wav() sets the sample width before the channel
        # count, which wave rejects on Python 3.14. Writing the header from the
        # first chunk ourselves sidesteps that and keeps one chunk stream.
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out_path), "wb") as wav_file:
            started = False
            for chunk in self._voice.synthesize(text):
                if not started:
                    wav_file.setnchannels(chunk.sample_channels)
                    wav_file.setsampwidth(chunk.sample_width)
                    wav_file.setframerate(chunk.sample_rate)
                    started = True
                wav_file.writeframes(chunk.audio_int16_bytes)
        return out_path
