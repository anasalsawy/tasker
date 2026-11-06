"""Localhost JSON API the UI / voice lanes call. stdlib http.server, loopback only.

Surface (documented in README 'Localhost API'):
  GET  /state                 -> presence snapshot (engine, ack stats, wake list)
  POST /intent                -> {utterance|text, session_id?, source?} -> {req_id}
  GET  /last_response         -> latest IntentResponse snapshot (status/text/tools)
  GET  /response?id=..        -> specific intent snapshot
  GET  /context?max_chars=..  -> ambient summary string (RAM buffer)
  GET  /health                -> {ok, version, uptime_s}
  POST /wake                   -> arm SIMULATED wake / text-driven wake for UIs
Loan flags: everything answers fast (<50 ms typical), handler threads never block
on persona runs (chain submit spins its own daemon worker). No auth: 127.0.0.1
process-local loopback per spec; chrome/electron UIs call this same package-commit.

NOTE: bind failure -> raise so main() can back off & retry (every 15 s watchdog).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import ShellConfig
from .chain import Chain

log = logging.getLogger("hands.httpd")

_START = time.time()


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "HandsShell/0.9"
    cfg: ShellConfig                     # injected on class by ShellAPI
    chain: Chain
    state: callable = staticmethod(lambda: {})   # injected per-app wiring

    def log_message(self, fmt, *args):   # keep the noise down; errors visible
        if "404" in fmt or "500" in fmt:
            log.warning("httpd: " + fmt, *args)

    # ------------- helpers -------------

    def _json(self, code: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n == 0:
            return {}
        raw = self.rfile.read(min(n, 65536))
        try:
            return json.loads(raw.decode("utf-8", "ignore"))
        except json.JSONDecodeError:
            return {"_parse_error": "invalid json body"}

    # ------------- GET -------------

    def do_GET(self) -> None:
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path.rstrip("/") or "/"
        try:
            if path == "/health":
                self._json(200, {"ok": True, "version": self.cfg.__dict__.get("version", "0.9.0"),
                                 "uptime_s": round(time.time() - _START, 1)})
            elif path == "/state":
                st = dict(self.state()) if callable(self.state) else {}
                self._json(200, st if isinstance(st, dict) else {"state": st})
            elif path == "/context":
                mx = int((q.get("max_chars") or [0])[0]) or self.cfg.http.context_prefix_max_chars
                self._json(200, {"summary": self.chain.context_summary()[:mx],
                                 "poll_interval_s": self.cfg.context.poll_interval_s})
            elif path == "/last_response":
                r = self.chain.latest()
                self._json(200 if r else 404, r.snapshot() if r else {"error": "no intents yet"})
            elif path == "/response":
                rid = (q.get("id") or [""])[0]
                r = self.chain._by_id.get(rid)
                wait = float((q.get("wait") or [0])[0])
                if r and wait > 0:
                    r = self.chain.wait(rid, timeout_s=min(wait, 90.0))
                self._json(200 if r else 404, r.snapshot() if r else {"error": "unknown id"})
            else:
                self._json(404, {"error": "not found",
                                 "routes": ["/health", "/state", "/context",
                                            "/last_response", "/response?id="]})
        except Exception as exc:                       # never leak a stacktrace
            log.exception("GET %s failed", self.path)
            self._json(500, {"error": str(exc)[:200]})

    # ------------- POST -------------

    def do_POST(self) -> None:
        u = urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        try:
            if path == "/intent":
                body = self._read_body()
                utt = (body.get("utterance") or body.get("text") or "").strip()
                if not utt:
                    self._json(400, {"error": "need utterance|text"})
                    return
                src = (body.get("source") or "text").strip()[:20]
                resp = self.chain.submit(utt, session_id=body.get("session_id"),
                                         source=src)
                self._json(202, {"req_id": resp.req_id, "status": resp.status,
                                 "session_id": resp.session_id,
                                 "poll": f"/response?id={resp.req_id}"})
            elif path == "/wake":
                body = self._read_body() or {}
                armed = self.chain_note_wake()
                ok = self.wake_arm()
                self._json(200, {"session_id": armed, "armed": ok,
                                 "note": "sim/text-driven wake arming (see README)"
                                         if not ok else "engine armed"})
            else:
                self._json(404, {"error": "not found", "routes": ["/intent", "/wake"]})
        except Exception as exc:
            log.exception("POST %s failed", self.path)
            self._json(500, {"error": str(exc)[:200]})

    # class-level hooks main.py overrides via ShellAPI.set_wake_hook(...)
    wake_arm = staticmethod(lambda: False)

    def chain_note_wake(self) -> str:
        return self.chain.note_wake()


class ShellAPI:
    """Owns the threaded loopback server; start()/stop(); no external deps.
    Binds 127.0.0.1 ONLY (privacy). Port busy/OSError -> re-raise for main
    backoff clock (15 s watchdog relaunch)."""

    def __init__(self, cfg: ShellConfig, chain: Chain,
                 state_fn=None, wake_arm=None, logger=log):
        self.cfg, self.chain = cfg, chain
        self.logger = logger
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.state_fn = state_fn or (lambda: {})
        self._wake_arm = wake_arm or (lambda: False)

    def _build_handler_cls(self) -> type:
        outer = self

        class Bound(ApiHandler):
            cfg = outer.cfg
            chain = outer.chain

            @staticmethod
            def state():
                return outer.state_fn()

            @staticmethod
            def wake_arm():
                return outer._wake_arm()

        return Bound

    def start(self) -> int:
        """Bind+serve; returns actual port. Raises OSError on bind conflict."""
        addr = (self.cfg.http.host, self.cfg.http.port)
        if addr[0] not in ("127.0.0.1", "localhost", "::1"):
            raise RuntimeError("refusing to bind non-loopback host "
                               + str(addr))   # privacy rail
        self._server = ThreadingHTTPServer(addr, self._build_handler_cls())
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        name="shell-api", daemon=True)
        self._thread.start()
        self.logger.info("localhost API on http://%s:%d", *addr)
        return self._server.server_address[1]

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None


__all__ = ["ShellAPI", "ApiHandler"]

