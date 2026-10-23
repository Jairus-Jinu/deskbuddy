"""Voice activity detection and turn-taking, without pulling in torch.

Silero VAD is the accuracy/size sweet spot (2.3 MB ONNX, ~0.2 ms per 32 ms
window), but the `silero-vad` PyPI package drags in PyTorch. We run the same
model through onnxruntime directly and hold its recurrent state ourselves.

`TurnDetector` turns per-frame speech probabilities into a decision: "the
person is talking", "they paused, take the turn", or "they stopped". It also
decides whether the utterance was real speech or just a cough.
"""

from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

SILERO_URL = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
CACHE_DIR = Path.home() / ".cache" / "deskbuddy"
WINDOW = 512  # samples at 16 kHz
CONTEXT = 64  # the model wants 64 samples of prior audio prepended


class VadError(RuntimeError):
    """Raised when the VAD model is unavailable or cannot run."""


def ensure_model(path: Path | None = None) -> Path:
    """Download + cache silero_vad.onnx (2.3 MB), returning its path."""
    target = path or (CACHE_DIR / "silero_vad.onnx")
    if target.exists() and target.stat().st_size > 100_000:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(SILERO_URL, timeout=60) as response, open(target, "wb") as handle:
                handle.write(response.read())
            if target.stat().st_size > 100_000:
                return target
        except Exception as exc:  # noqa: BLE001 - retried, then reported
            last = exc
            target.unlink(missing_ok=True)
    raise VadError(f"could not download the VAD model: {last}")


class SileroVad:
    """Speech probability for successive 512-sample windows of 16 kHz PCM."""

    def __init__(self, model_path: Path | None = None) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise VadError("onnxruntime is not installed") from exc
        import numpy as np

        self._np = np
        options = ort.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        model = str(model_path or ensure_model())
        self._session = ort.InferenceSession(model, options, providers=["CPUExecutionProvider"])
        self.reset()

    def reset(self) -> None:
        np = self._np
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        # The first window is padded with the context the model normally gets
        # from its own history; zeros are what silero's reference wrapper uses.
        self._context = np.zeros((1, CONTEXT), dtype=np.float32)

    def __call__(self, chunk: bytes) -> float:
        """Probability that this 32 ms chunk contains speech (0.0–1.0)."""
        np = self._np
        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        x = np.concatenate([self._context, samples.reshape(1, -1)], axis=1)
        out, self._state = self._session.run(
            None,
            {"input": x, "state": self._state, "sr": np.array(16000, dtype=np.int64)},
        )
        self._context = x[..., -CONTEXT:]
        return float(out[0][0])

    def speech_probabilities(self, pcm: bytes) -> list[float]:
        """Run a whole buffer through from a clean state (used by tests)."""
        self.reset()
        np = self._np
        samples = np.frombuffer(pcm, dtype=np.int16)
        return [
            self(samples[i : i + WINDOW].tobytes())
            for i in range(0, len(samples) - WINDOW + 1, WINDOW)
        ]


