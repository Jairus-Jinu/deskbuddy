"""Live duplex audio through PortAudio (sounddevice).

The old `audio.py` shells out to `arecord`/`aplay`, which can only produce one
fixed-length file at a time — fine for a push-to-talk prototype, useless for a
conversation that has to hear when you start and stop speaking.

This module keeps a continuous 16 kHz capture stream alive and hands frames to
whoever asks, and plays TTS audio through a stream that can be stopped mid-word
for barge-in. Both are plain blocking calls so the turn loop stays readable.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

MIC_RATE = 16_000
FRAME_SAMPLES = 512  # 32 ms at 16 kHz — the window Silero VAD expects


class AudioDeviceError(RuntimeError):
    """Raised when no usable input/output device is present."""


def _resolve_device(spec: str | int | None, kind: str) -> int | None:
    """Turn a CLI device spec into a PortAudio index.

    Accepts an index, a full device name, or a case-insensitive substring so
    `--mic digital` is enough on a machine with a dozen ALSA devices.
    """
    if spec is None:
        return None
    try:
        import sounddevice as sd
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise AudioDeviceError("sounddevice is not installed (pip install sounddevice)") from exc

    wanted = "max_input_channels" if kind == "input" else "max_output_channels"
    if isinstance(spec, int) or str(spec).isdigit():
        index = int(spec)
        devices = sd.query_devices()
        if index >= len(devices) or devices[index][wanted] < 1:
            raise AudioDeviceError(f"device {index} is not an {kind} device")
        return index

    needle = str(spec).lower()
    for index, device in enumerate(sd.query_devices()):
        if device[wanted] > 0 and needle in device["name"].lower():
            return index
    raise AudioDeviceError(f"no {kind} device matches {spec!r} — try `python main.py devices`")


@dataclass
class MicLevel:
    """Cheap level report used by `doctor` to catch a muted microphone."""

    peak: int
    muted_hint: str = ""


class Microphone:
    """A never-closing capture stream with a droppable frame queue.

    Frames are int16 mono at 16 kHz. The queue is bounded: if the consumer
    stalls we drop the oldest audio rather than growing without limit, which is
    the right trade-off when the goal is "what did they just say" rather than
    "transcribe the whole session".
    """

    def __init__(self, device: str | int | None = None, max_frames: int = 400) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise AudioDeviceError("sounddevice is not installed (pip install sounddevice)") from exc

        self._sd = sd
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=max_frames)
        self._device = _resolve_device(device, "input")
        try:
            self._stream = sd.InputStream(
                samplerate=MIC_RATE,
                channels=1,
                dtype="int16",
                blocksize=FRAME_SAMPLES,
                device=self._device,
                callback=self._on_audio,
            )
        except Exception as exc:  # noqa: BLE001 - PortAudio raises several types
            raise AudioDeviceError(f"could not open microphone: {exc}") from exc

    def _on_audio(self, indata, frames, time_info, status) -> None:  # noqa: ANN001, ARG002
        if status:  # overflow/underflow — drop the frame, do not crash the stream
            return
        try:
            self._queue.put_nowait(bytes(indata))
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass

    def start(self) -> "Microphone":
        self._stream.start()
        return self

    def stop(self) -> None:
        self._stream.stop()

    def close(self) -> None:
        self._stream.close()

    def __enter__(self) -> "Microphone":
        return self.start()

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def read(self, timeout: float = 1.0) -> bytes | None:
        """Next chunk of PCM, or None if nothing arrived within `timeout`."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def read_samples(self, count: int, timeout: float = 1.0) -> bytes | None:
        """Exactly `count` samples (2 bytes each), or None on timeout."""
        need = count * 2
        buffer = bytearray()
        while len(buffer) < need:
            chunk = self.read(timeout=timeout)
            if chunk is None:
                return None
            buffer.extend(chunk)
        return bytes(buffer[:need])

    def flush(self) -> None:
        """Discard audio captured so far (after playback, before listening)."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return


class Speaker:
    """Streaming 24 kHz playback that can be cancelled mid-sentence."""

    def __init__(self, device: str | int | None = None, rate: int = 24_000) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise AudioDeviceError("sounddevice is not installed (pip install sounddevice)") from exc

        self._sd = sd
        self.rate = rate
        self._device = _resolve_device(device, "output")
        self._stream = None
        self._cancelled = threading.Event()

    def _ensure_stream(self) -> None:
        if self._stream is not None:
            return
        try:
            self._stream = self._sd.OutputStream(
                samplerate=self.rate,
                channels=1,
                dtype="float32",
                device=self._device,
            )
            self._stream.start()
        except Exception as exc:  # noqa: BLE001 - PortAudio raises several types
            raise AudioDeviceError(f"could not open speaker: {exc}") from exc

    def cancel(self) -> None:
        """Stop the current utterance as soon as the current chunk is written."""
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def play(self, samples, on_chunk=None) -> bool:  # noqa: ANN001
        """Write a float32 mono array. Returns False if playback was cancelled.

        `on_chunk` runs between writes — the conversation loop uses it to check
        for barge-in without a second thread.
        """
        self._ensure_stream()
        self._cancelled.clear()
        import numpy as np

        block = 1024
        for start in range(0, len(samples), block):
            if self._cancelled.is_set():
                return False
            chunk = np.asarray(samples[start : start + block], dtype="float32").reshape(-1, 1)
            self._stream.write(chunk)
            if on_chunk is not None and on_chunk():
                self.cancel()
                return False
        return True

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    def __enter__(self) -> "Speaker":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
