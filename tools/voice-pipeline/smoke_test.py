#!/usr/bin/env python3
"""Offline checks — no API key, no network.

Verifies the parts that break silently: does the mic capture, does silence
detection run, does the turn loop remember context. Run before `doctor`:

    .venv/bin/python smoke_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from voice_pipeline import Conversation, is_silent, play_wav, record_wav, wav_duration

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {name}{' — ' + detail if detail else ''}")
    if not condition:
        failures.append(name)


class FakeBrain:
    """Stands in for a real provider so the loop can run without a key."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list]] = []

    def reply(self, text: str, history=None) -> str:
        self.calls.append((text, list(history or [])))
        return f"echo: {text}"

    def transcribe(self, path: Path) -> str:
        return "hello there"

    def speak(self, text: str, out_path: Path) -> Path:
        out_path.write_bytes(b"RIFF")
        return out_path


def main() -> int:
    clip = Path(".smoke.wav")
    try:
        print("audio:")
        record_wav(clip, 2)
        check("records a 2s WAV", clip.exists() and wav_duration(clip) >= 1.9,
              f"{wav_duration(clip):.2f}s")
        check("silence detection runs", isinstance(is_silent(clip), bool))
        play_wav(clip)
        check("plays back without error", True)

        print("turn loop (fake brain, no network):")
        brain = FakeBrain()
        convo = Conversation(brain=brain)
        check("reply returns text", convo.ask("one") == "echo: one")
        convo.ask("two")
        check("history reaches the next call", len(brain.calls[1][1]) == 1,
              f"{len(brain.calls[1][1])} prior turn(s)")
        check("conversation remembered two turns", len(convo.history) == 2)
    finally:
        clip.unlink(missing_ok=True)

    print()
    print("FAILED: " + ", ".join(failures) if failures else "all offline checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
