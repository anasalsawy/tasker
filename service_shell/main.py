"""Hands Always-On Shell — resident entrypoint. Tray + wake <1s ack + ambient
context + localhost API, all composed from shell.* symbols that actually exist.

run:      .venv\\Scripts\\python.exe main.py            (tray + wake + API)
headless: .venv\\Scripts\\python.exe main.py --no-tray  (API + wake only)
sim demo: .venv\\Scripts\\python.exe main.py --sim-say "hey hands what's 5+7"
once ctx: .venv\\Scripts\\python.exe main.py --context-once

Privacy rails: RAW AUDIO NEVER LEAVES THE PROCESS (capture -> VAD gate -> RAM ring
-> detector, nothing streamed/persisted). Ambient context = foreground window
title/process via ctypes every ~20 s, in memory only unless config opts into JSONL.
No screenshots (capture isn't implemented / never auto-enabled), no keylogging.
"""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import time

from shell import __version__
from shell.audio import MicSource, silence_frames, synthetic_speech_frames
from shell.chain import Chain
from shell.config import ACK_DEADLINE_S, ShellConfig
from shell.context import ContextSampler
from shell.httpd import ShellAPI
from shell.notify import acknowledge, configure_tts, notify
from shell.tray import TrayPresence
from shell.wake import PsEngine, SimulatedEngine, WakePipeline, build_engine

log = logging.getLogger("hands.main")

CAPTURE_WINDOW_S = 6.0        # after wake+ack: hand audio lane briefly, then resume


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="hands-shell", description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=None, help="path to config.toml")
    ap.add_argument("--no-tray", action="store_true", help="headless (API + wake only)")
    ap.add_argument("--no-mic", action="store_true", help="skip microphone (text/API only)")
    ap.add_argument("--engine", default=None,
                    help="force wake engine: porcupine|openwakeword|pocketsphinx|"
                         "energy_vad|simulated|auto")
    ap.add_argument("--sim-say", metavar="UTTERANCE", default=None,
                    help="one-shot simulated wake->chain->reply demo, then exit")
    ap.add_argument("--context-once", action="store_true",
                    help="sample the foreground window once, print summary, exit")
    ap.add_argument("--port", type=int, default=None, help="override [http] port")
    return ap.parse_args(argv)


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout)


