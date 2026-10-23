"""Wake word: "choom", spotted with sherpa-onnx.

Why not openWakeWord: it only ships a fixed set of words (alexa, hey jarvis,
hey mycroft, timer, weather) and a custom word needs a Colab training run
against tens of thousands of clips. sherpa-onnx's zipformer keyword spotter is
a tiny ASR model with the decoder constrained to whatever phrase you list, so
a new word is a text file, not a training job:

    CH UW1 M @CHOOM      # "choom"

Phonemes come from the CMU dictionary the model ships (`en.phone`); any English
word can be spelled this way, which is why this engine was chosen.

The model is a 3.3 M-parameter bilingual zipformer (~10 MB int8) that runs
comfortably in real time on one CPU thread.
"""

from __future__ import annotations

import shutil
import tarfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_WORD = "choom"
# "choom" as CMU phonemes. CH as in "choose", UW as in "boot", M as in "mum".
DEFAULT_PHRASE = "CH UW1 M"

CACHE_DIR = Path.home() / ".cache" / "deskbuddy" / "kws"
MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/"
    "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2"
)
ENCODER = "encoder-epoch-13-avg-2-chunk-16-left-64.int8.onnx"
DECODER = "decoder-epoch-13-avg-2-chunk-16-left-64.onnx"
JOINER = "joiner-epoch-13-avg-2-chunk-16-left-64.int8.onnx"


class WakeWordError(RuntimeError):
    """Raised when the keyword spotter cannot be built."""


@dataclass
class WakeWord:
    """Detects one phrase on a stream of 16 kHz int16 chunks."""

    name: str = DEFAULT_WORD
    phrase: str = DEFAULT_PHRASE
    score: float = 1.0  # keyword boosting; higher = more eager
    threshold: float = 0.25  # lower = more sensitive
    model_dir: Path | None = None
    _spotter: object = field(default=None, init=False, repr=False)
    _stream: object = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            import sherpa_onnx
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise WakeWordError("sherpa-onnx is not installed (pip install sherpa-onnx)") from exc

        directory = self.model_dir or ensure_model()
        keywords = CACHE_DIR / f"keywords-{self.name}.txt"
        keywords.parent.mkdir(parents=True, exist_ok=True)
        keywords.write_text(f"{self.phrase} :{self.score} #{self.threshold} @{self.name.upper()}\n", encoding="utf-8")

        try:
            self._spotter = sherpa_onnx.KeywordSpotter(
                tokens=str(directory / "tokens.txt"),
                encoder=str(directory / ENCODER),
                decoder=str(directory / DECODER),
                joiner=str(directory / JOINER),
                keywords_file=str(keywords),
                num_threads=2,
                keywords_score=self.score,
                keywords_threshold=self.threshold,
            )
        except Exception as exc:  # noqa: BLE001 - sherpa raises RuntimeError
            raise WakeWordError(f"could not build the keyword spotter: {exc}") from exc

        self._stream = self._spotter.create_stream()

    # -- detection ------------------------------------------------------------
    def push(self, chunk: bytes) -> bool:
        """Feed 16 kHz int16 mono audio. True once the phrase has been heard.

        sherpa-onnx expects float32 in [-1, 1]; handing it raw int16 makes the
        features meaningless and the word never matches.
        """
        import numpy as np

        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        self._stream.accept_waveform(16000, samples)
        fired = False
        while self._spotter.is_ready(self._stream):
            self._spotter.decode_stream(self._stream)
            if self._spotter.get_result(self._stream):
                fired = True
                self._spotter.reset_stream(self._stream)
        return fired

    def reset(self) -> None:
        self._spotter.reset_stream(self._stream)

    def wait(self, mic, timeout: float | None = None, on_idle=None) -> bool:  # noqa: ANN001
        """Block until the phrase is heard. False if `timeout` passes first."""
        import time

        self.reset()
        deadline = None if timeout is None else time.monotonic() + timeout
        while deadline is None or time.monotonic() < deadline:
            chunk = mic.read(timeout=0.3)
            if chunk is None:
                if on_idle is not None:
                    on_idle()
                continue
            if self.push(chunk):
                return True
        return False


def ensure_model(directory: Path | None = None) -> Path:
    """Download and unpack the keyword-spotting model once, return its folder."""
    target = directory or (CACHE_DIR / "model")
    marker = target / "tokens.txt"
    if marker.exists() and (target / ENCODER).exists():
        return target

    target.mkdir(parents=True, exist_ok=True)
    archive = target / "model.tar.bz2"
    last: Exception | None = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(MODEL_URL, timeout=300) as response, open(archive, "wb") as handle:
                shutil.copyfileobj(response, handle)
            with tarfile.open(archive, "r:bz2") as bundle:
                # The archive has one top-level folder; flatten it.
                for member in bundle.getmembers():
                    if not member.isfile():
                        continue
                    member.name = Path(member.name).name
                    if member.name in {"tokens.txt", ENCODER, DECODER, JOINER, "en.phone"}:
                        bundle.extract(member, target)
            archive.unlink(missing_ok=True)
            if marker.exists():
                return target
        except Exception as exc:  # noqa: BLE001 - retried, then reported
            last = exc
    raise WakeWordError(f"could not download the wake-word model: {last}")
