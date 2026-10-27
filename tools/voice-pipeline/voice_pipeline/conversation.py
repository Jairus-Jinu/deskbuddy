"""Continuous, hands-free conversation.

The old loop was: Enter → record 6 s → transcribe → reply → speak. Every step
waited for the one before it, so a turn took ~4 s of mostly silence.

This loop overlaps everything it can while keeping the code linear:

    mic stream ──▶ VAD ──▶ [utterance ends] ──▶ Whisper
                                                  │
                                          Groq tokens ──▶ sentence ──▶ Kokoro ──▶ speaker
                                                  └──────── history ────────┘

Concretely: the microphone never stops, the reply is spoken sentence by
sentence as it is generated, and (optionally) speech during playback cuts the
reply off instead of being ignored.

Flow: the wake word opens a session; after that every finished utterance is
answered until the session goes quiet for a while, then it goes back to
listening for the wake word.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import TextIO

from .audio import AudioError, temp_wav
from .audio_io import MIC_RATE, AudioDeviceError, Microphone, Speaker
from .brain import MAX_TURNS_REMEMBERED
from .level import NearFieldGate
from .providers import Turn
from . import state as ui
from .vad import SileroVad, TurnDetector, UtteranceRecorder

# A sentence boundary is [.!?…] followed by whitespace — but "Dr. Smith" and
# "3.5 seconds" are not boundaries, so common abbreviations and single-letter
# initials are excluded.
SENTENCE_END = re.compile(r"(?<!\bDr)(?<!\bMr)(?<!\bMs)(?<!\bMrs)(?<!\bSt)(?<!\be\.g)(?<!\bi\.e)(?<=[.!?…])\s+")
MIN_SENTENCE_CHARS = 8  # "Okay." merges forward; "Hey there." speaks alone


def split_sentences(buffer: str, *, flush: bool = False) -> tuple[list[str], str]:
    """Split complete sentences off the front of a streaming reply.

    Short fragments ("Okay.") are kept with the next sentence rather than
    spoken on their own — one extra round trip for a two-word clip sounds
    worse than waiting a few hundred milliseconds.

    Returns (ready_sentences, leftover_text). With `flush=True` the remainder
    is returned as a final sentence.
    """
    sentences: list[str] = []
    pending = ""
    while True:
        match = SENTENCE_END.search(buffer)
        if not match:
            break
        candidate = (pending + buffer[: match.start() + 1]).strip()
        buffer = buffer[match.end() :]
        pending = ""
        if len(candidate) < MIN_SENTENCE_CHARS:
            pending = candidate + " "
            continue
        sentences.append(candidate)
    buffer = pending + buffer
    if flush and buffer.strip():
        sentences.append(buffer.strip())
        buffer = ""
    return sentences, buffer


def pcm_to_wav(pcm: bytes, rate: int = MIC_RATE) -> bytes:
    """Wrap raw mono int16 PCM in a WAV container Whisper accepts."""
    import io
    import wave

    handle = io.BytesIO()
    with wave.open(handle, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        wav_file.writeframes(pcm)
    return handle.getvalue()


@dataclass
class ConversationSettings:
    """Everything tunable about a hands-free session."""

    wake_word: str = "choom"
    require_wake_word: bool = True
    silence_ms: int = 800
    session_timeout: float = 45.0  # quiet seconds before the wake word is needed again
    barge_in: bool = False  # cut the reply off if the person talks over it
    echo_guard: float = 0.35  # ignore the mic this long after playback ends
    max_turns: int | None = None
    # Near-field gate: how far above the room's background a voice has to be.
    # Public spaces (classroom, café) need a higher value; a quiet room can run
    # lower. 0 disables the gate entirely.
    min_snr_db: float = 9.0
    # Off by default: in a classroom the room is as loud as the speaker, so a
    # level gate rejects your voice along with everyone else's. The wake word
    # (which matches on content, not loudness) is the reliable filter.
    near_field: bool = False


@dataclass
class ConversationSession:
    """Runs the loop. Owns the mic/speaker and the turn memory."""

    brain: object
    mic: Microphone
    speaker: Speaker
    settings: ConversationSettings = field(default_factory=ConversationSettings)
    history: list[Turn] = field(default_factory=list)
    out: TextIO = None  # type: ignore[assignment]
    err: TextIO = None  # type: ignore[assignment]
    feed: object = field(default_factory=ui.NullFeed)
    expires_at: float = field(default=0.0, init=False)
    _stop: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        import sys

        self.out = self.out or sys.stdout
        self.err = self.err or sys.stderr
        gate = NearFieldGate(min_snr_db=self.settings.min_snr_db) if self.settings.near_field else None
        self.detector = TurnDetector(
            vad=SileroVad(), silence_ms=self.settings.silence_ms, gate=gate
        )
        self.gate = gate
        self.recorder = UtteranceRecorder(self.mic, self.detector)
        self.recorder.on_frame = self._on_mic_frame
        self._wake = None
        if self.settings.require_wake_word:
            from .wake_word import WakeWord

            self._wake = WakeWord(name=self.settings.wake_word)
            self._wake.on_frame = self.feed.set_level

    # -- UI feed --------------------------------------------------------------
    def _on_mic_frame(self, level: float, vad_state: str) -> None:
        self.feed.set_level(level)
        if vad_state == "speech":
            self.feed.publish(ui.LISTENING)

    # -- output ---------------------------------------------------------------
    def _say(self, text: str) -> None:
        print(text, file=self.out, flush=True)

    def _warn(self, text: str) -> None:
        print(text, file=self.err, flush=True)

    # -- one turn -------------------------------------------------------------
    def transcribe(self, pcm: bytes, index: int = 0) -> str:
        wav = pcm_to_wav(pcm)
        if hasattr(self.brain, "transcribe_audio"):
            return self.brain.transcribe_audio(wav, f"turn-{index}.wav")
        clip = temp_wav()
        clip.write_bytes(wav)
        try:
            return self.brain.transcribe(clip)
        finally:
            clip.unlink(missing_ok=True)

    def reply(self, text: str) -> str:
        """Ask the brain and speak the answer sentence by sentence."""
        stream = getattr(self.brain, "stream", None)
        if stream is None:
            answer = self.brain.reply(text, self.history)
            self.history.append(Turn(user=text, reply=answer))
            del self.history[:-MAX_TURNS_REMEMBERED]
            self._speak_text(answer)
            return answer

        collected: list[str] = []
        buffer = ""
        for delta in stream(text, self.history):
            collected.append(delta)
            buffer += delta
            sentences, buffer = split_sentences(buffer)
            for sentence in sentences:
                if not self._speak_text(sentence):
                    # Barge-in: keep consuming tokens so history stays honest,
                    # but stop synthesising.
                    continue
        tail, _ = split_sentences(buffer, flush=True)
        for sentence in tail:
            self._speak_text(sentence)

        answer = "".join(collected).strip()
        self.history.append(Turn(user=text, reply=answer))
        del self.history[:-MAX_TURNS_REMEMBERED]
        return answer

    def _speak_text(self, text: str) -> bool:
        """Speak one sentence. Returns False if it was interrupted."""
        if not text.strip():
            return True
        tts = getattr(self.brain, "tts", None)
        if tts is None:
            return True
        probe = self._probe_barge_in if self.settings.barge_in else None
        import numpy as np

        self.feed.publish(ui.SPEAKING, text=text)
        samples, rate = tts.synthesise(text)
        if rate != self.speaker.rate:
            samples = _resample(np, samples, rate, self.speaker.rate)
        ok = self.speaker.play(samples, on_chunk=probe)
        self.mic.flush()  # whatever the mic heard during playback is not ours
        time.sleep(self.settings.echo_guard)
        self.mic.flush()
        self.feed.publish(ui.LISTENING)
        return ok

    def _probe_barge_in(self) -> bool:
        """Called between playback blocks: has the person started talking?"""
        return self.recorder.has_speech(window=0.1)

    # -- the loop -------------------------------------------------------------
    def calibrate(self, seconds: float = 1.5) -> str:
        """Learn the room's background level before trusting the gate."""
        if self.gate is None:
            return "near-field gate off"
        started = time.monotonic()
        while time.monotonic() - started < seconds:
            chunk = self.mic.read(timeout=0.3)
            if chunk:
                self.gate.observe(chunk)
        return self.gate.report()

    def run(self) -> int:
        turns = 0
        room = self.calibrate()
        self._say(
            "DeskBuddy is listening"
            + (f" — say '{self.settings.wake_word.replace('_', ' ')}'" if self.settings.require_wake_word else "")
            + f". ({room})"
            + " Ctrl-C to stop."
        )
        try:
            while (self.settings.max_turns is None or turns < self.settings.max_turns) and not self._stop:
                if not self._conversation_open():
                    if not self._await_wake_word():
                        break
                pcm = self.recorder.record(
                    deadline=self._turn_deadline(), should_stop=lambda: self._stop
                )
                if pcm is None:
                    continue
                if not pcm or len(pcm) < 1600:  # < 50 ms of audio
                    continue
                self._handle_turn(pcm, turns)
                turns += 1
        except KeyboardInterrupt:
            self._say("\nbye.")
        return 0

    def _sleep(self) -> None:
        """Mark the widget as waiting for the wake word again."""
        self.feed.publish(ui.SLEEPING, text="", detail="")

    def stop(self) -> None:
        """Ask the loop to finish. Used when the widget window is closed."""
        self._stop = True

    def _conversation_open(self) -> bool:
        if not self.settings.require_wake_word:
            return True
        return time.monotonic() < self.expires_at

    def _turn_deadline(self) -> float | None:
        """How long to wait for someone to start talking before we give up."""
        if not self.settings.require_wake_word:
            # No session to expire: block until somebody actually speaks.
            return None
        if not self._conversation_open():
            return 1.0  # short poll so we notice the session ending
        return max(1.0, self.expires_at - time.monotonic())

    def _await_wake_word(self) -> bool:
        """Block until the phrase is heard. Returns False when interrupted."""
        assert self._wake is not None
        self._sleep()
        while not self._stop:
            if self._wake.wait(self.mic, timeout=1.0):
                self._say("   (heard the wake word)")
                self.feed.publish(ui.LISTENING, text="", detail="")
                self.mic.flush()
                self.expires_at = time.monotonic() + self.settings.session_timeout
                return True
            # Timed out with nothing heard — loop and keep listening.
        return False

    def _handle_turn(self, pcm: bytes, index: int) -> str:
        """Transcribe and answer one utterance; returns the transcript."""
        self.feed.publish(ui.THINKING, text="")
        try:
            transcript = self.transcribe(pcm, index)
        except Exception as exc:  # noqa: BLE001 - one bad turn shouldn't end the session
            self._warn(f"   ! transcribe failed: {exc}")
            self.feed.publish(ui.ERROR, detail=f"transcribe failed: {exc}")
            return ""
        if not transcript:
            self.feed.publish(ui.LISTENING)
            return ""
        self._say(f"   you: {transcript}")
        self.feed.publish(ui.THINKING, text=transcript)
        try:
            self.reply(transcript)
        except Exception as exc:  # noqa: BLE001 - keep the conversation alive
            self._warn(f"   ! reply failed: {exc}")
            self.feed.publish(ui.ERROR, detail=f"reply failed: {exc}")
        # Refresh the open session: the person is still here and talking.
        self.expires_at = time.monotonic() + self.settings.session_timeout
        return transcript


