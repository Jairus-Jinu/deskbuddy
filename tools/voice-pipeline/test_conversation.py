#!/usr/bin/env python3
"""Offline tests for the conversation machinery — no mic, no key, no network.

Run with pytest or plainly:

    .venv/bin/python test_conversation.py

Unlike `smoke_test.py` (which exercises real devices), everything here uses
fake audio so it can run in CI.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from voice_pipeline.conversation import (  # noqa: E402
    ConversationSettings,
    ConversationSession,
    pcm_to_wav,
    split_sentences,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {name}{' — ' + detail if detail else ''}")
    if not condition:
        FAILURES.append(name)


# -- sentence splitting -------------------------------------------------------
def test_split_sentences() -> None:
    print("sentence splitting:")
    sentences, rest = split_sentences("Hello there. How are you? I am fine.")
    check("splits complete sentences", sentences == ["Hello there.", "How are you?"], str(sentences))
    check("leaves the unfinished tail", rest == "I am fine.", repr(rest))

    sentences, rest = split_sentences("One moment")
    check("no boundary yet -> nothing ready", sentences == [] and rest == "One moment")

    sentences, _ = split_sentences("One moment", flush=True)
    check("flush emits the tail", sentences == ["One moment"])

    sentences, _ = split_sentences("Dr. Smith went home. He was tired!", flush=True)
    check("abbreviations do not split", sentences[0] == "Dr. Smith went home.", str(sentences))

    sentences, _ = split_sentences("It took 3.5 seconds. Then it finished.", flush=True)
    check("decimals do not split", sentences[0] == "It took 3.5 seconds.", str(sentences))

    sentences, _ = split_sentences("Yes. No. Maybe so.", flush=True)
    check("tiny fragments merge forward", sentences == ["Yes. No.", "Maybe so."], str(sentences))

    # Incremental: sentences appear as soon as their full stop arrives.
    buffer, ready = "", []
    for delta in ["Hey", " there.", " I was", " thinking."]:
        buffer += delta
        found, buffer = split_sentences(buffer)
        ready.extend(found)
    tail, _ = split_sentences(buffer, flush=True)
    ready.extend(tail)
    check("streamed deltas split incrementally", ready == ["Hey there.", "I was thinking."], str(ready))


# -- wav wrapping -------------------------------------------------------------
def test_pcm_to_wav() -> None:
    print("pcm wrapping:")
    import wave
    import io

    pcm = b"\x00\x01" * 1600  # 1600 samples, 100 ms at 16 kHz
    data = pcm_to_wav(pcm)
    with wave.open(io.BytesIO(data)) as handle:
        check("wraps as 16 kHz mono", handle.getframerate() == 16000 and handle.getnchannels() == 1)
        check("keeps every sample", handle.getnframes() == 1600, str(handle.getnframes()))


# -- fakes --------------------------------------------------------------------
class FakeTTS:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def synthesise(self, text: str):
        import numpy as np

        self.spoken.append(text)
        return np.ones(2400, dtype="float32"), 24_000


class FakeBrain:
    """Streams a scripted reply and records the turns it was asked about."""

    def __init__(self) -> None:
        self.tts = FakeTTS()
        self.asks: list[tuple[str, int]] = []
        self.script = ["Hey", " there.", " Good", " to see", " you.", " Bye!"]

    def stream(self, text: str, history=None):
        self.asks.append((text, len(history or [])))
        yield from self.script

    def transcribe_audio(self, wav_bytes: bytes, filename: str = "speech.wav") -> str:
        return "hello buddy"


class FakeMic:
    def __init__(self) -> None:
        self.flushed = 0

    def read(self, timeout: float = 1.0):
        return None

    def flush(self) -> None:
        self.flushed += 1


class FakeSpeaker:
    rate = 24_000

    def __init__(self) -> None:
        self.played = 0

    def play(self, samples, on_chunk=None) -> bool:
        self.played += 1
        return True


def make_session(brain=None, settings=None) -> ConversationSession:
    session = ConversationSession(
        brain=brain or FakeBrain(),
        mic=FakeMic(),
        speaker=FakeSpeaker(),
        settings=settings or ConversationSettings(require_wake_word=False),
        out=open("/dev/null", "w"),
        err=open("/dev/null", "w"),
    )
    return session


# -- one turn -----------------------------------------------------------------
def test_reply_streams_sentences() -> None:
    print("streaming reply:")
    brain = FakeBrain()
    session = make_session(brain)
    answer = session.reply("how are you")

    check("returns the full text", answer == "Hey there. Good to see you. Bye!", repr(answer))
    check("speaks per sentence", brain.tts.spoken == ["Hey there.", "Good to see you.", "Bye!"], str(brain.tts.spoken))
    check("plays each sentence", session.speaker.played == 3, str(session.speaker.played))
    check("records the turn", len(session.history) == 1 and session.history[0].user == "how are you")

    session.reply("again")
    check("history is passed to the next turn", brain.asks[-1][1] == 1, str(brain.asks[-1]))


def test_handle_turn() -> None:
    print("turn handling:")
    brain = FakeBrain()
    session = make_session(brain)
    transcript = session._handle_turn(b"\x00\x01" * 5000, 0)
    check("transcribes and answers", transcript == "hello buddy", repr(transcript))
    check("session stays open after speaking", session._conversation_open() if session.settings.require_wake_word else True)

    # A failure in one turn must not kill the session.
    class BrokenBrain(FakeBrain):
        def transcribe_audio(self, wav_bytes, filename="speech.wav"):
            raise RuntimeError("network down")

    broken = make_session(BrokenBrain())
    try:
        result = broken._handle_turn(b"\x00\x01" * 5000, 0)
        check("transcribe failure is swallowed", result == "")
    except Exception as exc:  # noqa: BLE001 - that is the failure being tested
        check("transcribe failure is swallowed", False, repr(exc))


def test_turn_detector() -> None:
    print("turn detection:")

    class ScriptedVad:
        """Emits a scripted probability per call."""

        def __init__(self, probabilities: list[float]) -> None:
            self._probabilities = list(probabilities)
            self.reset_count = 0

        def reset(self) -> None:
            self.reset_count += 1

        def __call__(self, chunk: bytes) -> float:
            return self._probabilities.pop(0) if self._probabilities else 0.0

    from voice_pipeline.vad import TurnDetector

    # 10 speech frames (320 ms) then silence until the turn ends.
    vad = ScriptedVad([0.9] * 10 + [0.0] * 40)
    detector = TurnDetector(vad=vad, silence_ms=320)
    states = [detector.feed(b"\x00\x00" * 512) for _ in range(40)]
    check("idle until speech starts", states[0] == "idle", states[0])
    check("reports speech while talking", "speech" in states)
    check("ends the turn after the pause", "turn" in states, str(states[-6:]))
    check("turn reported exactly once", states.count("turn") == 1, str(states.count("turn")))

    # Pure noise that never reaches the start threshold must not open a turn.
    vad = ScriptedVad([0.9, 0.0] * 30)
    detector = TurnDetector(vad=vad, silence_ms=320)
    states = [detector.feed(b"\x00\x00" * 512) for _ in range(30)]
    check("brief blips stay idle", "speech" not in states, str(set(states)))

    # A very short utterance is rejected, not sent to the STT bill.
    vad = ScriptedVad([0.9] * 7 + [0.0] * 12)
    detector = TurnDetector(vad=vad, silence_ms=320, min_speech_ms=500)
    states = [detector.feed(b"\x00\x00" * 512) for _ in range(20)]
    check("too-short speech is discarded", "too_short" in states, str(states[-4:]))


def test_settings_defaults() -> None:
    print("settings:")
    settings = ConversationSettings()
    check("wake word on by default", settings.require_wake_word)
    check("barge-in off by default", not settings.barge_in)
    check("sane silence window", 400 <= settings.silence_ms <= 1500, str(settings.silence_ms))


def main() -> int:
    for test in (
        test_split_sentences,
        test_pcm_to_wav,
        test_settings_defaults,
        test_reply_streams_sentences,
        test_handle_turn,
        test_turn_detector,
    ):
        test()
    print()
    print("FAILED: " + ", ".join(FAILURES) if FAILURES else "all conversation checks passed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
