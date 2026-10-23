"""Level tracking, so a busy room doesn't turn into constant conversation.

Silero VAD answers "is this speech?" — it cannot answer "is this *me*". In a
classroom (or a café, or a living room with the TV on) it says yes constantly,
and the assistant would reply to people who are not talking to it.

The fix is the oldest one in audio: compare the current level against the
room's own background level and require a margin. Someone talking to a desk
robot from 40 cm is much louder at the microphone than conversation across
the room; walking that back to a signal-to-noise ratio makes the threshold
move with the room instead of being a magic constant.

`NoiseFloor` tracks the background with a low percentile over a rolling
window. A percentile rather than a mean is deliberate: in a room where speech
is present most of the time, the mean drifts up to meet the speech and would
eventually mask it, while the 20th percentile keeps tracking the gaps.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np


def rms(chunk: bytes | np.ndarray) -> float:
    """Root-mean-square level of int16 PCM."""
    samples = np.frombuffer(chunk, dtype=np.int16) if isinstance(chunk, bytes) else chunk
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))


def to_db(value: float, floor: float = 1.0) -> float:
    """RMS -> dBFS-ish scale. Silence maps to 0 instead of -inf."""
    return 20.0 * math.log10(max(value, floor))


@dataclass
class NoiseFloor:
    """Rolling background level, in dB, robust to continuous speech."""

    window: int = 250  # ~8 s of 32 ms frames
    percentile: float = 20.0
    _db: deque = field(default_factory=deque, init=False)

    def __post_init__(self) -> None:
        self._db = deque(maxlen=self.window)

    def observe(self, chunk: bytes | np.ndarray) -> float:
        """Record one frame; returns the current floor estimate in dB."""
        self._db.append(to_db(rms(chunk)))
        return self.db

    @property
    def db(self) -> float:
        if not self._db:
            return 0.0
        return float(np.percentile(np.fromiter(self._db, dtype=float), self.percentile))

    @property
    def ready(self) -> bool:
        """Enough frames to trust the estimate (about 1 s)."""
        return len(self._db) >= 30

    def snr(self, chunk: bytes | np.ndarray) -> float:
        """How far this frame sits above the background, in dB."""
        return to_db(rms(chunk)) - self.db

    def reset(self) -> None:
        self._db.clear()


@dataclass
class NearFieldGate:
    """Decide whether an utterance is close enough to be aimed at us.

    `min_snr_db` is the knob to turn: raise it in a noisy room, lower it if
    the assistant ignores you when the room is quiet.

    Speech is not uniformly loud — syllables swing 20 dB — so a per-frame test
    would reject the quiet half of every word. The decision uses a short
    rolling mean (~200 ms) instead, which is what "is this voice nearby?"
    actually means at conversational timescales.
    """

    min_snr_db: float = 9.0
    smoothing_frames: int = 6  # ~200 ms of 32 ms frames
    floor: NoiseFloor = field(default_factory=NoiseFloor)
    _recent: deque = field(default_factory=deque, init=False)

    def __post_init__(self) -> None:
        self._recent = deque(maxlen=self.smoothing_frames)

    def observe(self, chunk: bytes) -> None:
        """Continuously learn the room (call this even when nothing is said)."""
        self.floor.observe(chunk)
        if self.floor.ready:
            self._recent.append(self.floor.snr(chunk))

    def accepts(self, chunk: bytes | None = None) -> bool:
        """Is the recent level far enough above the room to be near-field?"""
        if not self.floor.ready:
            return True  # still calibrating — don't reject, just listen
        if chunk is not None and self.floor.ready:
            self._recent.append(self.floor.snr(chunk))
        if not self._recent:
            return True
        return float(np.mean(self._recent)) >= self.min_snr_db

    def report(self) -> str:
        return f"noise floor {self.floor.db:.0f} dB, gate +{self.min_snr_db:.0f} dB"
