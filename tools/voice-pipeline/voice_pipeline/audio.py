"""WAV capture/playback through the system audio stack.

Record path uses the `sounddevice`-free route: it shells out to `ffmpeg` when
available (PipeWire/ALSA friendly, resamples cleanly), falling back to `arecord`.
Playback uses `aplay`/`ffplay`. Keeping this dependency-free means the same WAV
files move to the ESP32 later unchanged (16 kHz mono PCM for STT).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

STT_RATE = 16_000
STT_CHANNELS = 1
TTS_RATE = 24_000


class AudioError(RuntimeError):
    """Raised when no usable capture/playback backend is present."""


def _have(binary: str) -> bool:
    return shutil.which(binary) is not None


def record_wav(
    path: Path,
    seconds: float,
    rate: int = STT_RATE,
    channels: int = STT_CHANNELS,
    input_device: str | None = None,
) -> Path:
    """Capture `seconds` of mono PCM into a 16-bit WAV at `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)

    if _have("arecord"):
        cmd = [
            "arecord",
            "-q",
            "-f", "S16_LE",
            "-r", str(rate),
            "-c", str(channels),
            "-d", str(max(1, round(seconds))),
            str(path),
        ]
        if input_device:
            cmd[1:1] = ["-D", input_device]
    elif _have("ffmpeg"):
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "pulse", "-i", input_device or "default",
            "-t", str(seconds),
            "-ac", str(channels), "-ar", str(rate),
            "-sample_fmt", "s16",
            str(path),
        ]
    else:
        raise AudioError("need `arecord` or `ffmpeg` on PATH to record")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not path.exists():
        raise AudioError(f"capture failed: {proc.stderr.strip() or '(no stderr)'}")
    return path


def play_wav(path: Path, output_device: str | None = None) -> None:
    """Play a WAV file through the default speaker."""
    if _have("aplay"):
        cmd = ["aplay", "-q", str(path)]
        if output_device:
            cmd[1:1] = ["-D", output_device]
    elif _have("ffplay"):
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", str(path)]
    else:
        raise AudioError("need `aplay` or `ffplay` on PATH to play audio")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AudioError(f"playback failed: {proc.stderr.strip() or '(no stderr)'}")


def wav_duration(path: Path) -> float:
    """Seconds of audio in a WAV file (0.0 if unreadable)."""
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            return frames / float(handle.getframerate() or 1)
    except (wave.Error, OSError):
        return 0.0


def is_silent(path: Path, threshold: int = 250) -> bool:
    """Rough silence check on 16-bit PCM — cheap guard before paying for STT."""
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, OSError):
        return True
    if not frames:
        return True
    peak = 0
    for index in range(0, len(frames) - 1, 2):
        sample = int.from_bytes(frames[index:index + 2], "little", signed=True)
        peak = max(peak, abs(sample))
        if peak >= threshold:
            return False
    return True


def temp_wav(suffix: str = ".wav") -> Path:
    """A temp WAV path owned by this process."""
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    handle.close()
    return Path(handle.name)