class ShellApp:
    """Owns every resident thread. Nothing here blocks the wake->ack path."""

    def __init__(self, cfg: ShellConfig, use_tray: bool = True, use_mic: bool = True):
        self.cfg = cfg
        self.use_tray = use_tray
        self.use_mic = use_mic
        self.stop = threading.Event()

        # --- persona chain: ambient context feeds it; done callback feeds tray ---
        self.ctx = ContextSampler(cfg.context)
        self.chain = Chain(cfg, context_summary=self.ctx.summary,
                           on_done=self._on_intent_done)

        # --- wake: ladder engine + pipeline (ack is the on_wake surface) ---
        self.engine = build_engine(cfg.wake, logger=log)
        self.attempts = getattr(self.engine, "attempts", {})
        self.pipeline = WakePipeline(cfg.wake, self.engine,
                                     on_wake=self._on_wake,
                                     post_wake=self._post_wake)
        self.mic: MicSource | None = None
        self.mic_error = ""
        self._capture_timer: threading.Timer | None = None

        # --- tray presence + localhost API ---
        self.tray = TrayPresence(on_quit=self.shutdown) if use_tray else None
        import shell.notify as notify_mod
        notify_mod.TRAY = self.tray              # ack/balloon see the tray if present
        configure_tts(cfg.tts_voice_cmd if cfg.ack_tts else None)
        self.api = ShellAPI(cfg, self.chain,
                            state_fn=self.state, wake_arm=self.wake_arm)

    # ---------------- wake handlers (order: ack FIRST, then everything else) ----

    def _on_wake(self, ev) -> float:
        """Synchronous proof of life; must finish well under ACK_DEADLINE_S."""
        return acknowledge(engine=ev.engine, score=ev.score,
                           sound=self.cfg.ack_sound,
                           tts_text="Yes?" if self.cfg.ack_tts else None)

    def _post_wake(self, ev) -> None:
        """Runs AFTER ack returned. Opens the persona session and hands the
        audio lane a capture window; wake spotting pauses then resumes."""
        sid = self.chain.note_wake()
        log.info("wake session %s opened (capture window %.1fs)", sid, CAPTURE_WINDOW_S)
        self.pipeline.pause()
        if self.tray:
            self.tray.set_state("listening")
        if self._capture_timer:
            self._capture_timer.cancel()
        self._capture_timer = threading.Timer(
            CAPTURE_WINDOW_S, self._resume_spotting)
        self._capture_timer.daemon = True
        self._capture_timer.start()

    def _resume_spotting(self) -> None:
        if self.stop.is_set():
            return
        self.pipeline.resume()
        if self.tray and self.tray.state == "listening":
            self.tray.set_state("idle")

    def _on_intent_done(self, resp) -> None:
        """Chain worker finished a persona run (any thread) -> notify surface."""
        head = (resp.text or resp.error or "").strip().splitlines()
        msg = head[0][:120] if head else "no reply"
        if self.tray:
            self.tray.set_state("done" if resp.status == "done" else "error")
            self.tray.notify(f"Hands ({resp.route or 'chain'}): {resp.status}", msg)
            threading.Timer(4.0, self._resume_spotting).start()
        notify("Hands", msg)

    # ---------------- shared hooks for the API ---------------------------------

    def wake_arm(self) -> bool:
        """POST /wake: arm engines that support it (simulated/text lane)."""
        return self.pipeline.arm_text()

    def state(self) -> dict:
        ev = self.pipeline.last
        return {
            "version": __version__,
            "wake_engine": self.engine.name,
            "engine_note": getattr(self.engine, "note", ""),
            "ladder_attempts": self.attempts,
            "frames_seen": self.pipeline.frames_seen,
            "detector_calls": self.pipeline.detector_calls,
            "spotting_paused": bool(self.pipeline._paused),
            "last_wake": ev.as_dict() if ev else None,
            "ack_deadline_s": ACK_DEADLINE_S,
            "mic": (not self.use_mic and "disabled") or
                   (self.mic is not None and "live") or self.mic_error or "starting",
            "tray": (self.tray and ("ok" if self.tray.ok else "degraded: " + self.tray.error)) or "off",
            "intents": len(self.chain._order),
        }

    # ---------------- audio lane ------------------------------------------------

    def _mic_frames(self, frame: bytes) -> None:
        """PortAudio callback body: frame -> pipeline. Guarded so a slow detector
        tick can never overlap — drops instead (audio is throw-away RAM)."""
        if self._mic_busy:
            return
        self._mic_busy = True
        try:
            self.pipeline.push_frame(frame)
        finally:
            self._mic_busy = False

    _mic_busy = False

    def _mic_loop(self) -> None:
        """Mic with restart backoff: bind failures retry every 15 s; the shell
        stays alive either way (API + tray + text intents keep working)."""
        while not self.stop.is_set():
            src = MicSource(self._mic_frames)
            try:
                src.start()
                self.mic = src
                self.mic_error = ""
                log.info("microphone live (16kHz mono, 30ms frames)")
                self.stop.wait()               # callback-driven; sleep cheap
                src.stop()
                self.mic = None
                return                         # stop requested -> thread exit
            except Exception as exc:
                self.mic = None
                self.mic_error = f"{type(exc).__name__}: {str(exc)[:160]}"
                log.warning("DEGRADED mic (%s); retry in 15s", self.mic_error)
                self.stop.wait(15.0)

    # ---------------- lifecycle ----------------------------------------------

    def run(self) -> int:
        self.ctx.start()
        port = None
        for wait in (0.5, 15.0):               # quick retry then 15 s watchdog
            try:
                port = self.api.start()
                break
            except OSError as exc:
                log.warning("API bind failed (%s); retry in %.0fs", exc, wait)
                if self.stop.wait(wait):
                    return 0
        if port is None:
            log.error("DEGRADED: localhost API never bound — continuing tray+wake only")
        if self.tray:
            t = threading.Thread(target=self.tray.run, name="tray", daemon=True)
            t.start()
            self.stop.wait(2.0)
            if not self.tray.ok:
                log.warning("tray DEGRADED: %s", self.tray.error)
        if self.use_mic:
            threading.Thread(target=self._mic_loop, name="mic", daemon=True).start()
        else:
            log.info("microphone disabled by flag — wake via POST /wake or /intent")
        log.info("Hands shell resident: engine=%s port=%s tray=%s mic=%s",
                 self.engine.name, port or "-", self.tray and "on" or "off",
                 self.use_mic and "arming" or "off")
        ack = ("ack<deadline" if ACK_DEADLINE_S <= 1.0 else "check config")
        log.info("wake→ack commitment: %s (%.1fs)", ack, ACK_DEADLINE_S)
        try:
            while not self.stop.is_set():
                self.stop.wait(1.0)
        except KeyboardInterrupt:
            log.info("Ctrl-C -> shutdown")
        self.shutdown()
        return 0

    def shutdown(self) -> None:
        if self.stop.is_set():
            return
        log.info("shutdown requested")
        self.stop.set()
        if self._capture_timer:
            self._capture_timer.cancel()
        self.ctx.stop()
        if self.mic:
            try:
                self.mic.stop()
            except Exception:
                pass
        try:
            self.api.stop()
        except Exception:
            pass
        if self.tray:
            self.tray.stop()


