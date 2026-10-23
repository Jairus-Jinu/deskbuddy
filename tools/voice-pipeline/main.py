#!/usr/bin/env python3
"""DeskBuddy voice pipeline CLI.

    python main.py doctor              # check audio + key before you rely on it
    python main.py devices             # list microphones and speakers
    python main.py say "hello"         # text -> speech out of the speaker
    python main.py ask "what's up"     # text -> reply text
    python main.py chat                # typed back-and-forth, keeps memory
    python main.py converse            # the real thing: hands-free conversation
    python main.py voice               # legacy push-to-talk loop (Enter per turn)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from voice_pipeline import (
    AudioError,
    Conversation,
    ConversationSettings,
    build_brain,
    converse,
    selected_provider,
    voice_loop,
)

PROJECT_ROOT = Path(__file__).resolve().parent


def load_dotenv(path: Path) -> None:
    """Minimal .env loader — avoids a dependency for six lines of parsing."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deskbuddy", description="DeskBuddy voice pipeline")
    parser.add_argument("--seconds", type=float, default=6.0, help="mic capture length per turn (legacy `voice`)")
    parser.add_argument("--mic", default=None, help="capture device: index, name, or substring")
    parser.add_argument("--speaker", default=None, help="playback device: index, name, or substring")
    parser.add_argument(
        "--provider",
        choices=("groq", "gemini"),
        default=None,
        help="override DESKBUDDY_PROVIDER for this run",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check the local setup")
    sub.add_parser("devices", help="list audio devices")
    sub.add_parser("chat", help="typed conversation that remembers context")

    conv = sub.add_parser("converse", help="hands-free conversation (wake word, then just talk)")
    conv.add_argument("--wake-word", default=os.environ.get("DESKBUDDY_WAKE_WORD", "choom"),
                      help="phrase to say to start talking (default: choom)")
    conv.add_argument("--no-wake-word", action="store_true", help="always listen, no trigger phrase")
    conv.add_argument("--silence-ms", type=int, default=800, help="pause length that ends your turn")
    conv.add_argument("--session-timeout", type=float, default=45.0, help="quiet seconds before the wake word is needed again")
    conv.add_argument("--barge-in", action="store_true", help="let you talk over a reply to cut it off")
    conv.add_argument("--max-turns", type=int, default=None, help="stop after N answered turns")
    conv.add_argument("--min-snr", type=float, default=9.0,
                      help="near-field gate: how far above room noise a voice must be (dB)")
    conv.add_argument("--near-field", action="store_true",
                      help="only answer voices louder than the room (unreliable in a loud room)")

    say = sub.add_parser("say", help="speak the given text")
    say.add_argument("text", nargs="+")

    ask = sub.add_parser("ask", help="ask one question, print the reply")
    ask.add_argument("text", nargs="+")

    voice = sub.add_parser("voice", help="talk to DeskBuddy through the mic")
    voice.add_argument("--rounds", type=int, default=None, help="stop after N turns")

    return parser


def cmd_devices() -> int:
    """List audio devices so --mic/--speaker can be pointed at the right one."""
    try:
        import sounddevice as sd
    except ImportError:
        print("error: sounddevice is not installed (pip install sounddevice)", file=sys.stderr)
        return 2

    print("id  in  out  name")
    print("-" * 60)
    for index, device in enumerate(sd.query_devices()):
        name = device["name"]
        if device["max_input_channels"] < 1 and device["max_output_channels"] < 1:
            continue
        if "monitor" in name.lower():
            continue
        print(f"{index:>2}  {device['max_input_channels']:>2}  {device['max_output_channels']:>3}  {name}")

    try:
        default_in, default_out = sd.default.device
        print(f"\ndefaults: mic={default_in} speaker={default_out}")
    except Exception:  # noqa: BLE001 - defaults are a nicety
        pass
    print("Pick one with --mic <id> / --speaker <id>, or pass part of the name.")
    return 0


def cmd_doctor(provider: str | None = None) -> int:
    import shutil
    import wave

    name = (provider or selected_provider()).lower()
    print(f"DeskBuddy doctor — provider: {name}")
    print("-" * 40)

    for tool in ("arecord", "aplay", "ffmpeg", "pactl"):
        print(f"  {'ok ' if shutil.which(tool) else 'MISSING'}  {tool}")

    try:
        brain = build_brain(name)
    except Exception as exc:  # noqa: BLE001 - this command exists to report exactly this
        print(f"  FAIL provider setup: {exc}")
        return 1
    brain.close()
    print("  ok   provider configured and reachable")

    tts_engine = os.environ.get("DESKBUDDY_TTS_ENGINE", "kokoro").lower()
    if name == "groq" and tts_engine == "kokoro":
        try:
            from voice_pipeline import KokoroTTS

            tts = KokoroTTS(os.environ.get("DESKBUDDY_TTS_VOICE", "af_heart"))
            print(f"  ok   kokoro voice loaded ({tts.voice_name})")
        except Exception as exc:  # noqa: BLE001 - reported as a doctor finding
            print(f"  FAIL kokoro voice: {exc}")
            return 1
    elif name == "groq" and tts_engine == "piper":
        try:
            from voice_pipeline import PiperTTS

            tts = PiperTTS(os.environ.get("DESKBUDDY_TTS_VOICE", "en_US-lessac-medium"))
            print(f"  ok   piper voice loaded ({tts.voice_name})")
        except Exception as exc:  # noqa: BLE001 - reported as a doctor finding
            print(f"  FAIL piper voice: {exc}")
            return 1

    for label, loader in (("wake word", _check_wake_word), ("voice activity", _check_vad)):
        try:
            print(f"  ok   {label} ({loader()})")
        except Exception as exc:  # noqa: BLE001 - reported as a doctor finding
            print(f"  FAIL {label}: {exc}")
            return 1

    import time

    try:
        from voice_pipeline import Microphone, Speaker

        with Microphone() as mic:
            peak = 0
            started = time.monotonic()
            while time.monotonic() - started < 2.0:
                chunk = mic.read(timeout=0.2)
                if chunk:
                    peak = max(peak, _peak(chunk))
        if peak == 0:
            print("  FAIL microphone: 2 s of pure digital silence — the mic (or its mute "
                  "switch) is off. Run `pactl set-source-mute @DEFAULT_SOURCE@ 0`.")
            return 1
        print(f"  ok   microphone capture (16 kHz mono, peak {peak})")
    except Exception as exc:  # noqa: BLE001 - reported as a doctor finding
        print(f"  FAIL microphone: {exc}")
        return 1

    try:
        import numpy as np

        with Speaker() as speaker:
            speaker.play(np.zeros(2400, dtype="float32"))
        print("  ok   speaker playback")
    except Exception as exc:  # noqa: BLE001 - reported as a doctor finding
        print(f"  FAIL speaker: {exc}")
        return 1

    print("-" * 40)
    print("ready — try: python main.py converse")
    return 0


def _peak(chunk: bytes) -> int:
    from array import array

    samples = array("h")
    samples.frombytes(chunk)
    return max((abs(value) for value in samples), default=0)


def _check_wake_word() -> str:
    """Construct the detector (downloads the ~10 MB model on first run)."""
    from voice_pipeline import WakeWord

    detector = WakeWord()
    return f"'{detector.name}' (sherpa-onnx)"


def _check_vad() -> str:
    from voice_pipeline import SileroVad

    SileroVad()
    return "silero onnx"


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.provider:
        os.environ["DESKBUDDY_PROVIDER"] = args.provider

    if args.command == "devices":
        return cmd_devices()
    if args.command == "doctor":
        return cmd_doctor(args.provider)

    try:
        brain = build_brain()
    except Exception as exc:  # provider config/install problems are user-facing
        print(f"error: {exc}", file=sys.stderr)
        print("see tools/voice-pipeline/README.md for setup", file=sys.stderr)
        return 2

    with brain:
        conversation = Conversation(brain=brain)

        if args.command == "say":
            text = " ".join(args.text)
            print(f"buddy: {text}")
            try:
                conversation.speak(text, speaker=args.speaker)
            except AudioError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            return 0

        if args.command == "ask":
            print(conversation.ask(" ".join(args.text)))
            return 0

        if args.command == "chat":
            print("DeskBuddy chat — blank line or Ctrl-D to stop.")
            while True:
                try:
                    line = input("you: ").strip()
                except EOFError:
                    print()
                    break
                if not line:
                    break
                try:
                    print(f"buddy: {conversation.ask(line)}")
                except Exception as exc:  # noqa: BLE001 - keep the REPL alive
                    print(f"error: {exc}", file=sys.stderr)
            return 0

        if args.command == "converse":
            settings = ConversationSettings(
                wake_word=args.wake_word,
                require_wake_word=not args.no_wake_word,
                silence_ms=args.silence_ms,
                session_timeout=args.session_timeout,
                barge_in=args.barge_in,
                max_turns=args.max_turns,
                min_snr_db=args.min_snr,
                near_field=args.near_field,
            )
            return converse(
                brain,
                mic=args.mic,
                speaker=args.speaker,
                settings=settings,
                out=sys.stdout,
                err=sys.stderr,
            )

        if args.command == "voice":
            return voice_loop(
                conversation,
                seconds=args.seconds,
                rounds=args.rounds,
                mic=args.mic,
                speaker=args.speaker,
                out=sys.stdout,
                err=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