@dataclass
class TurnDetector:
    """Frame-by-frame turn taking.

    The interesting knob is `silence_ms`: how long a pause ends the turn. Too
    short and it cuts people off mid-thought; too long and it feels laggy.

    `gate` is an optional near-field check. Silero says "somebody is talking";
    in a crowded room that is usually true. The gate adds "…and they are close
    to the microphone", which is what makes the difference between a
    conversation and a transcript of the room.
    """

    vad: SileroVad
    start_ms: int = 192  # ~6 frames of speech before we believe it
    silence_ms: int = 800
    max_utterance_ms: int = 30_000
    min_speech_ms: int = 300
    frame_ms: int = 32
    threshold: float = 0.5
    gate: object | None = None
    _speech_ms: int = field(default=0, init=False)
    _silence_ms: int = field(default=0, init=False)
    _started: bool = field(default=False, init=False)
    _frames: list[bytes] = field(default_factory=list, init=False)
    _speech_frames: int = field(default=0, init=False)
    _terminal: str | None = field(default=None, init=False)

    def reset(self) -> None:
        self._speech_ms = 0
        self._silence_ms = 0
        self._started = False
        self._frames = []
        self._speech_frames = 0
        self._terminal = None
        self.vad.reset()

    @property
    def speaking(self) -> bool:
        return self._started

    def feed(self, chunk: bytes) -> str:
        """Consume one 512-sample chunk.

        Returns one of `"idle"`, `"speech"`, `"turn"` (utterance finished) or
        `"too_short"` (noise, discarded). Call `reset()` after a terminal value.
        """
        if self._terminal is not None:
            # Report the end of a turn exactly once. A caller that forgets to
            # reset must not hand the same utterance over twice.
            return "idle"

        # Learn the room on every frame, speech or not, so the floor keeps
        # tracking even while somebody is talking.
        probability = self.vad(chunk)
        is_speech = probability >= self.threshold

        if self.gate is not None:
            self.gate.observe(chunk)
            if not self._started:
                # The gate only guards the *entry* into a turn. Once somebody is
                # talking, a quiet syllable must not eject them mid-sentence.
                is_speech = is_speech and self.gate.accepts()
        if is_speech:
            self._speech_frames += 1

        if not self._started:
            # Keep a little pre-roll so the first phoneme isn't clipped.
            self._frames.append(chunk)
            if len(self._frames) > max(10, self.start_ms // self.frame_ms):
                self._frames.pop(0)
            self._speech_ms = self._speech_ms + self.frame_ms if is_speech else 0
            if self._speech_ms >= self.start_ms:
                self._started = True
                self._silence_ms = 0
                return "speech"
            return "idle"

        self._frames.append(chunk)
        if is_speech:
            self._silence_ms = 0
        else:
            self._silence_ms += self.frame_ms

        if self._silence_ms >= self.silence_ms:
            spoken = self._speech_frames * self.frame_ms
            self._terminal = "turn" if spoken >= self.min_speech_ms else "too_short"
            return self._terminal
        if len(self._frames) * self.frame_ms >= self.max_utterance_ms:
            self._terminal = "turn"
            return self._terminal
        return "speech"

    def pcm(self) -> bytes:
        """The captured utterance so far."""
        return b"".join(self._frames)


class UtteranceRecorder:
    """Blocking wrapper: listen until the person finishes a sentence.

    Returns the PCM for one utterance, or None if `deadline` seconds pass with
    nobody speaking. Used by the wake-word gate ("did they say the word, then
    keep talking?") and by the barge-in probe.
    """

    def __init__(self, mic, detector: TurnDetector, *, frame_timeout: float = 0.5) -> None:  # noqa: ANN001
        self._mic = mic
        self._detector = detector
        self._frame_timeout = frame_timeout

    def record(self, deadline: float | None = None, on_idle=None) -> bytes | None:  # noqa: ANN001
        detector = self._detector
        detector.reset()
        started = time.monotonic()
        while True:
            if deadline is not None and time.monotonic() - started > deadline:
                return None
            chunk = self._mic.read(timeout=self._frame_timeout)
            if chunk is None:
                if on_idle is not None:
                    on_idle()
                continue
            state = detector.feed(chunk)
            if state == "turn":
                pcm = detector.pcm()
                detector.reset()
                return pcm
            if state == "too_short":
                pcm = detector.pcm()
                detector.reset()
                if deadline is not None:
                    return pcm  # caller decides whether that counts
                continue

    def has_speech(self, window: float = 0.6) -> bool:
        """Is somebody talking right now? Cheap probe for barge-in."""
        self._detector.reset()
        frames = int(window / (WINDOW / 16000))
        for _ in range(frames):
            chunk = self._mic.read(timeout=0.2)
            if chunk is None:
                continue
            if self._detector.feed(chunk) == "speech":
                return True
        self._detector.reset()
        return False
