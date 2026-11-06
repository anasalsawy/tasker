"""Intent command chain: wake/session -> persona -> response registry
(fire-and-forget; the shell thread never waits on network).

Flow:
  POST /intent {utterance|text, source, session_id?}
    -> handler returns {req_id} immediately (202-style)
    -> worker thread runs persona.stream_turn(utterance, context.summary()),
       appending deltas live into the IntentResponse buffer the UI polls via
       GET /last_response (or /response?wait=1 for the tail).
  Wake events call open_session(); intents in the window share session_id so the
  persona keeps lane order (x-sawii-session-id).

Persona tool_calls: recorded on the response for the UI/voice lanes to act. If
[core] exec_tools + task_executor_url are set, each call is POSTed to the
executor fire-and-forget; otherwise calls sit "parked" (documented degradation,
covered by tests/test_chain_offline.py).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from . import persona
from .config import ShellConfig

log = logging.getLogger("hands.chain")


@dataclass
class IntentResponse:
    """One intent in flight or finished; UI lane polls snapshots() of it."""
    req_id: str
    utterance: str
    session_id: str | None = None
    source: str = "text"               # wake-voice | typed | ui | simulated
    status: str = "running"            # running | done | error
    text: str = ""                     # accumulates deltas live
    tool_calls: list[dict] = field(default_factory=list)
    parked_tools: list[str] = field(default_factory=list)
    error: str | None = None
    route: str = ""                    # backend | persona-direct (set at end)
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def grow(self, delta: str) -> None:
        with self._lock:
            self.text += delta

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {k: getattr(self, k) for k in (
                "req_id", "utterance", "session_id", "source", "status",
                "text", "tool_calls", "parked_tools", "error", "route",
                "created_at", "finished_at")}


class Chain:
    """Registry + fire-and-forget runners for intents."""

    SESSION_WINDOW_S = 12.0            # intents this close to a wake share its session

    def __init__(self, cfg: ShellConfig,
                 context_summary: Callable[[], str],
                 on_done: Callable[[IntentResponse], None] | None = None,
                 http_client_factory: Callable[[], httpx.Client] | None = None):
        self.cfg = cfg
        self.context_summary = context_summary   # wire to ContextSampler.summary
        self.on_done = on_done                   # tray/balloon update after finish
        self._client_factory = http_client_factory
        self._lock = threading.Lock()
        self._order: list[str] = []              # oldest first
        self._by_id: dict[str, IntentResponse] = {}
        self._max_keep = 24
        self._last_wake = 0.0
        self._wake_session: str | None = None
        self.threads: list[threading.Thread] = []

    # ---------------- wake session linkage ----------------

    def note_wake(self) -> str:
        sid = "shl-" + uuid.uuid4().hex[:12]
        with self._lock:
            self._last_wake = time.monotonic()
            self._wake_session = sid
        return sid

    def session_for_intent(self, explicit: str | None) -> str | None:
        if explicit:
            return explicit
        with self._lock:
            if self._wake_session and (time.monotonic() - self._last_wake) <= self.SESSION_WINDOW_S:
                return self._wake_session
        return None

    # ---------------- submit / registry ----------------

    def submit(self, utterance: str, session_id: str | None = None,
               source: str = "text", run: bool = True) -> IntentResponse:
        resp = IntentResponse(req_id="i_" + uuid.uuid4().hex[:10],
                              utterance=utterance.strip()[:4000],
                              session_id=self.session_for_intent(session_id),
                              source=source)
        with self._lock:
            self._by_id[resp.req_id] = resp
            self._order.append(resp.req_id)
            while len(self._order) > self._max_keep:
                self._by_id.pop(self._order.pop(0), None)
        if run:
            t = threading.Thread(target=self._run, args=(resp,),
                                 name=f"chain-{resp.req_id}", daemon=True)
            self.threads.append(t)
            t.start()
        return resp

    def wait(self, req_id: str, timeout_s: float = 30.0) -> IntentResponse | None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            r = self._by_id.get(req_id)
            if r and r.status in ("done", "error"):
                return r
            time.sleep(0.05)
        return self._by_id.get(req_id)

    def latest(self) -> IntentResponse | None:
        with self._lock:
            for rid in reversed(self._order):
                r = self._by_id.get(rid)
                if r:
                    return r
        return None

    # ---------------- worker ----------------

    def _run(self, resp: IntentResponse) -> None:
        client = self._client_factory() if self._client_factory else None
        try:
            backend_side = bool(self.cfg.backend.thread_id
                                and self.cfg.backend.token
                                and persona.backend_reachable(self.cfg, client))
            resp.route = "backend" if backend_side else "persona-direct"
            ctxfn = self.context_summary() or ""
            # build the persona/stream generator the same way the shell will:
            for ev in persona.stream_turn(self.cfg, resp.utterance, ctxfn,
                                          resp.session_id, client):
                t = ev.get("type")
                if t == "delta":
                    resp.grow(ev.get("text", ""))
                elif t == "tool_call":
                    self._dispatch_tool(resp, ev.get("tool_call", {}))
                elif t == "error":
                    resp.error = ev.get("message")
                elif t == "done":
                    if ev.get("text") and not resp.text:
                        resp.text = ev["text"]
            resp.status = "error" if (resp.error and not resp.text) else "done"
        except Exception as exc:               # never kill the worker silently
            log.exception("chain worker failed")
            resp.status = "error"
            resp.error = f"{type(exc).__name__}: {exc}"
        finally:
            resp.finished_at = time.time()
            if client:
                try:
                    client.close()
                except Exception:
                    pass
            if self.on_done:
                try:
                    self.on_done(resp)
                except Exception:
                    log.warning("on_done callback failed", exc_info=True)

    def _dispatch_tool(self, resp: IntentResponse, call: dict) -> None:
        resp.tool_calls.append(call)
        url = self.cfg.task_executor_url
        if self.cfg.exec_tools and url:
            try:
                httpx.post(url, json=call, timeout=3.0)
            except Exception as exc:
                log.warning("tool exec forward failed (parking): %s", exc)
                resp.parked_tools.append(call.get("id") or call.get("name") or "?")
        else:                     # DOCUMENTED DEGRADATION: no executor wired yet
            resp.parked_tools.append(call.get("id") or call.get("name") or "?")


__all__ = ["Chain", "IntentResponse"]
