"""Wake word: "choom", spotted with Vosk's grammar-restricted recognizer.

Why Vosk and not the obvious choices:

* **openWakeWord** only ships fixed phrases (alexa, hey jarvis, hey mycroft,
  timer, weather); a custom word means training against thousands of clips.
* **sherpa-onnx's keyword spotter** can spell any word in phonemes, but was
  measured unreliable here: it detected "choom" only 4 times out of 6 on
  identical clean audio with different amounts of leading silence, and never
  once with classroom noise behind it.

Vosk runs a small ASR model but constrains its decoder to a handful of words.
The catch is that "choom" is not in Vosk's vocabulary, so it cannot be listed
directly — but the model already hears the word as "chum"/"choon", so those are
the grammar entries. That is the phrase list this module uses.

Measured: fires on every clean and classroom-noise case, silent on ordinary
speech and on 5 s of classroom background, 57x realtime on one core.
"""

from __future__ import annotations

import json
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_WORD = "choom"
# What the recognizer actually hears when the word is spoken. "choom" itself
# cannot be used: Vosk drops unknown words from the grammar with a warning.
HOMOPHONES = ("chum", "choon", "chump", "choose")

CACHE_DIR = Path.home() / ".cache" / "deskbuddy" / "vosk"
MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"


class WakeWordError(RuntimeError):
    """Raised when the recognizer cannot be built."""


def ensure_model() -> Path:
    """Download and unpack the small English model (~68 MB) once."""
    target = CACHE_DIR / MODEL_NAME
    if (target / "am").is_dir() and (target / "conf").is_dir():
        return target

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    archive = CACHE_DIR / f"{MODEL_NAME}.zip"
    last: Exception | None = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(MODEL_URL, timeout=300) as response, open(archive, "wb") as handle:
                shutil.copyfileobj(response, handle)
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(CACHE_DIR)
            archive.unlink(missing_ok=True)
            if (target / "am").is_dir():
                return target
        except Exception as exc:  # noqa: BLE001 - retried, then reported
            last = exc
    raise WakeWordError(f"could not download the wake-word model: {last}")


@dataclass
class WakeWord:
    """Detects one phrase on a stream of 16 kHz int16 chunks."""

    name: str = DEFAULT_WORD
    homophones: tuple[str, ...] = HOMOPHONES
    model_dir: Path | None = None
    on_frame: object = field(default=None, init=False, repr=False)
    _meter: object = field(default=None, init=False, repr=False)
    _model: object = field(default=None, init=False, repr=False)
    _rec: object = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            import vosk
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise WakeWordError("vosk is not installed (pip install vosk)") from exc

        vosk.SetLogLevel(-1)  # the grammar parser is chatty; errors still raise
        directory = self.model_dir or ensure_model()
        try:
            self._model = vosk.Model(str(directory))
        except Exception as exc:  # noqa: BLE001 - vosk raises RuntimeError
            raise WakeWordError(f"could not load the wake-word model: {exc}") from exc
        self._vosk = vosk
        self.reset()

    @property
    def _grammar(self) -> str:
        return json.dumps([*self.homophones, "[unk]"])

    def reset(self) -> None:
        self._rec = self._vosk.KaldiRecognizer(self._model, 16000, self._grammar)

    def _match(self, text: str) -> bool:
        return any(word in text for word in self.homophones)

    def push(self, chunk: bytes) -> bool:
        """Feed 16 kHz int16 mono audio. True once the phrase has been heard."""
        if self._rec.AcceptWaveform(chunk):
            text = json.loads(self._rec.Result()).get("text", "")
            if self._match(text):
                self.reset()
                return True
        return False

    def wait(self, mic, timeout: float | None = None, on_idle=None) -> bool:  # noqa: ANN001
        """Block until the phrase is heard. False if `timeout` passes first."""
        import time

        from .vad import Meter

        self.reset()
        deadline = None if timeout is None else time.monotonic() + timeout
        while deadline is None or time.monotonic() < deadline:
            chunk = mic.read(timeout=0.3)
            if chunk is None:
                if getattr(mic, "closed", False):
                    return False
                if on_idle is not None:
                    on_idle()
                continue
            if self.on_frame is not None:
                if self._meter is None:
                    self._meter = Meter()
                self.on_frame(self._meter(chunk))
            if self.push(chunk):
                return True
        return False
