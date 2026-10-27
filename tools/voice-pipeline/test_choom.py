#!/usr/bin/env python3
"""Say "choom" out loud and see whether the wake word fires.

    .venv/bin/python test_choom.py

It prints what the recognizer hears, so a near-miss is visible rather than
silent. Run this first; `main.py converse` uses exactly the same detector.
"""

from __future__ import annotations

import json
import sys
import time

from voice_pipeline.audio_io import Microphone
from voice_pipeline.vad import Meter
from voice_pipeline.wake_word import HOMOPHONES, WakeWord, ensure_model


def main() -> int:
    import vosk

    mic = Microphone().start()
    try:
        wake = WakeWord()
    except Exception as exc:  # noqa: BLE001 - first run downloads a model
        print(f"error: {exc}")
        return 2
    meter = Meter()

    print('Say "choom" out loud. Listening for 25 seconds. Ctrl-C to stop.\n')
    started = time.monotonic()
    level_seen = 0.0
    try:
        while time.monotonic() - started < 25:
            chunk = mic.read(timeout=0.3)
            if not chunk:
                continue
            level = meter(chunk)
            level_seen = max(level_seen, level)
            bar = "#" * int(level * 24)
            print(f"\r  mic [{bar:<24}] {level:4.2f}", end="", flush=True)
            if wake.push(chunk):
                print(f"\n\n  >>> HEARD IT after {time.monotonic() - started:.1f}s <<<\n")
                return 0
    except KeyboardInterrupt:
        print()
    finally:
        mic.close()

    print(f"\n\nNo wake word heard. Peak mic level was {level_seen:.2f}.")
    if level_seen < 0.2:
        print("The microphone barely moved — check it is unmuted and raise its volume:")
        print("  pactl set-source-mute @DEFAULT_SOURCE@ 0")
        print("  pactl set-source-volume @DEFAULT_SOURCE@ 40%")
    else:
        print("The microphone is working, so the word was not recognised. Try:")
        print("  - saying it slower and closer to the laptop")
        print("  - running: .venv/bin/python test_choom.py --what-heard")
    return 1


def what_heard() -> int:
    """Print a plain transcript of 6 seconds, to see what it thinks you said."""
    import vosk

    from voice_pipeline.audio_io import Microphone

    mic = Microphone().start()
    model = vosk.Model(str(ensure_model()))
    rec = vosk.KaldiRecognizer(model, 16000)
    chunks: list[bytes] = []
    print("Speak now — recording 6 seconds...")
    started = time.monotonic()
    while time.monotonic() - started < 6:
        chunk = mic.read(timeout=0.3)
        if chunk:
            chunks.append(chunk)
            rec.AcceptWaveform(chunk)
    rec.AcceptWaveform(b"\x00\x00" * 8000)
    mic.close()
    pcm = b"".join(chunks)
    print(f"\nmicrophone level: {Meter()(pcm):.2f}")
    print(f"transcript: {json.loads(rec.FinalResult()).get('text', '(nothing)')!r}")
    print(f"\nthe wake word matches any of: {', '.join(HOMOPHONES)}")
    return 0


if __name__ == "__main__":
    if "--what-heard" in sys.argv:
        sys.exit(what_heard())
    sys.exit(main())
