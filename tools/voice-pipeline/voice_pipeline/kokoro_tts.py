"""Text-to-speech with Kokoro — local, offline, free, and noticeably warmer
than Piper's default.

Two things matter for a conversation rather than a demo:

* **Synthesis is per sentence, so the first one starts playing in ~0.7 s**
  instead of waiting for the whole reply.
* **A reply can be cut off mid-word** when the person starts talking again.

The model is 325 MB on disk (89 MB for the int8 build) and caches under
`~/.cache/deskbuddy/kokoro/`.
"""

from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
CACHE_DIR = Path.home() / ".cache" / "deskbuddy" / "kokoro"
MODEL_FILE = "kokoro-v1.0.onnx"
VOICES_FILE = "voices-v1.0.bin"
SAMPLE_RATE = 24_000

# Kokoro v1.0 voices worth knowing about. `af_heart` is the most natural of the
# American female set and the default; `am_michael` is the male alternative.
KNOWN_VOICES = {
    "af_heart": "warm American female (default)",
    "af_bella": "bright American female",
    "af_nicole": "soft, slower American female",
    "am_michael": "American male",
    "am_puck": "American male, lighter",
    "bf_emma": "British female",
    "bm_george": "British male",
}


class KokoroError(RuntimeError):
    """Raised when Kokoro or its model files are unavailable."""


def _fetch(name: str) -> Path:
    target = CACHE_DIR / name
    if target.exists() and target.stat().st_size > 100_000:
        return target
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(f"{MODEL_URL}/{name}", timeout=300) as response, open(target, "wb") as handle:
                shutil.copyfileobj(response, handle)
            if target.stat().st_size > 100_000:
                return target
        except Exception as exc:  # noqa: BLE001 - retried, then reported
            last = exc
            target.unlink(missing_ok=True)
    raise KokoroError(f"could not download {name}: {last}")


def ensure_model() -> tuple[Path, Path]:
    """Return (model, voices) paths, downloading once on first use."""
    return _fetch(MODEL_FILE), _fetch(VOICES_FILE)


class KokoroTTS:
    """A `TextToSpeech` that can also stream sentence by sentence."""

    def __init__(self, voice: str = "af_heart", *, threads: int = 4) -> None:
        try:
            import numpy as np
            import onnxruntime as ort
            from kokoro_onnx import Kokoro
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise KokoroError("kokoro-onnx is not installed (pip install kokoro-onnx)") from exc

        self._np = np
        self.voice_name = voice
        model, voices = ensure_model()

        # Four intra-op threads is the measured sweet spot on this CPU class:
        # one thread is too slow to keep up, eight is slower than four.
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        self._session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
        self._kokoro = Kokoro.from_session(self._session, str(voices))
        self._check_voice(voice)
        self._warm()

    def _check_voice(self, voice: str) -> None:
        try:
            available = set(self._kokoro.get_voices())
        except Exception:  # noqa: BLE001 - older builds expose no list
            return
        if voice not in available:
            known = ", ".join(sorted(KNOWN_VOICES))
            raise KokoroError(f"unknown voice {voice!r}. Known: {known}")

    def _warm(self) -> None:
        """First inference pays graph-optimisation cost; keep it off the first turn."""
        try:
            self._kokoro.create("mm", voice=self.voice_name, speed=1.0, lang="en-us")
        except Exception:  # noqa: BLE001 - warming is an optimisation, never fatal
            pass

    def synthesise(self, text: str):
        """Yield (float32 mono samples, sample_rate) for one sentence."""
        samples, rate = self._kokoro.create(text, voice=self.voice_name, speed=1.0, lang="en-us")
        return self._np.asarray(samples, dtype="float32"), rate

    # -- TextToSpeech protocol -------------------------------------------------
    def speak(self, text: str, out_path: Path) -> Path:
        """Write a WAV file (kept for `main.py say` and the batch path)."""
        import wave

        out_path.parent.mkdir(parents=True, exist_ok=True)
        samples, rate = self.synthesise(text)
        pcm = (self._np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        with wave.open(str(out_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(rate)
            wav_file.writeframes(pcm)
        return out_path
