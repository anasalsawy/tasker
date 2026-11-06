"""Ambient awareness: foreground window title + process name -> rolling in-memory
summary + "user task signature".

HARD RULES (founder requirements 4):
  * NO screenshots unless config opt-in (and even then this build only logs that
    the flag exists -- capture itself is a marked stub).
  * NO keylogging -- nothing in this module can see keystrokes.
  * Activity history stays in memory. JSONL persistence happens ONLY when
    context.opt_in_persist_jsonl = true, into var/state/ with rotation.
  * Raw values never leave the process except through the localhost API.

Implementation: pure ctypes against user32/kernel32 (zero deps). When the session
is locked/disconnected GetForegroundWindow() returns NULL -- the sampler degrades
silently (last snapshot kept, `locked=True` flag) so tests can skip gracefully.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from .config import ContextConfig, SHELL_ROOT

IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _psapi = ctypes.windll.kernel32 if hasattr(ctypes.windll, "psapi") else None
    try:
        _user32.GetForegroundWindow.restype = wt.HWND
        _user32.GetWindowTextLengthW.restype = ctypes.c_int
        _user32.GetWindowTextW.restype = ctypes.c_int
        _user32.GetWindowThreadProcessId.restype = wt.DWORD
        _kernel32.OpenProcess.restype = wt.HANDLE
        _kernel32.QueryFullProcessImageNameW.restype = wt.BOOL
    except Exception:  # pragma: no cover - very old Python
        pass

_QUERY_LIMITED_INFORMATION = 0x1000


def _grab_foreground() -> dict | None:
    """One snapshot of the foreground window. Returns None if unobtained (locked)."""
    if not IS_WINDOWS:
        return None
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:  # locked session / no desktop access -> caller degrades
            return None
        n = _user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        if n:
            _user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value or ""
        pid = wt.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app = _process_name(pid.value)
        return {"title": title, "app": app, "pid": pid.value,
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    except Exception:
        return None


def _process_name(pid: int) -> str:
    if not pid or not IS_WINDOWS:
        return ""
    try:
        h = _kernel32.OpenProcess(_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return ""
        try:
            size = wt.DWORD(32768)
            name = ctypes.create_unicode_buffer(size.value)
            if _kernel32.QueryFullProcessImageNameW(h, 0, name, ctypes.byref(size)):
                return os.path.basename(name.value)
            return ""
        finally:
            _kernel32.CloseHandle(h)
    except Exception:
        return ""


def activity_hint(app: str, title: str) -> str:
    """Cheap heuristics: what KIND of work the user signature looks like.
    Title content only -- we never open files or read contents."""
    t = (title or "").lower()
    a = (app or "").lower()
    if a in ("code.exe", "cursor.exe", "idea64.exe") or " - " in t and any(
            t.endswith(x) for x in (".py", ".ts", ".tsx", ".js", ".md", ".go")):
        return "coding"
    if any(x in t for x in (".docx", ".xlsx", ".pptx", "word", "excel", "outlook", "mail")):
        return "docs"
    if any(x in a for x in ("chrome", "msedge", "firefox", "brave")):
        return "browsing"
    if any(x in a for x in ("terminal", "console", "wt.exe", "powershell", "cmd")):
        return "shell"
    if any(x in a for x in ("teams", "zoom", "webex", "meet")):
        return "call"
    return "unknown"


class ContextSampler:
    """Polls the foreground window and keeps a rolling summary entirely in RAM."""

    FAST_POLL_S = 2.0  # on-change trigger: watch closely while the title is settling

    def __init__(self, cfg: ContextConfig, fetch=_grab_foreground, clock=time.monotonic):
        self.cfg = cfg
        self._fetch = fetch
        self._clock = clock
        self.history: deque[dict] = deque(maxlen=max(4, cfg.history_len))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_raw: dict | None = None
        self.locked = False          # True when session gave us no window (e.g. locked)
        self.samples_taken = 0
        self._persist_total_bytes = 0

    # ---------------- public ----------------

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop, name="ctx-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def sample_once(self) -> tuple[dict, bool] | None:
        """One tick (also used by tests / --once CLI).
        Returns (raw, changed) or None when the session gave us nothing."""
        raw = self._fetch()
        if raw is None:
            self.locked = True
            return None
        self.locked = False
        changed = self._note(raw)
        return raw, changed

    def summary(self, max_chars: int | None = None) -> str:
        """Compact human/LLM-readable roll-up for the persona context block."""
        max_chars = max_chars or self.cfg.max_summary_chars
        with self._lock:
            items = list(self.history)
        if not items:
            return "ambient: no samples yet (session may be locked)"
        # de-dupe consecutive same-window stretches
        stretches: list[dict] = []
        for it in items:
            key = (it["app"], it["title"])
            if stretches and (stretches[-1]["app"], stretches[-1]["title"]) == key:
                stretches[-1]["until"] = it["ts"]
                stretches[-1]["count"] += 1
            else:
                stretches.append({"app": it["app"], "title": it["title"],
                                  "hint": it.get("hint", "unknown"),
                                  "since": it["ts"], "until": it["ts"], "count": 1})
        recent = stretches[-6:]
        hints: list[str] = []
        seen_hint: set[str] = set()
        for s in stretches:
            if s["hint"] not in seen_hint and s["hint"] != "unknown":
                seen_hint.add(s["hint"])
                hints.append(s["hint"])
        lines = ["ambient context (device-local, observed since "
                 + recent[0]["since"] + "):"]
        for s in recent:
            lines.append(f"- {s['app'] or '?'} :: {s['title'][:80]}  [{s['hint']}]")
        if hints:
            lines.append(f"- task signature: {'+'.join(hints[:4])}")
        if self.locked:
            lines.append("- (session appears locked; titles may be stale)")
        out = "\n".join(lines)
        return out[:max_chars] + "…" if len(out) > max_chars else out

    def snapshot(self) -> dict:
        with self._lock:
            hist = [dict(h) for h in list(self.history)[-12:]]
        return {"locked": self.locked, "samples": self.samples_taken,
                "current": hist[-1] if hist else None, "history_tail": hist}

    # ---------------- internals ----------------

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.sample_once()
            self._persist_tick()
            # on-change trigger: if the last two samples differ and we noticed the
            # swap, chase for FAST_POLL intervals until it settles (max 4 chases).
            waited = 0.0
            chase = self.cfg.on_change and getattr(self, "_just_changed", False)
            self._just_changed = False
            budget = self.cfg.poll_interval_s
            if chase:
                budget = 0.0
                for _ in range(4):
                    prev = self._last_key()
                    self._stop.wait(min(0.15, max(budget, 0.15)))
                    waited += 0.15
                    if self._last_key() != prev:
                        self._just_changed = True
                        break
            self._stop.wait(max(0.5, budget - (waited if chase else 0)))

    def _last_key(self):
        with self._lock:
            if self.history:
                h = self.history[-1]
                return (h["app"], h["title"])
        return None

    def _note(self, raw: dict) -> bool:
        raw = dict(raw)
        raw["hint"] = raw.get("hint") or activity_hint(raw["app"], raw["title"])
        key = (raw["app"], raw["title"])
        with self._lock:
            prev = (self.history[-1]["app"], self.history[-1]["title"]) if self.history else None
            self.history.append(raw)
            self.samples_taken += 1
        changed = prev is not None and prev != key
        if changed:
            self._just_changed = True
        return changed

    # ------- opt-in persistence ONLY (never on by default) -------

    def _persist_tick(self) -> None:
        if not self.cfg.opt_in_persist_jsonl:
            return
        with self._lock:
            if not self.history:
                return
            item = dict(self.history[-1])
            item["persisted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        path = Path(self.cfg.persist_path)
        if not path.is_absolute():
            path = SHELL_ROOT / path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(item, ensure_ascii=False, default=str) + "\n"
            if path.exists() and path.stat().st_size + len(line) > self.cfg.persist_max_bytes:
                self._rotate(path)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass  # persistence must NEVER crash the sampler loop

    def _rotate(self, path: Path) -> None:
        keep = max(1, self.cfg.persist_keep)
        for i in range(keep - 1, 0, -1):
            src = path.with_suffix(path.suffix + f".{i}")
            dst = path.with_suffix(path.suffix + f".{i + 1}")
            if src.exists():
                if dst.exists():
                    dst.unlink()
                src.rename(dst)
        if path.exists():
            path.rename(path.with_suffix(path.suffix + ".1"))


__all__ = ["ContextSampler", "activity_hint", "IS_WINDOWS"]