def _resample(np, samples, source_rate: int, target_rate: int):  # noqa: ANN001
    """Linear resample — only used if a TTS engine disagrees with the speaker."""
    if source_rate == target_rate:
        return samples
    ratio = target_rate / source_rate
    count = int(round(len(samples) * ratio))
    positions = np.linspace(0, len(samples) - 1, count)
    return np.interp(positions, np.arange(len(samples)), samples).astype("float32")


def converse(
    brain,
    *,
    out: TextIO | None = None,
    err: TextIO | None = None,
    mic: str | int | None = None,
    speaker: str | int | None = None,
    settings: ConversationSettings | None = None,
    widget: bool = False,
) -> int:
    """Build the devices and run one hands-free session.

    With `widget=True` the face window is driven from this process: the loop
    runs on a worker thread and Tk keeps the main thread, which is what Tk
    requires on Linux.
    """
    settings = settings or ConversationSettings()
    try:
        mic_device = Microphone(device=mic)
        speaker_device = Speaker(device=speaker, rate=24_000)
    except (AudioDeviceError, AudioError) as exc:
        print(f"error: {exc}", file=err or __import__("sys").stderr)
        return 2

    feed = ui.StateFeed() if widget else ui.NullFeed()

    with mic_device, speaker_device:
        session = ConversationSession(
            brain=brain,
            mic=mic_device,
            speaker=speaker_device,
            settings=settings,
            out=out,
            err=err,
            feed=feed,
        )

        if not widget:
            return session.run()

        import threading

        result = {"code": 0}

        def run_loop() -> None:
            try:
                result["code"] = session.run()
            except Exception as exc:  # noqa: BLE001 - surface it in the window
                feed.publish(ui.ERROR, detail=str(exc))
                result["code"] = 1

        worker = threading.Thread(target=run_loop, daemon=True)
        worker.start()

        import tkinter as tk

        from .widget import Widget

        def stop() -> None:
            # Closing the window ends the session. Three things have to happen
            # to make that prompt: the loop's stop flag, waking the mic stream
            # (a thread parked in read() otherwise waits out its timeout), and
            # letting the loop unwind before the audio devices are torn down.
            session.stop()
            mic_device.close()

        window = Widget(feed, on_close=stop)
        try:
            window.root.mainloop()
        except tk.TclError:
            pass
        session.stop()
        worker.join(timeout=5.0)
        return result["code"]
