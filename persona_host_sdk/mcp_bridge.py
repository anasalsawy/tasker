"""persona_host_sdk.mcp_bridge — minimal MCP stdio server around a PersonaSession.

Hand-rolled JSON-RPC 2.0 over stdio (initialize / tools/list / tools/call) so
ANY MCP host (Cursor, Goose, Hermes, Klein, Claude Desktop...) can mount the
persona as tools with zero heavyweight deps. Framing = newline-delimited JSON:
one JSON object per line on stdin, one per line on stdout; diagnostics to
STDERR only (stdout is sacred). If you prefer the official `mcp` pip package it
is installed here too, but this bridge deliberately has no dependency on it.

Tools:
    persona_chat(message)        -> persona turn, buffered final text (L)
    persona_delegate(task)       -> start headless lane, returns lane id NOW
    persona_status()             -> json {lanes, pending, timeline tail}
    persona_output(lane)         -> tail (running) / full text (done) of a lane
    persona_stop(lane)           -> stop_lane breaker -> status string
    persona_share_awaken(text)   -> optional shared-mind pulse (+whisper to persona)

Run:  python -m persona_host_sdk.mcp_bridge
MCP stdio config: {"command": "python", "args": ["-m", "persona_host_sdk.mcp_bridge"]}
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any, Callable, Optional

from .core import PersonaClient, PersonaSession, TextDelta, default_client

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "persona-host-sdk", "version": "0.1.0"}

_STR = {"type": "string"}
_BOOL = {"type": "boolean"}
_NOARGS = {"type": "object", "properties": {}}


def _tool(name: str, desc: str, props: dict[str, Any],
          required: Optional[list[str]] = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return {"name": name, "description": desc, "inputSchema": schema}


TOOLS = [
    _tool("persona_chat",
          "Send one message to the persona mind; returns its final voice text "
          "after any delegated lanes it launches have settled.",
          {"message": _STR}, ["message"]),
    _tool("persona_delegate",
          "Delegate a task to a fresh persona R-lane (headless session). "
          "Returns the lane id immediately; poll persona_output / persona_status.",
          {"task": _STR, "label": _STR}, ["task"]),
    _tool("persona_status",
          "JSON snapshot of all lanes + shared timeline tail (shared-mind observability).",
          {}),
    _tool("persona_output",
          "Tail (while running) or full final text (when done) of a delegated lane.",
          {"lane": _STR}, ["lane"]),
    _tool("persona_stop",
          "Stop a delegated lane (host-side circuit breaker; server lane may keep "
          "thinking — see README steering notes).",
          {"lane": _STR}, ["lane"]),
    _tool("persona_share_awaken",
          "Shared-mind pulse: record a note into the timeline; whisper=true also "
          "feeds it to the persona as a user turn on the main chat session.",
          {"text": _STR, "whisper": _BOOL}, ["text"]),
]


class PersonaBridge:
    """Owns the persona sessions behind the MCP tools. One chat session; every
    delegated lane is its own headless PersonaSession. All cancelable."""

    def __init__(self,
                 client_factory: Optional[Callable[[], PersonaClient]] = None,
                 log_path: Optional[str] = None,
                 strict_openai: bool = False):
        self.client_factory = client_factory or (lambda: default_client())
        self.log_path = log_path
        self.strict_openai = strict_openai
        self.chat: Optional[PersonaSession] = None
        self.lanes: dict[str, dict[str, Any]] = {}
        self.timeline: list[dict[str, Any]] = []
        self._counter = 0

    # ── helpers ─────────────────────────────────────────────────────────────

    def _new_session(self, session_id: Optional[str] = None) -> PersonaSession:
        return PersonaSession(client=self.client_factory(),
                              session_id=session_id,
                              log_path=self.log_path,
                              strict_openai=self.strict_openai)

    def _note(self, kind: str, **kw: Any) -> None:
        row = {"ts": round(time.time(), 4), "kind": kind}
        row.update(kw)
        self.timeline.append(row)
        if len(self.timeline) > 300:
            del self.timeline[:50]

    # ── tools ───────────────────────────────────────────────────────────────

    async def persona_chat(self, message: str) -> str:
        if self.chat is None:
            self.chat = self._new_session(session_id="mcp-chat")
        self._note("chat", message=message[:200])
        result = await self.chat.run(message)
        self._note("chat_done", text_chars=len(result.text or ""))
        return result.text

    async def persona_delegate(self, task: str, label: str = "") -> str:
        self._counter += 1
        lane_id = "ln{:08x}".format(self._counter)
        sess = self._new_session(session_id="mcp-{}-{}".format(
            time.strftime("%H%M%S"), lane_id))
        entry: dict[str, Any] = {"session": sess, "label": label or task[:80],
                                 "out": [], "done": False, "result": None,
                                 "started": time.time()}
        entry["task"] = asyncio.ensure_future(self._lane_run(lane_id, sess, task))
        self.lanes[lane_id] = entry
        self._note("delegated", lane=lane_id, task=task[:200])
        return lane_id           # returned BEFORE any execution awaits

    async def _lane_run(self, lane_id: str, sess: PersonaSession, task: str) -> None:
        def on_ev(ev: Any) -> None:
            if isinstance(ev, TextDelta):
                entry = self.lanes.get(lane_id)
                if entry is not None:
                    entry["out"].append(ev.text)
        try:
            result = await sess.run(task, on_event=on_ev)
            entry = self.lanes.get(lane_id)
            if entry is not None:
                entry["done"] = True
                entry["result"] = result
            self._note("lane_done", lane=lane_id, turns=result.turns)
        except asyncio.CancelledError:
            self._note("lane_stopped", lane=lane_id)
            raise
        except Exception as exc:  # noqa: BLE001
            entry = self.lanes.get(lane_id)
            if entry is not None:
                entry["done"] = True
            self._note("lane_error", lane=lane_id, error=str(exc)[:200])

    async def persona_status(self) -> str:
        lanes_out = {}
        for lid, e in self.lanes.items():
            st = e["session"].status()
            lanes_out[lid] = {
                "label": e["label"], "done": e["done"],
                "elapsed_s": round(time.time() - e["started"], 1),
                "persona_lanes": st["lanes"],
                "chars_streamed": sum(len(x) for x in e["out"]),
            }
        return json.dumps({
            "chat_session": self.chat.status() if self.chat else None,
            "delegated_lanes": lanes_out,
            "timeline_tail": self.timeline[-15:],
        }, ensure_ascii=False)

    async def persona_output(self, lane: str) -> str:
        e = self.lanes.get(lane)
        if e is None:
            return json.dumps({"error": "unknown lane " + lane})
        if e["done"] and e["result"] is not None:
            return e["result"].text or json.dumps(
                {"tail": e["out"][-8:]}, ensure_ascii=False)
        return "running:\n" + "".join(e["out"])[-1500:]

    async def persona_stop(self, lane: str) -> str:
        e = self.lanes.get(lane)
        if e is None:
            return json.dumps({"stopped": False, "error": "unknown lane " + lane})
        # (lane ids are minted here; stop cancels the headless session task)
        if not e["task"].done():
            e["task"].cancel()
        e["done"] = True
        self._note("stop_requested", lane=lane)
        return json.dumps({"stopped": True, "lane": lane})

    async def persona_share_awaken(self, text: str, whisper: bool = False) -> str:
        self._note("awaken", text=text[:200], whisper=whisper)
        if whisper and self.chat is not None:
            result = await self.chat.run(str(text))
            return result.text
        return json.dumps({"recorded": True})

    async def dispatch(self, name: str, args: dict[str, Any]) -> str:
        fn = getattr(self, name, None)
        if fn is None:
            raise ValueError("no such MCP tool: " + name)
        return await fn(**(args or {}))

# ──────────────────────────────────────────────────────────────────────────────
# Minimal MCP JSON-RPC 2.0 over stdio (newline-delimited). stdout = protocol
# only; anything else goes to stderr. Handlers: initialize, initialized
# (notification), tools/list, tools/call, ping.

def _log(msg: str) -> None:
    print("[mcp-bridge] " + msg, file=sys.stderr, flush=True)


def _resp(msg_id: Any, result: dict[str, Any]) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result},
                      ensure_ascii=False)


def _err(msg_id: Any, code: int, message: str) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": msg_id,
                       "error": {"code": code, "message": message}},
                      ensure_ascii=False)


async def _handle_line(bridge: PersonaBridge, line: str) -> Optional[str]:
    """One request line -> one response line (None for notifications)."""
    try:
        req = json.loads(line)
    except json.JSONDecodeError:
        return _err(None, -32700, "parse error")
    if not isinstance(req, dict):
        return _err(None, -32600, "invalid request")
    mid = req.get("id")
    method = str(req.get("method") or "")
    params = req.get("params") or {}
    is_notification = "id" not in req

    if method == "initialize":
        return _resp(mid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method in ("notifications/initialized", "initialized"):
        return None if is_notification else _resp(mid, {})
    if method == "ping":
        return _resp(mid, {})
    if method == "tools/list":
        return _resp(mid, {"tools": TOOLS})
    if method == "tools/call":
        name = str(params.get("name") or "")
        args = params.get("arguments") or {}
        if name not in {t["name"] for t in TOOLS}:
            return _err(mid, -32602, "unknown tool " + name)
        try:
            text = await bridge.dispatch(name, args if isinstance(args, dict) else {})
            return _resp(mid, {"content": [{"type": "text", "text": text}],
                               "isError": False})
        except Exception as exc:  # noqa: BLE001 — tool failure is a result, not a crash
            return _resp(mid, {"content": [{"type": "text",
                                            "text": "ERROR: " + str(exc)[:500]}],
                               "isError": True})
    if is_notification:
        return None
    return _err(mid, -32601, "method not found: " + method)


async def _amain() -> None:
    bridge = PersonaBridge()
    loop = asyncio.get_running_loop()
    q: "asyncio.Queue[Optional[str]]" = asyncio.Queue()

    # Windows Proactor pipes are flaky under asyncio.connect_*_pipe, so stdin is
    # slurped in a worker thread. Queue is NOT thread-safe, so every put goes
    # through call_soon_threadsafe — a raw put_nowait from the thread can leave
    # the loop asleep in q.get() forever (sporadic stdio deadlock).
    def _deliver(item: Optional[str]) -> None:
        loop.call_soon_threadsafe(q.put_nowait, item)

    def _read_stdin() -> None:
        # Must ALWAYS deliver the EOF sentinel — if a decode error escapes here
        # the loop blocks forever in q.get() and a plain Ctrl-C/pipe close can't
        # wake it (that's the classic silent stdio wedge).
        try:
            for raw in sys.stdin:
                _deliver(raw)
        except Exception as exc:  # noqa: BLE001
            _log("stdin reader died: " + repr(exc)[:200])
        finally:
            _deliver(None)

    _log("ready; tools: " + ", ".join(t["name"] for t in TOOLS))
    write_lock = asyncio.Lock()

    def _write(line: str) -> None:
        sys.stdout.buffer.write((line + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()

    async def _serve_line(text: str) -> None:
        out = await _handle_line(bridge, text)
        if out:
            async with write_lock:  # responses are id-keyed; may arrive out of order
                await loop.run_in_executor(None, _write, out)

    read_task = asyncio.ensure_future(loop.run_in_executor(None, _read_stdin))
    pending: set[asyncio.Task] = set()
    while True:
        line = await q.get()
        if line is None:
            break
        line = line.strip()
        if not line:
            continue
        t = asyncio.create_task(_serve_line(line))  # a slow persona_chat must
        pending.add(t)                              # never block persona_status
        t.add_done_callback(pending.discard)
    for t in list(pending):
        t.cancel()
    read_task.cancel()
    for e in bridge.lanes.values():
        if not e["task"].done():
            e["task"].cancel()
        await e["session"].aclose()
    if bridge.chat is not None:
        await bridge.chat.aclose()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