# --------------------------- one-shot demo lanes -------------------------------

def sim_say(cfg: ShellConfig, utterance: str) -> int:
    """Scripted wake -> ack -> delegate -> reply, no mic no tray no server."""
    engine = SimulatedEngine(cfg.wake)
    log.info("sim: engine=simulated (SIMULATED wake backend)")
    chain = Chain(cfg, context_summary=lambda: "ambient: sim run (no sampling)",
                  on_done=None)

    def on_wake(ev):
        return acknowledge(engine=ev.engine, score=ev.score, sound=cfg.ack_sound,
                           tts_text=None)

    def post_wake(ev):
        post_wake.sid = chain.note_wake()

    post_wake.sid = None
    pipe = WakePipeline(cfg.wake, engine, on_wake=on_wake, post_wake=post_wake)
    utt = utterance
    for w in cfg.wake.words:                      # strip the wake word itself
        if utt.lower().startswith(w):
            utt = utt[len(w):].strip()
            break
    pipe.arm_text()
    events = []
    for f in silence_frames(0.3) + synthetic_speech_frames(0.4):
        ev = pipe.push_frame(f)
        if ev:
            events.append(ev)
            break
    if not events:
        log.error("sim: scripted wake did not fire"); return 1
    ev = events[0]
    print(f"WAKE engine={ev.engine} ack_ms={ev.ack_latency_s * 1000:.1f} "
          f"under_deadline={0 <= ev.ack_latency_s <= ACK_DEADLINE_S}")
    resp = chain.submit(utt or "status check", session_id=post_wake.sid,
                        source="simulated")
    done = chain.wait(resp.req_id, timeout_s=8.0)
    snap = (done or resp).snapshot()
    print(f"INTENT status={snap['status']} route={snap['route']} "
          f"tools={len(snap['tool_calls'])} parked={len(snap['parked_tools'])}")
    print("REPLY:", (snap["text"] or snap["error"] or "(empty)")[:400])
    return 0 if snap["status"] in ("done", "error") else 1


def context_once(cfg: ShellConfig) -> int:
    cs = ContextSampler(cfg.context)
    got = cs.sample_once()
    print("sample:", got[0] if got else None)
    print("summary:\n" + cs.summary())
    return 0 if got else 2


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = ShellConfig.load(args.config)
    if args.engine:
        cfg.wake.engine = args.engine
    if args.port:
        cfg.http.port = args.port
    setup_logging(cfg.log_level)
    log.info("Hands Always-On Shell v%s starting", __version__)
    if args.sim_say:
        return sim_say(cfg, args.sim_say)
    if args.context_once:
        return context_once(cfg)
    app = ShellApp(cfg, use_tray=not args.no_tray, use_mic=not args.no_mic)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
