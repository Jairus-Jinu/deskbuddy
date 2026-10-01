"""The DeskBuddy turn loop: listen -> transcribe -> reply -> speak.

Kept isolated from the CLI so the same object can later be driven by the
wake-word detector or the eyes' state machine without a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, TextIO

from .audio import AudioError, is_silent, play_wav, record_wav, temp_wav
from .brain import Brain

MAX_TURNS_REMEMBERED = 12


@dataclass
class Turn:
    user: str
    reply: str


@dataclass
class Conversation:
    """Holds short-term memory and runs one exchange at a time."""

    brain: Brain
    history: list[Turn] = field(default_factory=list)

    def ask(self, user_text: str) -> str:
        """Text-in, text-out turn (used by tests and the text REPL)."""
        reply = self.brain.reply(user_text, self._context())
        self.history.append(Turn(user=user_text, reply=reply))
        del self.history[:-MAX_TURNS_REMEMBERED]
        return reply

    def listen_and_reply(self, seconds: float, mic: str | None = None) -> tuple[str, str]:
        """Record -> transcribe -> reply. Returns (transcript, reply)."""
        clip = temp_wav()
        record_wav(clip, seconds, input_device=mic)
        if is_silent(clip):
            return "", ""
        transcript = self.brain.transcribe(clip)
        if not transcript:
            return "", ""
        return transcript, self.ask(transcript)

    def speak(self, text: str, speaker: str | None = None) -> Path:
        """Synthesise and play a reply."""
        clip = self.brain.speak(text, temp_wav(".wav"))
        play_wav(clip, output_device=speaker)
        return clip

    def _context(self) -> list[dict[str, str]]:
        """Flatten remembered turns into the Interactions API content list."""
        turns: list[dict[str, str]] = []
        for turn in self.history:
            turns.append({"type": "text", "text": turn.user})
            turns.append({"type": "text", "text": turn.reply})
        return turns


def voice_loop(
    conversation: Conversation,
    *,
    seconds: float,
    rounds: int | None = None,
    mic: str | None = None,
    speaker: str | None = None,
    out: TextIO,
    err: TextIO,
) -> int:
    """Run the listen/reply/speak loop. Returns a shell-style exit code."""
    completed = 0
    while rounds is None or completed < rounds:
        try:
            input("   [Enter] to talk, Ctrl-C to stop ")
        except EOFError:
            break
        try:
            transcript, reply = conversation.listen_and_reply(seconds, mic=mic)
        except AudioError as exc:
            print(f"   ! audio problem: {exc}", file=err)
            return 2
        except Exception as exc:  # noqa: BLE001 - one bad turn shouldn't kill the session
            print(f"   ! turn failed: {exc}", file=err)
            continue

        if not transcript:
            print("   (heard nothing)", file=out)
            continue

        print(f"   you: {transcript}", file=out)
        print(f"   buddy: {reply}", file=out)
        try:
            conversation.speak(reply, speaker=speaker)
        except AudioError as exc:
            print(f"   ! could not speak: {exc}", file=err)
        completed += 1
    return 0
