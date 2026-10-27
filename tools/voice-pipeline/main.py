#!/usr/bin/env python3
"""DeskBuddy voice pipeline CLI.

    python main.py doctor              # check audio + key before you rely on it
    python main.py devices             # list microphones and speakers
    python main.py say "hello"         # text -> speech out of the speaker
    python main.py ask "what's up"     # text -> reply text
    python main.py chat                # typed back-and-forth, keeps memory
    python main.py converse            # the real thing: hands-free conversation
    python main.py converse --widget   # same, with a floating face window
    python main.py serve               # background service: hidden until "choom"
    python main.py service --install   # start `serve` automatically at login
    python main.py widget --demo       # preview every state, no mic or key
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


def _converse_flags() -> dict[str, dict]:
    """Options shared by `converse` and `serve`, so the two cannot drift."""
    return {
        "--wake-word": dict(default=os.environ.get("DESKBUDDY_WAKE_WORD", "choom"),
                            help="phrase to say to start talking (default: choom)"),
        "--no-wake-word": dict(action="store_true", help="always listen, no trigger phrase"),
        "--silence-ms": dict(type=int, default=800, help="pause length that ends your turn"),
        "--session-timeout": dict(type=float, default=45.0,
                                  help="quiet seconds before the wake word is needed again"),
        "--barge-in": dict(action="store_true", help="let you talk over a reply to cut it off"),
        "--max-turns": dict(type=int, default=None, help="stop after N answered turns"),
        "--min-snr": dict(type=float, default=9.0,
                          help="near-field gate: how far above room noise a voice must be (dB)"),
        "--near-field": dict(action="store_true",
                             help="only answer voices louder than the room (unreliable in a loud room)"),
    }


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
    for flag, kwargs in _converse_flags().items():
        conv.add_argument(flag, **kwargs)
    conv.add_argument("--widget", action="store_true",
                      help="show the floating face window while listening")

    serve = sub.add_parser("serve", help="run in the background; the window appears when you say the wake word")
    for flag, kwargs in _converse_flags().items():
        serve.add_argument(flag, **kwargs)

    svc = sub.add_parser("service", help="install/uninstall the login service for `serve`")
    svc.add_argument("--install", action="store_true", help="start with the desktop session")
    svc.add_argument("--uninstall", action="store_true", help="stop starting with the session")
    svc.add_argument("--status", action="store_true", help="is it running?")
    svc.add_argument("--show", action="store_true", help="print the systemd unit without writing it")

    face = sub.add_parser("widget", help="show the face window on its own")
    face.add_argument("--demo", action="store_true", help="cycle through every state (no mic needed)")
    face.add_argument("--hold", type=float, default=2.5, help="seconds per state in --demo")

    say = sub.add_parser("say", help="speak the given text")
    say.add_argument("text", nargs="+")

    ask = sub.add_parser("ask", help="ask one question, print the reply")
    ask.add_argument("text", nargs="+")

    voice = sub.add_parser("voice", help="talk to DeskBuddy through the mic")
    voice.add_argument("--rounds", type=int, default=None, help="stop after N turns")

    return parser


def _settings_from(args) -> ConversationSettings:  # noqa: ANN001
    return ConversationSettings(
        wake_word=args.wake_word,
        require_wake_word=not args.no_wake_word,
        silence_ms=args.silence_ms,
        session_timeout=args.session_timeout,
        barge_in=args.barge_in,
        max_turns=args.max_turns,
        min_snr_db=args.min_snr,
        near_field=args.near_field,
    )


def cmd_serve(args) -> int:  # noqa: ANN001
    """Background mode: hidden window, pops up when the wake word is heard."""
    if not _have_display():
        print("error: serve needs a desktop session (no DISPLAY/WAYLAND_DISPLAY).",
              file=sys.stderr)
        print("       without a screen, use `main.py converse` instead.", file=sys.stderr)
        return 2

    from voice_pipeline.service import ServiceLock

    lock = ServiceLock()
    if not lock.acquire():
        print("DeskBuddy is already running (another process holds the microphone).",
              file=sys.stderr)
        print("  stop it:  systemctl --user stop deskbuddy", file=sys.stderr)
        return 1

    try:
        brain = build_brain()
    except Exception as exc:  # provider config/install problems are user-facing
        lock.release()
        print(f"error: {exc}", file=sys.stderr)
        print("see tools/voice-pipeline/README.md for setup", file=sys.stderr)
        return 2

    print("DeskBuddy is running in the background — say “choom”.", flush=True)
    try:
        with brain:
            return converse(
                brain,
                mic=args.mic,
                speaker=args.speaker,
                settings=_settings_from(args),
                out=sys.stdout,
                err=sys.stderr,
                widget=True,
                daemon=True,
            )
    finally:
        lock.release()


def _have_display() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))


def cmd_service(action: str) -> int:
    from voice_pipeline import service

    if action == "show":
        print(service.render_unit(sys.executable, PROJECT_ROOT / "main.py"))
        return 0
    if action == "uninstall":
        return service.uninstall()
    if action == "status":
        return service.status()
    return service.install(sys.executable, PROJECT_ROOT / "main.py")


def cmd_widget(demo: bool = False, hold: float = 2.5) -> int:
    """Run just the face window — useful for styling without speaking."""
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("error: tkinter is not available in this Python", file=sys.stderr)
        return 2

    from voice_pipeline.state import DemoFeed, StateFeed
    from voice_pipeline.widget import show

    feed = DemoFeed(hold=hold) if demo else StateFeed()
    if not demo:
        print("no feed attached — the window will sit in its sleeping state.")
        print("run `main.py converse --widget` for a live one.")
    show(feed)
    return 0


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
        from voice_pipeline.vad import ClippingGuard

        guard = ClippingGuard()
        clipped = False
        peak = 0
        with Microphone() as mic:
            started = time.monotonic()
            while time.monotonic() - started < 2.5:
                chunk = mic.read(timeout=0.2)
                if chunk:
                    peak = max(peak, _peak(chunk))
                    clipped = guard(chunk) or clipped
        if peak == 0:
            print("  FAIL microphone: 2 s of pure digital silence — the mic (or its mute "
                  "switch) is off. Run `pactl set-source-mute @DEFAULT_SOURCE@ 0`.")
            return 1
        if clipped:
            print("  FAIL microphone: input is clipping (peaks pinned at full scale). "
                  "Speech will be distorted and the wake word will not fire.")
            print("       Fix: pactl set-source-volume @DEFAULT_SOURCE@ 25%")
            return 1
        print(f"  ok   microphone capture (16 kHz mono, peak {peak}, no clipping)")
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
    return f"'{detector.name}' (vosk)"


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
    if args.command == "widget":
        return cmd_widget(demo=args.demo, hold=args.hold)
    if args.command == "doctor":
        return cmd_doctor(args.provider)
    if args.command == "service":
        action = ("uninstall" if args.uninstall else "status" if args.status
                  else "show" if args.show else "install")
        return cmd_service(action)
    if args.command == "serve":
        return cmd_serve(args)

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
            return converse(
                brain,
                mic=args.mic,
                speaker=args.speaker,
                settings=_settings_from(args),
                out=sys.stdout,
                err=sys.stderr,
                widget=args.widget,
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
