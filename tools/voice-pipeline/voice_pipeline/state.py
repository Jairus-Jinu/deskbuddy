"""A one-way state feed from the conversation loop to whatever is displaying it.

The loop must never depend on a UI toolkit: `converse` has to keep working in a
terminal, over SSH, or with no widget at all. So it publishes plain values
here and anything watching (the desktop window) reads them. A no-op `publish`
is the default, which is why the loop costs nothing when no UI is running.

Deliberately lock-light and non-blocking on the producer side: the audio thread
calls this every 32 ms and must never be made to wait on a repaint.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field

# The four states the widget shows. Strings rather than an enum so a state can
# be added without every consumer needing the new class.
SLEEPING = "sleeping"  # mic open, waiting for the wake word
LISTENING = "listening"  # the person is being heard
THINKING = "thinking"  # transcribing or generating a reply
SPEAKING = "speaking"  # playing the reply
ERROR = "error"  # something broke; the widget says so instead of looking idle

COLORS = {
    SLEEPING: (0.42, 0.45, 0.52),
    LISTENING: (0.20, 0.78, 0.66),
    THINKING: (0.95, 0.72, 0.25),
    SPEAKING: (0.38, 0.62, 0.95),
    ERROR: (0.92, 0.32, 0.34),
}

LABELS = {
    SLEEPING: 'say "choom"',
    LISTENING: "listening",
    THINKING: "thinking",
    SPEAKING: "speaking",
    ERROR: "problem",
}


@dataclass
class State:
    """A snapshot of what the assistant is doing, safe to read from any thread."""

    state: str = SLEEPING
    level: float = 0.0  # 0..1, smoothed mic loudness for the ring
    text: str = ""  # what was heard or is being said
    detail: str = ""  # error text, if any


class StateFeed:
    """The shared cell between the loop (writer) and the window (reader)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = State()
        self._updated = time.monotonic()

    # -- writer (conversation loop) -------------------------------------------
    def publish(self, state: str | None = None, *, level: float | None = None,
                text: str | None = None, detail: str | None = None) -> None:
        with self._lock:
            current = self._state
            self._state = State(
                state=state if state is not None else current.state,
                level=current.level if level is None else max(0.0, min(1.0, level)),
                text=current.text if text is None else text,
                detail=current.detail if detail is None else detail,
            )
            self._updated = time.monotonic()

    def set_level(self, level: float) -> None:
        """Cheap path for the per-frame mic meter — leaves everything else alone."""
        with self._lock:
            self._state.level = max(0.0, min(1.0, level))
            self._updated = time.monotonic()

    # -- reader (window) ------------------------------------------------------
    def read(self) -> State:
        with self._lock:
            return State(self._state.state, self._state.level, self._state.text, self._state.detail)

    @property
    def idle_seconds(self) -> float:
        with self._lock:
            return time.monotonic() - self._updated


class NullFeed:
    """Drop-in that discards everything — the default when no widget is shown."""

    def publish(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        return None

    def set_level(self, level: float) -> None:  # noqa: ARG002
        return None

    def read(self) -> State:
        return State()

    @property
    def idle_seconds(self) -> float:
        return 0.0


class DemoFeed:
    """Walks through every state on a timer — for `main.py widget --demo`.

    Lets the widget be checked (and styled) without a microphone, an API key,
    or a room full of people.
    """

    def __init__(self, hold: float = 2.5) -> None:
        self._state = State()
        self._updated = time.monotonic()
        self._hold = hold
        self._steps = [
            State(SLEEPING, 0.0, "", ""),
            State(LISTENING, 0.55, "what is the weather like today", ""),
            State(THINKING, 0.1, "what is the weather like today", ""),
            State(SPEAKING, 0.8, "Warm and clear, about twenty-eight degrees.", ""),
            State(ERROR, 0.0, "", "microphone muted — pactl set-source-mute @DEFAULT_SOURCE@ 0"),
        ]
        self._started = time.monotonic()

    def read(self) -> State:
        elapsed = (time.monotonic() - self._started) / self._hold
        snapshot = self._steps[int(elapsed) % len(self._steps)]
        # Wiggle the level so the ring moves even on still frames.
        wiggle = 0.15 * math.sin(time.monotonic() * 6.0)
        return State(snapshot.state, max(0.0, snapshot.level + wiggle if snapshot.level else 0.0),
                     snapshot.text, snapshot.detail)

    def publish(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        return None

    def set_level(self, level: float) -> None:  # noqa: ARG002
        return None
