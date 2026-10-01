#!/usr/bin/env python3
"""DeskBuddy voice pipeline CLI.

    python main.py doctor              # check audio + key before you rely on it
    python main.py say "hello"         # text -> speech out of the speaker
    python main.py ask "what's up"     # text -> reply text
    python main.py chat                # typed back-and-forth, keeps memory
    python main.py voice               # the real thing: talk, it answers
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from voice_pipeline import (
    AudioError,
    Conversation,
    build_brain,
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
    parser.add_argument("--seconds", type=float, default=6.0, help="mic capture length per turn")
    parser.add_argument("--mic", default=None, help="capture device (arecord -D / pulse source)")
    parser.add_argument("--speaker", default=None, help="playback device (aplay -D / pulse sink)")
    parser.add_argument(
        "--provider",
        choices=("groq", "gemini"),
        default=None,
        help="override DESKBUDDY_PROVIDER for this run",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check the local setup")
    sub.add_parser("chat", help="typed conversation that remembers context")

    say = sub.add_parser("say", help="speak the given text")
    say.add_argument("text", nargs="+")

    ask = sub.add_parser("ask", help="ask one question, print the reply")
    ask.add_argument("text", nargs="+")

    voice = sub.add_parser("voice", help="talk to DeskBuddy through the mic")
    voice.add_argument("--rounds", type=int, default=None, help="stop after N turns")

    return parser


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

    tts_engine = os.environ.get("DESKBUDDY_TTS_ENGINE", "piper").lower()
    if name == "groq" and tts_engine == "piper":
        try:
            from voice_pipeline import PiperTTS

            tts = PiperTTS(os.environ.get("DESKBUDDY_TTS_VOICE", "en_US-lessac-medium"))
            print(f"  ok   piper voice loaded ({tts.voice_name})")
        except Exception as exc:  # noqa: BLE001 - reported as a doctor finding
            print(f"  FAIL piper voice: {exc}")
            return 1

    try:
        from voice_pipeline import is_silent, record_wav

        clip = Path(PROJECT_ROOT / ".doctor-capture.wav")
        record_wav(clip, 1.5)
        with wave.open(str(clip), "rb") as handle:
            summary = f"{handle.getframerate()} Hz, {handle.getnchannels()} ch"
        note = " — silent so far, that is fine" if is_silent(clip) else ""
        print(f"  ok   microphone capture ({summary}){note}")
        clip.unlink(missing_ok=True)
    except AudioError as exc:
        print(f"  FAIL microphone: {exc}")
        return 1

    print("-" * 40)
    print("ready — try: python main.py say \"hello\"")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.provider:
        os.environ["DESKBUDDY_PROVIDER"] = args.provider

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
