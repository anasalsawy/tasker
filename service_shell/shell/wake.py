"""Wake detection ladder + wake->ack pipeline (README: 'Wake engine notes').

Ladder order (founder spec): porcupine -> openwakeword -> pocketsphinx ->
energy_vad -> simulated. Resolution on THIS box with engine="auto":
  1. pvporcupine   -> not importable; even installed it needs a Picovoice console
                      AccessKey + custom 'hey hands' .ppn. Wired anyway via
                      [wake] sim_access_key / sim_prebuilt_keyword.
  2. openwakeword  -> installed; ONNX load verified offline here (~30s first zoo
                      fetch, then cached) BUT public zoo has no 'hey hands' and
                      custom training fails on this Windows box, so the ctor
                      RAISES (clear reason) unless [wake] oww_model_paths lists
                      trained models -> ladder skips to...
  3. pocketsphinx  -> WINNER: 5.1.1 wheel, bundled en-us model + CMU dict verified
                      on disk (contains hands/hey/tasker/operator); continuous
                      keyphrase spotting, fully local. API limit: keyphrase= takes
                      ONE phrase -> primary = words[0]; the extra allowlist phrases
                      arm through text intents (POST /intent) as documented.
  4. energy_vad    -> DEGRADED: sustained voiced burst = wake (word_specific
                      False; loud speech fires; /status flags engine_degraded).
  5. simulated     -> *** SIMULATION BACKEND, CLEARLY MARKED *** (spec fallback so
                      the loop is testable with zero installs): arm(), the next
                      voiced window fires exactly once.

PRIVACY: VAD gate lets only plausible-speech frames into scoring; the window
buffer is in-RAM only; nothing persisted, nothing sent, raw audio never leaves.

ACK PATH (requirement 3): decision -> on_wake() with NO classification/network/
disk in between; the test asserts measured ack latency < ACK_DEADLINE_S (1.0 s).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

import time

from .audio import FRAME_MS, RingBuffer, VadGate, frame_bytes, rms, SAMPLE_RATE
from .config import ACK_DEADLINE_S, WakeConfig

log = logging.getLogger("hands.wake")


class WakeEngine:
    name = "base"
    word_specific = True
    note = ""

    def score_frame(self, frame: bytes) -> float:
        """Cheap per-frame path; engines that stream return >0 when spotted."""
        return 0.0

    def score_window(self, pcm16: bytes) -> float:
        """Batch path over the rolling window (>=0..1; fires at threshold)."""
        raise NotImplementedError

    def reset(self) -> None:
        pass

    def close(self) -> None:
        pass


class PsEngine(WakeEngine):
    """PocketSphinx continuous keyphrase spotting, frame-fed after the VAD gate."""
    name = "pocketsphinx"

    def __init__(self, cfg: WakeConfig):
        import os
        import pocketsphinx as ps
        base = ps.get_model_path("en-us")
        hmm = os.path.join(base, "en-us")
        dic = os.path.join(base, "cmudict-en-us.dict")
        for p in (hmm, dic):
            if not os.path.exists(p):
                raise RuntimeError(f"pocketsphinx bundled model missing: {p}")
        self.keyphrase = (cfg.words or ["hey hands"])[0]
        self._dec = ps.Decoder(hmm=hmm, dict=dic, keyphrase=self.keyphrase,
                               samprate=SAMPLE_RATE, remove_noise=True)
        self._dec.start_utt()
        self._primed = 0          # frames seen this utterance; avoid hyp() mid-prime
        self.note = (f"audio spotting on '{self.keyphrase}'; wake extras arm via "
                     "text intents")

    def score_frame(self, frame: bytes) -> float:
        try:
            self._dec.process_raw(frame, False, False)
            self._primed += 1
            if self._primed >= 3 and self._dec.hyp() is not None:
                return 1.0
        except Exception:
            self.reset()
        return 0.0

    def score_window(self, pcm16: bytes) -> float:
        self.reset()
        step = frame_bytes(4)
        got = False
        for i in range(0, len(pcm16), step):
            part = pcm16[i:i + step]
            if not part:
                continue
            try:
                self._dec.process_raw(part, False, False)
                if self._dec.hyp() is not None:
                    got = True
                    break
            except Exception:
                break
        try:
            self._dec.end_utt()
        except Exception:
            pass
        return 1.0 if got else 0.0

    def reset(self) -> None:
        try:
            self._dec.start_utt()
        except Exception:
            pass
        self._primed = 0


class OwwEngine(WakeEngine):
    """OpenWakeWord. STUB-DEGRADED on this box: only constructs with trained custom
    models in [wake] oww_model_paths (no stock 'hey hands'; README 'Wake engine
    notes'). Then it wins the auto ladder if import+load succeed."""
    name = "openwakeword"

    def __init__(self, cfg: WakeConfig):
        paths = [p for p in (cfg.oww_model_paths or []) if str(p).strip()]
        if not paths:
            raise RuntimeError(
                "openwakeword: public zoo has no 'hey hands' and custom generation "
                "fails offline here; train one (`oww train -d <samples> -t hey_hands`) "
                "and set [wake] oww_model_paths.")
        from openwakeword.model import Model
        self._m = Model(wakeword_models=paths, inference_framework="onnx")
        self.note = "custom models: " + ", ".join(paths)

    def score_window(self, pcm16: bytes) -> float:
        import numpy as np
        a = np.frombuffer(pcm16, dtype="int16")
        step = int(0.08 * SAMPLE_RATE)
        best = 0.0
        for i in range(step, len(a) + 1, step):
            pred = self._m.predict(a[i - step:i].astype(np.float32) / 32768.0)
            for arr in pred.values():
                v = np.asarray(arr).ravel()
                if v.size:
                    best = max(best, float(v[-1]))
        return best

    def reset(self) -> None:
        try:
            self._m.reset()
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._m.close()
        except Exception:
            pass


class PorcupineEngine(WakeEngine):
    """pvporcupine: requires console AccessKey + .ppn (none exist offline). Wired so
    a key owner gets the best engine via config; otherwise ctor raises: documented."""
    name = "porcupine"

    def __init__(self, cfg: WakeConfig):
        if not (cfg.sim_access_key and cfg.sim_prebuilt_keyword):
            raise RuntimeError(
                "pvporcupine: needs [wake] sim_access_key + sim_prebuilt_keyword; "
                "'hey hands' is not a stock keyword (Picovoice console training).")
        import array  # noqa: F401 (kept for clarity of frame slicing)
        import pvporcupine
        self._h = pvporcupine.create(access_key=cfg.sim_access_key,
                                     keyword_paths=[cfg.sim_prebuilt_keyword])
        self._buf = bytearray()

    def score_frame(self, frame: bytes) -> float:
        import array as _a
        self._buf.extend(frame)
        step = self._h.frame_length * 2
        fired = 0.0
        while len(self._buf) >= step:
            ch = _a.array("h")
            ch.frombytes(bytes(self._buf[:step]))
            del self._buf[:step]
            if self._h.process(ch) >= 0:
                fired = 1.0
        return fired

    def score_window(self, pcm16: bytes) -> float:
        return self.score_frame(pcm16)

    def close(self) -> None:
        try:
            self._h.delete()
        except Exception:
            pass


class EnergyVadEngine(WakeEngine):
    """DEGRADED always-available arm: ~350 ms of gated speech = wake. NOT
    word-specific (any loud speech fires); note surfaces in /status."""
    name = "energy_vad"
    word_specific = False
    note = "DEGRADED wake: voiced bursts, not word-specific"

    def __init__(self, cfg: WakeConfig):
        self.floor = max(300.0, float(cfg.energy_floor))
        self._voiced_ms = 0.0

    def score_frame(self, frame: bytes) -> float:
        if rms(frame) >= self.floor:
            self._voiced_ms += FRAME_MS
            if self._voiced_ms >= 350:
                self._voiced_ms = 0.0
                return 1.0
        else:
            self._voiced_ms = 0.0
        return 0.0

    def score_window(self, pcm16: bytes) -> float:
        return 1.0 if rms(pcm16) >= self.floor else 0.0

    def reset(self) -> None:
        self._voiced_ms = 0.0


class SimulatedEngine(WakeEngine):
    """*** SIMULATED wake backend - CLEARLY MARKED (spec fallback) ***.
    Deterministic: arm('also called by tests/') then the next voiced fire window
    returns 1.0 exactly once. Not detection; documented via /status."""
    name = "simulated"
    word_specific = False
    note = "SIMULATED wake backend (scripted; real audio detection NOT active)"

    def __init__(self, cfg: WakeConfig):
        self._floor = max(50.0, float(cfg.energy_floor) * 0.2)
        self._armed = False
        self.hits = 0

    def arm(self) -> None:
        self._armed = True

    def score_window(self, pcm16: bytes) -> float:
        if self._armed and rms(pcm16) >= self._floor:
            self._armed = False
            self.hits += 1
            return 1.0
        return 0.0


class MockWakeEngine(WakeEngine):
    """Test double: Sci decides after N calls, both paths.” From spec test (b):
    'wake pipeline unit-tested around mock audio frames + mock detector'."""
    name = "mock"

    def __init__(self, fire_after: int = 1, score: float = 1.0):
        self.fire_after = fire_after
        self.fixed = score
        self.calls = 0

    def score_frame(self, frame: bytes) -> float:
        self._bump()
        return self.fixed if self.calls >= self.fire_after and self.fire_after > 0 else 0.0

    def score_window(self, pcm16: bytes) -> float:
        self._bump()
        return self.fixed if self.calls >= self.fire_after else 0.0

    def _bump(self) -> None:
        self.calls += 1


# ---------------------------------------------------------------------------

_ENGINES = {
    "porcupine": PorcupineEngine,
    "openwakeword": OwwEngine,
    "pocketsphinx": PsEngine,
    "energy_vad": EnergyVadEngine,
    "simulated": SimulatedEngine,
}


def build_engine(cfg: WakeConfig, logger: logging.Logger | None = None) -> WakeEngine:
    """Ladder resolution with reasons; .attempts(dict name->why skipped) for UI."""
    lg = logger or log
    forced = (cfg.engine or "auto").strip().lower()
    order = [forced] if forced != "auto" else ["porcupine", "openwakeword",
                                               "pocketsphinx", "energy_vad",
                                               "simulated"]
    attempts: dict[str, str] = {}
    for name in order:
        cls = _ENGINES.get(name)
        if cls is None:
            attempts[name] = "unknown [wake] engine name"
            continue
        try:
            eng = cls(cfg)
            eng.attempts = attempts  # type: ignore[attr-defined]
            lg.info("wake engine resolved: %s", eng.name)
            return eng
        except Exception as exc:
            attempts[name] = str(exc).strip().splitlines()[0][:250]
            lg.warning("wake ladder: %s skipped -> %s", name, attempts[name])
    eng = SimulatedEngine(cfg)
    eng.attempts = attempts  # type: ignore[attr-defined]
    why = "; ".join(f"{k}: {v}" for k, v in attempts.items())[:200]
    eng.note = "SIMULATED fallback - every engine failed. " + why
    lg.error("all wake engines unavailable -> SIMULATED (loop stays testable)")
    return eng


@dataclass
class WakeEvent:
    fired_at: float
    ack_at: float
    engine: str
    score: float
    win_rms: float
    window_ms: int
    word_specific: bool

    @property
    def ack_latency_s(self) -> float:
        return (self.ack_at - self.fired_at) if self.ack_at else -1.0

    def as_dict(self) -> dict:
        return {"engine": self.engine, "score": round(self.score, 3),
                "ack_latency_s": round(self.ack_latency_s, 4),
                "ack_under_deadline": 0.0 <= self.ack_latency_s <= ACK_DEADLINE_S,
                "word_specific": self.word_specific,
                "window_ms": self.window_ms}


class WakePipeline:
    """frame -> VAD gate -> ring -> engine -> on_wake immediately.

    on_wake is the whole ack surface (tray light + beep). post_wake runs only
    AFTER ack completes (capture-window handoff). A fire needs score >=
    threshold and the per-engine cooldown; between them no classification,
    no I/O. Tests inject MockWakeEngine + FrameSource to measure ack time."""

    def __init__(self, cfg: WakeConfig, engine: WakeEngine,
                 on_wake: Callable[[WakeEvent], None],
                 post_wake: Callable[[WakeEvent], None] | None = None,
                 vad: VadGate | None = None):
        self.cfg = cfg
        self.engine = engine
        self.on_wake = on_wake
        self.post_wake = post_wake
        self.vad = vad or VadGate(cfg.vad_aggressiveness)
        self.ring = RingBuffer(max(4, int(round(cfg.buffer_ms / FRAME_MS))))
        self.threshold = float(cfg.threshold)
        self.cooldown_s = max(1.5, cfg.buffer_ms / 1000.0 * 2.5)
        self.events: list[WakeEvent] = []
        self.last: WakeEvent | None = None
        self.frames_seen = 0
        self.detector_calls = 0
        self._next_ok = 0.0
        self._paused = False          # capture window: spoken-command listening

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False
        self.ring.clear()

    def arm_text(self) -> bool:
        """Text-launched wake (UI typed 'hey hands ...'): engines with arm()."""
        arm = getattr(self.engine, "arm", None)
        if callable(arm):
            arm()
            return True
        return False

    def push_frame(self, frame: bytes) -> WakeEvent | None:
        """One 30 ms int16 mono frame in; returns the WakeEvent if this frame
        produced detection + ack (tests time THAT against ACK_DEADLINE_S)."""
        if self._paused or len(frame) != frame_bytes(1):
            return None
        self.frames_seen += 1
        now = time.monotonic()
        voiced = self.vad.is_speech(frame)
        self.ring.push(frame)
        if not voiced:
            return None
        score = 0.0
        try:
            score = self.engine.score_frame(frame)
            self.detector_calls += 1
            if score < self.threshold:
                score = self.engine.score_window(self.ring.window())
                self.detector_calls += 1
        except Exception as exc:
            log.warning("wake engine threw: %s", exc)
            try:
                self.engine.reset()
            except Exception:
                pass
            return None
        if score >= self.threshold:
            if now >= self._next_ok:
                self._next_ok = now + self.cooldown_s
                return self._fire(score, now)
        return None

    def _fire(self, score: float, fired_at: float) -> WakeEvent:
        ev = WakeEvent(fired_at=fired_at, ack_at=0.0, engine=self.engine.name,
                       score=score, win_rms=rms(self.ring.window()),
                       window_ms=self.ring.maxlen_frames * FRAME_MS,
                       word_specific=self.engine.word_specific)
        self.on_wake(ev)              # ACK now - no I/O between detect and this
        ev.ack_at = time.monotonic()
        self.last = ev
        self.events.append(ev)
        if len(self.events) > 64:
            self.events.pop(0)
        log.info("WAKE engine=%s score=%.2f ack_ms=%.1f (deadline %.0f ms)",
                 ev.engine, ev.score, ev.ack_latency_s * 1000,
                 ACK_DEADLINE_S * 1000)
        if self.post_wake:
            try:
                self.post_wake(ev)
            except Exception as exc:
                log.warning("post_wake failed: %s", exc)
        return ev

    def feed(self, source) -> list[WakeEvent]:
        """Drain a pull-based frame source (FrameSource/MicSource adapter)."""
        out: list[WakeEvent] = []
        if hasattr(source, "start"):
            source.start()
        while not getattr(self, "stop_requested", False):
            f = source.read() if hasattr(source, "read") else None
            if f is None:
                break
            ev = self.push_frame(f)
            if ev:
                out.append(ev)
        if hasattr(source, "stop"):
            source.stop()
        return out


__all__ = ["WakeEngine", "PsEngine", "OwwEngine", "PorcupineEngine",
           "EnergyVadEngine", "SimulatedEngine", "MockWakeEngine",
           "build_engine", "WakePipeline", "WakeEvent", "ACK_DEADLINE_S"]
