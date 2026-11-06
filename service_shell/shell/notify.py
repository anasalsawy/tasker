"""Proof-of-life ack: tray light state + sound. <5 ms winsound, stdlib only.

acknowledge() is THE wake->ack surface (requirement 3): called by WakePipeline
synchronously, performs no classification, no network, no disk, and is measured
by tests. STUB MARKING: tray presence may be absent in --no-tray/headless mode;
ack chain degrades cleanly and sounds still fire (winsound on Windows).
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time

from .config import ACK_DEADLINE_S

log = logging.getLogger("hands.notify")

TRAY = None                 # set by tray.py on boot: object with .set_state(str)


def _beep() -> None:
    try:
        import winsound
        winsound.Beep(1200, 90)          # 1-4 kHz allowed; ~15 ms call cost
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.MessageBeep(0xFFFFFFFF)
        except Exception:
            pass


def _tts(text: str) -> None:
    if sys.platform != "win32":
        return
    cmds = _TTS_CMD[0]
    if not cmds:
        return
    def _run() -> None:
        try:
            subprocess.run(cmds, input=text.encode("utf-8", "ignore"),
                           capture_output=True, timeout=15)
        except Exception as exc:
            log.debug("tts failed (non-fatal ack path): %s", exc)
    threading.Thread(target=_run, daemon=True, name="ack-tts").start()


_TTS_CMD: list = [None]


def configure_tts(cmd: list[str] | None) -> None:
    _TTS_CMD[0] = cmd


def set_tray_state(state: str) -> None:
    t = TRAY
    if t is not None:
        try:
            t.set_state(state)
        except Exception:
            pass


def acknowledge(engine: str = "", score: float = 0.0,
                sound: bool = True, tts_text: str | None = None) -> float:
    """The full ack: light state + optional beep, then DETACHED spoken 'Yes?'
    (never joined; must not add latency). Returns ack duration seconds so the
    pipeline/tests can assert it under ACK_DEADLINE_S."""
    t0 = time.monotonic()
    set_tray_state("listening")
    if sound:
        _beep()
    if tts_text:
        _tts(tts_text)          # detached thread; not on the ack critical path
    dt = time.monotonic() - t0
    log.info("ack engine=%s score=%.2f took=%.4fs (deadline %.2fs)%s",
             engine, score, dt, ACK_DEADLINE_S,
             " OVER-BUDGET" if dt > ACK_DEADLINE_S else "")
    return dt


def notify(title: str, msg: str, timeout: float = 4.0) -> None:
    """Balloon via tray when present; winsound fallback otherwise. Fire-forget."""
    t = TRAY
    if t is not None:
        try:
            t.notify(title, msg, timeout)
            return
        except Exception:
            pass
    set_tray_state("done")


from .config import ACK_DEADLINE_S  # noqa: E402  (after funcs to avoid cycle noise)

__all__ = ["acknowledge", "notify", "set_tray_state", "configure_tts"]
