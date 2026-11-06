"""Microphone capture for wake listening. VAD-gated short buffers only.

PRIVACY (hard rules from the founder):
  * Raw audio NEVER persists: no disk writes, no network sends, from this module.
    The only outputs are (a) int16 chunks handed to the in-process detector and
    (b) scalar energy stats. If the process dies there is nothing left behind.
  * The rolling buffer keeps ~buffer_ms of audio in RAM and is circular.

The capture thread is isolated behind Source so tests can inject frames:
    src = FrameSource(frames=[...])    # fake mic, same interface
    real = MicSource()                 # sounddevice, if installed
"""
from __future__ import annotations

import collections
import threading
import time
from typing import Callable, Iterable

import numpy as np  # present in venv probe (deps pillow/numpy pulled in transitively)

SAMPLE_RATE = 16_000          # 16 kHz mono per spec
FRAME_MS = 30                 # webrtcvad granularity: 10/20/30 ms only
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000


def frame_bytes(nframes: int = 1) -> int:
    return np.int16().nbytes * FRAME_SAMPLES * nframes


def rms(pcm_int16: bytes | np.ndarray) -> float:
    a = np.frombuffer(pcm_int16, dtype=np.int16) if isinstance(pcm_int16, (bytes, bytearray)) else pcm_int16
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(a.astype(np.float64) ** 2)))


class VadGate:
    """webrtcvad wrapper with graceful fallback to an energy noise gate.

    webrtcvad is optional: the venv probe found no cp314 wheels and only
    webrtcvad-wheels is gal available for 3.11. So default = energy gate; if the
    import works we use real WebRTC VAD mode 2-3 (voice-activity ON only feeds
    the detector; silence burns the rolling buffer instead of being scored)."""

    def __init__(self, aggressiveness: int = 2):
        self.mode = int(aggressiveness)
        self.fallback = "energy"
        try:
            import webrtcvad  # noqa
            self._vad = webrtcvad.Vad(self.mode)
            self.fallback = "webrtcvad"
        except Exception:
            self._vad = None

    def is_speech(self, pcm30: bytes) -> bool:
        """pcm30 must be exactly one 30 ms 16 kHz mono int16 frame."""
        if len(pcm30) == 0:
            return False
        if self._vad is not None:
            try:
                return bool(self._vad.is_speech(pcm30, SAMPLE_RATE))
            except Exception:
                pass
        if rms(pcm30) < 300:      # permissive energy gate (tunable upstream)
            return False
        return True


class RingBuffer:
    """Circular slide window of the most recent `maxlen_frames` 30 ms frames."""

    def __init__(self, maxlen_frames: int = 20):  # 20 * 30ms = 600ms
        self.buf = collections.deque(
            [b"\x00\x00" * FRAME_SAMPLES] * maxlen_frames, maxlen=maxlen_frames)
        self.maxlen_frames = maxlen_frames

    def push(self, frame: bytes) -> None:
        self.buf.append(frame)

    def window(self) -> bytes:
        return b"".join(self.buf)

    def frames(self) -> list[bytes]:
        return list(self.buf)

    def clear(self) -> None:
        for _ in range(self.maxlen_frames):
            self.push(b"\x00\x00" * FRAME_SAMPLES)


class MicSource:
    """sounddevice/PortAudio capture -> 30 ms int16 frames via callback.

    Import of sounddevice is deferred so unit tests on headless machines work.
    """

    def __init__(self, on_frame: Callable[[bytes], None], device: int | None = None):
        self.on_frame = on_frame
        self.device = device
        self._stream = None
        self.error: str | None = None

    def start(self) -> None:
        import sounddevice as sd  # deferred; may raise -> caller shows degraded state

        def _cb(indata, nframes, tstatus, x) -> None:  # real callback deadline
            if x:
                return
            self.on_frame(indata[:, 0].astype(np.int16).tobytes())

        self._stream = sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1,
                                         dtype="int16", blocksize=FRAME_SAMPLES,
                                         device=self.device, callback=_cb)
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


class FrameSource:
    """Fake microphone for tests/simulation: pull-based, paced for realism."""

    def __init__(self, frames: Iterable[bytes], pace_s: float = 0.0):
        self._frames = list(frames)
        self._i = 0
        self._t0: float | None = None
        self.pace_s = pace_s

    def start(self) -> None:
        self._t0 = time.monotonic()

    def stop(self) -> None:
        pass

    def read(self) -> bytes | None:
        if self._i >= len(self._frames):
            return None
        if self.pace_s:  # pace playback so multi-frame pipelines run in real time
            target = self._t0 + self._i * self.pace_s
            delay = target - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        f = self._frames[self._i]
        self._i += 1
        return f


def synthetic_speech_frames(duration_s: float = 0.5, seed: int = 3,
                            level: int = 6000) -> list[bytes]:
    """Deterministic loud pseudo-speech (noise burst) for tests/simulation.
    NOT audio for recognition -- only used to prove pipeline plumbing + timing."""
    rng = np.random.default_rng(seed)
    n = int(duration_s * SAMPLE_RATE)
    sig = (rng.normal(0, 1, n) * level).astype(np.int16)
    return [sig[i:i + FRAME_SAMPLES].tobytes()
            for i in range(0, n - FRAME_SAMPLES + 1, FRAME_SAMPLES)]


def silence_frames(duration_s: float = 0.5) -> list[bytes]:
    n = int(duration_s * SAMPLE_RATE)
    return [np.zeros(n, dtype=np.int16)[i:i + FRAME_SAMPLES].tobytes()
            for i in range(0, n - FRAME_SAMPLES + 1, FRAME_SAMPLES)]


__all__ = ["SAMPLE_RATE", "FRAME_MS", "FRAME_SAMPLES", "frame_bytes", "rms",
           "VadGate", "RingBuffer", "MicSource", "FrameSource",
           "synthetic_speech_frames", "silence_frames"]
