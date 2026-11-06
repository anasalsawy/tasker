"""persona_host_sdk.core — the reusable engine every adapter is built on.

Run the DL-Companion 'Persona' (unified mind) as an agent host's brain, with
delegated execution lanes. Works in any host that speaks OpenAI-compatible model
endpoints (Cursor, Goose, Klein, Hermes, ...) or MCP — see strategies.py /
mcp_bridge.py for the ways to wire this in.

Proven mechanics lifted from tasker-github backend (persona_client.py,
routers/aiagent/persona_orchestrator.py) — the turn contract is identical:

Turn contract (the only endpoint this SDK calls):
    POST {base_url}/v1/chat/completions
    Authorization: Bearer {api_key}                <- the persona key
    {"model": "sawii-persona", "stream": true, "messages": [...], "tools": [...]}

SSE frames:
    choices[0].delta.content      -> conversation lane (L) chunks, stream to user
    choices[0].delta.tool_calls   -> delegation; id ~ "call_(lnXXXXXXXX)_..."
    sawii_status: "delegated"     -> batch handed to host-side execution
    sawii_event / sawii_tool      -> R-lane rows (beat/hold/verify/steer)
    finish_reason + sawii_text    -> final voice string
    [DONE]                        -> close

STEERING (two rails, both always sent — live verification TODO):
    1. a NEW user turn whose text references the lane ids (the mind reads its own
       shared timeline, so "lane lnabcd1234: stop and do X instead" works);
    2. x-sawii-* structured headers on the next POST:
           x-sawii-steer:     "lnXXXXXXXX=instruction" (repeatable, comma-joined)
           x-sawii-stop-lane: "lnXXXXXXXX,lnYYYYYYYY"  (ask server to cancel)
    Servers that predate the headers ignore them; rail 1 keeps the mind informed.

LANE MODEL — the one invariant this SDK enforces:
    R lanes (delegated tool calls) are fire-and-forget: each tool_call spawns its
    own asyncio.Task the MOMENT it is parsed off the stream. The L stream (user-
    visible text) NEVER awaits an R completion — no gather, no queue, no cap.
    Results are re-fed as role="tool" messages keyed by tool_call_id on the NEXT
    turn (auto-loop until a turn ends with nothing pending, or max_turns).
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import inspect
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional, Union

import httpx

# ``call_(lnXXXXXXXX)_`` -> the lane that owns the call. L keeps no lane id.
_LANE_IN_ID = re.compile(r"^call_(ln[0-9a-f]{8})_", re.IGNORECASE)


def lane_of(call_id: str) -> Optional[str]:
    """Lane id embedded in a persona call id, or None for non-delegated calls."""
    m = _LANE_IN_ID.match(call_id or "")
    return m.group(1) if m else None


def _default_session_id(session_id: Optional[str]) -> str:
    """Role-contiguous bridge id reused across turns so lanes stay in one mind."""
    if session_id:
        return session_id[:128]
    return uuid.uuid4().hex


# ──────────────────────────────────────────────────────────────────────────────
# Typed stream events (what consumers see)

@dataclasses.dataclass
class TextDelta:
    """L-lane voice chunk. Safe to render straight to the user — never waits on R."""
    text: str


@dataclasses.dataclass
class ToolCall:
    """One delegation on an R lane. Dispatch happens in the background — never awaited here."""
    call_id: str
    lane_id: Optional[str]          # None = host-local tool, no R lane
    tool: str
    args_json: str
    raw: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class LaneEvent:
    """Persona R-lane telemetry row (beat/hold/verify/steer). Optional for UI."""
    kind: str                        # "lane_event" | "lane_tool"
    event: dict[str, Any]


@dataclasses.dataclass
class Delegated:
    """Persona marked this batch as delegated to the host (sawii_status: 'delegated')."""


@dataclasses.dataclass
class TurnComplete:
    """One model turn finished. ``tool_calls`` lists what was launched in the background."""
    text: str
    finish_reason: Optional[str] = None
    turn_id: Optional[str] = None
    metrics: Optional[dict[str, Any]] = None
    tool_calls: list[ToolCall] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ErrorEvent:
    message: str


StreamEvent = Union[TextDelta, ToolCall, LaneEvent, Delegated, TurnComplete, ErrorEvent]


def _shallow(d: dict[str, Any]) -> dict[str, Any]:
    """Keep log/timeline rows json-safe: only primitives, truncated."""
    out: dict[str, Any] = {}
    for k, v in list(d.items())[:12]:
        if isinstance(v, str):
            out[k] = v[:200]
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Observability: append-only jsonl of lane lifecycle => shared-mind demonstrable

class LaneLog:
    """Append-only JSONL of lane lifecycle events, written by a background task.
    log() is non-blocking by design — lifecycle hooks can never stall a stream."""

    def __init__(self, path: Optional[Union[str, Path]] = None, echo: bool = False):
        self.path = Path(path) if path else None
        self.echo = echo
        self._queue: "asyncio.Queue[Optional[str]]" = asyncio.Queue()
        self._writer: Optional[asyncio.Task] = None

    def log(self, kind: str, **fields: Any) -> None:
        row = {"ts": round(time.time(), 4), "event": kind}
        for k, v in fields.items():
            if isinstance(v, str):
                row[k] = v[:200]
            elif isinstance(v, (int, float, bool)) or v is None:
                row[k] = v
        line = json.dumps(row, ensure_ascii=False)
        if self.echo:
            print(f"[lanes] {line[:300]}", flush=True)
        if self.path is not None:
            self._ensure_writer()
            self._queue.put_nowait(line)

    def _ensure_writer(self) -> None:
        if self._writer is not None and not self._writer.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # nowhere to run; drop (observability never breaks the mind)
        self._writer = loop.create_task(self._drain())

    async def _drain(self) -> None:
        assert self.path is not None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        while True:
            line = await self._queue.get()
            if line is None:
                self._queue.task_done()
                return
            try:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                pass
            self._queue.task_done()

    async def flush(self) -> None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self._queue.join(), timeout=5.0)

    async def aclose(self) -> None:
        self._queue.put_nowait(None)
        await self.flush()


# ──────────────────────────────────────────────────────────────────────────────
# Tool registry — HOST-SUPPLIED async callbacks per tool name (results feed lanes)

ToolFn = Callable[..., Any]


class ToolRegistry:
    """name -> async (or sync) callable.

    Callback arity is inferred:
        fn(args)               -> result
        fn(args, call)         -> result
        fn(ctx, args, call)    -> result    (ctx = owning PersonaSession)
    Result may be str or any JSON-able value (dict/list are dumps'd).
    """

    def __init__(self) -> None:
        self._fns: dict[str, ToolFn] = {}
        self._specs: dict[str, dict[str, Any]] = {}

    def register(self, name: str, fn: ToolFn, *, description: str = "",
                 parameters: Optional[dict[str, Any]] = None) -> None:
        self._fns[name] = fn
        self._specs[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters or {"type": "object", "properties": {}},
            },
        }

    def tool(self, name: str, **kw: Any):
        """Decorator form: @registry.tool('fetch_url', description=...)>"""
        def deco(fn: ToolFn) -> ToolFn:
            self.register(name, fn, **kw)
            return fn
        return deco

    def merge_specs(self, extra: Optional[list[dict[str, Any]]] = None) -> Optional[list[dict[str, Any]]]:
        specs = list(self._specs.values())
        specs.extend(extra or [])
        return specs or None

    def has(self, name: str) -> bool:
        return name in self._fns

    def names(self) -> list[str]:
        return sorted(self._fns)

    def spec_for(self, name: str) -> Optional[dict[str, Any]]:
        return self._specs.get(name)

    @staticmethod
    def _arity(fn: ToolFn) -> int:
        try:
            sig = inspect.signature(fn)
            return len([p for p in sig.parameters.values()
                        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])
        except (TypeError, ValueError):
            return 1

    async def invoke(self, name: str, args: dict[str, Any], call: ToolCall,
                     ctx: Any = None) -> Any:
        fn = self._fns[name]
        n = ToolRegistry._arity(fn)
        if n >= 3:
            res = fn(ctx, args, call)
        elif n == 2:
            res = fn(args, call)
        else:
            res = fn(args)
        if inspect.isawaitable(res):
            res = await res
        return res


# ──────────────────────────────────────────────────────────────────────────────
# Persona client — SSE mechanics lifted 1:1 from backend/persona_client.py

class PersonaClient:
    """Async streaming client for DL-Companion's OpenAI-compatible /v1/chat/completions."""

    def __init__(self, base_url: str, api_key: str, timeout_s: float = 180.0,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s
        # Tests inject httpx.MockTransport / ASGITransport; None -> real network.
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None

    async def _get(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_s, connect=15.0),
                headers={"Authorization": f"Bearer {self.api_key}"},
                transport=self._transport,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def aclose(self) -> None:
        await self.close()
    async def stream_turn(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        session_id: Optional[str] = None,
        tz: Optional[str] = None,
        model: str = "sawii-persona",
        extra_headers: Optional[dict[str, str]] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream one Persona turn. Yields raw dict events:
        delta / tool_call / lane_event / lane_tool / delegated / done.
        """
        body: dict[str, Any] = {"model": model, "stream": True, "messages": messages}
        if tools:
            body["tools"] = tools
        if tz:
            body["timezone"] = tz[:64]
        headers: dict[str, str] = {}
        if session_id:
            headers["x-sawii-session-id"] = session_id[:128]
        if extra_headers:
            headers.update({k: str(v)[:256] for k, v in extra_headers.items()})

        client = await self._get()
        url = f"{self.base_url}/v1/chat/completions"
        async with client.stream("POST", url, json=body, headers=headers) as resp:
            resp.raise_for_status()
            async for raw in resp.aiter_lines():
                if not raw or not raw.startswith("data:"):
                    continue
                data = raw[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                for ev in PersonaClient._parse_chunk(chunk):
                    yield ev

    @staticmethod
    def _parse_chunk(chunk: dict[str, Any]) -> list[dict[str, Any]]:
        """One SSE frame -> 0..n events. Mechanics identical to backend/persona_client.py."""
        out: list[dict[str, Any]] = []
        if isinstance(chunk.get("sawii_event"), dict):
            out.append({"type": "lane_event", "event": chunk["sawii_event"]})
        if isinstance(chunk.get("sawii_tool"), dict):
            out.append({"type": "lane_tool", "event": chunk["sawii_tool"]})
        if chunk.get("sawii_status") == "delegated":
            out.append({"type": "delegated", "tools": []})
        sawii_done = False
        for choice in (chunk.get("choices") or []):
            delta = choice.get("delta") or {}
            if delta.get("content"):
                out.append({"type": "delta", "text": delta["content"]})
            for tc in (delta.get("tool_calls") or []):
                fn = tc.get("function") or {}
                call_id = tc.get("id") or ""
                out.append({
                    "type": "tool_call",
                    "tool_call": {
                        "id": call_id,
                        "lane": lane_of(call_id),
                        "name": fn.get("name") or "",
                        "arguments": fn.get("arguments") or "{}",
                    },
                })
            if choice.get("finish_reason"):
                out.append({
                    "type": "done",
                    "text": chunk.get("sawii_text", ""),
                    "turn_id": chunk.get("sawii_turn"),
                    "metrics": chunk.get("sawii_metrics"),
                    "finish_reason": choice.get("finish_reason"),
                })
                sawii_done = True
        # Frames carrying only sawii_text (no choices) also close a turn.
        if chunk.get("sawii_text") and not sawii_done:
            out.append({
                "type": "done",
                "text": chunk["sawii_text"],
                "turn_id": chunk.get("sawii_turn"),
                "metrics": chunk.get("sawii_metrics"),
                "finish_reason": "stop",
            })
        return out


# Hands — persona id 60 on DL-Companion. Hardcoded defaults, overridable by env.
HANDS_PERSONA_URL = "https://dl-companion-production.up.railway.app"
HANDS_PERSONA_KEY = "sp_sltCBbGrfWzwyiQBUthGNQSE0NxbQNBy-PV673fH6U4"


def default_client(**kw: Any) -> PersonaClient:
    base = os.getenv("SAWII_PERSONA_URL", HANDS_PERSONA_URL).strip() or HANDS_PERSONA_URL
    key = os.getenv("SAWII_PERSONA_KEY", HANDS_PERSONA_KEY).strip() or HANDS_PERSONA_KEY
    return PersonaClient(base, key, **kw)


# ──────────────────────────────────────────────────────────────────────────────
# Lane bookkeeping

@dataclasses.dataclass
class Lane:
    lane_id: str
    status: str = "running"          # running|done|error|stopped|hold|unknown
    label: str = ""
    calls: list[str] = dataclasses.field(default_factory=list)
    started_at: float = dataclasses.field(default_factory=time.time)
    ended_at: Optional[float] = None
    last_message: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id, "status": self.status, "label": self.label,
            "calls": self.calls, "started_at": self.started_at, "ended_at": self.ended_at,
            "last_message": self.last_message,
            "elapsed_s": round((self.ended_at or time.time()) - self.started_at, 2),
        }


@dataclasses.dataclass
class TurnResult:
    """Outcome of PersonaSession.run()."""
    text: str
    turns: int
    lane_results: list[dict[str, Any]]
    max_turns_reached: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# The session

class PersonaSession:
    """One persona, one message history, delegated R lanes, never blocking L.

    Usage:
        sess = PersonaSession(client=..., registry=reg, session_id="host-42")
        async for ev in sess.stream_turn("do three things"):
            if isinstance(ev, TextDelta): ui.print(ev.text)   # L never waits on R

        # full auto-loop (background dispatch + re-feed until quiet):
        result = await sess.run("go do the thing")
        print(result.text, result.lane_results)

    stop_lane() is the host-side circuit breaker: it cancels the local dispatch
    tasks and synthesizes a 'stopped' tool-result so the mind sees the break on
    the next turn. Server-side lanes keep thinking (TODO: live-verify x-sawii-*-
    stop-lane header support); the local break is what the user watches.
    """

    def __init__(
        self,
        client: Optional[PersonaClient] = None,
        registry: Optional[ToolRegistry] = None,
        *,
        system: Optional[str] = None,
        session_id: Optional[str] = None,
        max_turns: int = 8,
        timezone: Optional[str] = None,
        lane_log: Optional[LaneLog] = None,
        log_path: Optional[Union[str, Path]] = None,
        log_echo: bool = False,
        tools: Optional[list[dict[str, Any]]] = None,
        result_char_limit: int = 6000,
        strict_openai: bool = False,
        ctx: Any = None,
    ):
        self.client = client or default_client()
        self.registry = registry or ToolRegistry()
        self.extra_tools = tools or []
        self.max_turns = max_turns
        self.session_id = _default_session_id(str(session_id) if session_id else None)
        self.timezone = timezone
        self.result_char_limit = result_char_limit
        self.strict_openai = strict_openai     # drop non-standard sawii_* extensions
        self.log = lane_log or LaneLog(path=log_path, echo=log_echo)
        self.ctx = ctx if ctx is not None else self
        self.history: list[dict[str, Any]] = []
        if system:
            self.history.append({"role": "system", "content": system})
        self.lanes: dict[str, Lane] = {}
        self.timeline: list[dict[str, Any]] = []       # every event, for observers/shim
        self._pending: dict[str, asyncio.Task] = {}    # call_id -> background dispatch task
        self._results: dict[str, dict[str, Any]] = {}  # call_id -> unfed role=tool message
        self._steer: dict[str, str] = {}               # lane_id -> queued steer instruction
        self._stop_lanes: set[str] = set()             # lanes the server should stop next turn
        self._closed = False
        self.first_text_latency_s: Optional[float] = None   # proof L didn't wait on R

    # ── public API ──────────────────────────────────────────────────────────

    def tool_specs(self) -> Optional[list[dict[str, Any]]]:
        return self.registry.merge_specs(self.extra_tools)

    def add_user(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})
        self._record("user", text=text[:500])

    def steer_lane(self, lane_id: str, instruction: str) -> None:
        """Queue steering for lane `lane_id`. It ships TWO ways next turn:
        as message text (always works) and as x-sawii-steer header (new servers)."""
        if not lane_id.startswith("ln"):
            lane_id = "ln" + lane_id
        lane_id = lane_id.lower()[:10]
        self._steer[lane_id] = instruction
        lane = self.lanes.get(lane_id)
        if lane is not None:
            lane.status = "running"
        self.log.log("steer_queued", lane=lane_id, instruction=instruction[:200])

    async def stop_lane(self, lane_or_call_id: str) -> bool:
        """Cancel by lane id OR call id. Kills local dispatch tasks, records a
        'stopped' tool-result so the mind sees the break, queues server-side stop."""
        ref = lane_or_call_id
        target_calls: list[str] = []
        lane: Optional[Lane] = None
        if ref in self.lanes:
            lane = self.lanes[ref]
            target_calls = list(lane.calls)
            self._stop_lanes.add(ref)
        elif ref in self._pending or ref in self._results:
            target_calls = [ref]
            if lane_of(ref):
                self._stop_lanes.add(lane_of(ref) or "")
                lane = self.lanes.get(lane_of(ref) or "")
        if not target_calls:
            return False
        for cid in target_calls:
            task = self._pending.pop(cid, None)
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            if cid not in self._results:
                self._results[cid] = self._tool_message(cid, json.dumps(
                    {"status": "stopped", "reason": "host stop_lane"}, ensure_ascii=False))
        if lane is not None:
            lane.status = "stopped"
            lane.ended_at = time.time()
        self.log.log("lane_stopped", session_id=self.session_id, ref=ref, calls=target_calls)
        self._record("lane_stopped", ref=ref)
        return True

    def status(self) -> dict[str, Any]:
        """Lanes + timeline summary — what the MCP persona_status tool returns."""
        return {
            "session_id": self.session_id,
            "messages_in_history": len(self.history),
            "strict_openai": self.strict_openai,
            "lanes": [l.as_dict() for l in self.lanes.values()],
            "pending_calls": sorted(self._pending),
            "results_unfed": sorted(self._results),
            "timeline_tail": self.timeline[-20:],
        }

    async def aclose(self) -> None:
        self._closed = True
        for task in list(self._pending.values()):
            if not task.done():
                task.cancel()
        self._pending.clear()
        await self.client.aclose()
        await self.log.flush()

    async def __aenter__(self) -> "PersonaSession":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    # ── the stream: L flows, R fires in background ──────────────────────────

    async def stream_turn(self, text: Optional[str] = None) -> AsyncIterator[StreamEvent]:
        """One model turn. Lanes dispatch the MOMENT their call is parsed.

        CONTRACT (the lane model): this generator yields L deltas as they arrive;
        every ToolCall fires asyncio.create_task immediately. Nothing in here
        awaits a lane — the only sync point is the turn boundary in run(). SSE
        frames are drained through an asyncio.Queue producer so HTTP parsing and
        event consumption are decoupled and the whole turn is cancelable.
        """
        if text is not None:
            self.add_user(text)
        steer_txt = self._steer_text()
        if steer_txt:
            # Rail 1 of steering: instructions enter history as a user turn too.
            self.add_user(steer_txt)
        messages = list(self.history)
        headers = self._steering_headers()
        self._steer.clear()
        self._stop_lanes.clear()
        t_open = time.time()
        text_parts: list[str] = []
        calls_this_turn: list[ToolCall] = []
        q: "asyncio.Queue[Optional[dict[str, Any]]]" = asyncio.Queue()

        async def _producer() -> None:
            try:
                async for ev in self.client.stream_turn(
                    messages=messages, tools=self.tool_specs(),
                    session_id=self.session_id, tz=self.timezone,
                    extra_headers=headers,
                ):
                    await q.put(ev)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — surface as event, never crash consumer
                await q.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
            finally:
                await q.put(None)

        prod = asyncio.create_task(_producer())
        try:
            while True:
                ev = await q.get()
                if ev is None:
                    break
                t = ev.get("type")
                if t == "delta":
                    if self.first_text_latency_s is None:
                        self.first_text_latency_s = time.time() - t_open
                    text_parts.append(ev["text"])
                    self._record("delta", text=ev["text"][:500])
                    yield TextDelta(text=ev["text"])
                elif t == "tool_call":
                    raw = ev["tool_call"]
                    call = ToolCall(
                        call_id=raw.get("id", ""), lane_id=raw.get("lane"),
                        tool=raw.get("name", ""), args_json=raw.get("arguments") or "{}",
                        raw=raw,
                    )
                    calls_this_turn.append(call)
                    self._record("tool_call", call_id=call.call_id, lane=call.lane_id,
                                 tool=call.tool)
                    self._start_dispatch(call)      # fire-and-forget; NEVER awaited here
                    yield call                      # consumer sees the delegation instantly;
                    # ...note: continuing to yield L deltas after this is the invariant —
                    # the loop keeps draining q while the lane task runs in background.
                elif t == "lane_event":
                    self._observe_lane_event(ev["event"])
                    self._record("lane_event", **_shallow(ev["event"]))
                    yield LaneEvent(kind="lane_event", event=ev["event"])
                elif t == "lane_tool":
                    self._observe_lane_event(ev["event"], tool=True)
                    self._record("lane_tool", **_shallow(ev["event"]))
                    yield LaneEvent(kind="lane_tool", event=ev["event"])
                elif t == "delegated":
                    self._record("delegated")
                    yield Delegated()
                elif t == "error":
                    self._record("error", message=ev["message"])
                    yield ErrorEvent(message=ev["message"])
                elif t == "done":
                    # sawii_text is the server's final-voice string; only use it when
                    # no deltas streamed (some turns close tail-only). Never concatenate
                    # — that would duplicate the L tail in history.
                    if not text_parts and ev.get("text") and not self.strict_openai:
                        text_parts.append(ev["text"])
                    assistant_text = "".join(text_parts)
                    msg: dict[str, Any] = {"role": "assistant", "content": assistant_text}
                    if calls_this_turn:
                        msg["tool_calls"] = [
                            {"id": c.call_id, "type": "function",
                             "function": {"name": c.tool, "arguments": c.args_json}}
                            for c in calls_this_turn
                        ]
                    if assistant_text or calls_this_turn:
                        self.history.append(msg)
                    done = TurnComplete(
                        text=assistant_text,
                        finish_reason=ev.get("finish_reason"),
                        turn_id=ev.get("turn_id"),
                        metrics=None if self.strict_openai else ev.get("metrics"),
                        tool_calls=list(calls_this_turn),
                    )
                    self._record("turn_complete", text=done.text[:500],
                                 finish_reason=done.finish_reason,
                                 delegated=len(calls_this_turn))
                    yield done
        finally:
            prod.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await prod

    async def run(self, text: Optional[str] = None, *,
                  on_event: Optional[Callable[[StreamEvent], Any]] = None) -> TurnResult:
        """Auto-loop: turn -> lanes fan out -> sync ONLY at the turn boundary ->
        re-feed role=tool results -> next turn. Stops when a turn ends with
        nothing outstanding, or at max_turns.

        on_event sees every event LIVE (L streams to the caller while lanes are
        still running — proof the user-visible tail never waits for execution).
        """
        turns = 0
        final_text = ""
        all_fed: list[dict[str, Any]] = []
        hit_max = True
        while turns < self.max_turns:
            turns += 1
            launched: list[str] = []
            async for ev in self.stream_turn(None if turns > 1 else text):
                if on_event is not None:
                    r = on_event(ev)
                    if inspect.isawaitable(r):
                        await r
                if isinstance(ev, ToolCall):
                    launched.append(ev.call_id)
                elif isinstance(ev, TurnComplete):
                    final_text = ev.text or final_text
            if launched:
                # THE sync point — outside the stream, at the boundary. Waits only
                # for lanes this turn launched; results re-feed on the next turn.
                await self._await_calls(launched)
                all_fed.extend(self._feed_results(launched))
            elif self._results:
                all_fed.extend(self._feed_results(sorted(self._results)))
            else:
                hit_max = False
                break
        if hit_max:
            self.log.log("max_turns_reached", session_id=self.session_id, turns=turns)
        return TurnResult(text=final_text, turns=turns, lane_results=all_fed,
                          max_turns_reached=hit_max)

    # ── internals ────────────────────────────────────────────────────────────

    def _steering_headers(self) -> dict[str, str]:
        """x-sawii-* steering rails queued since last turn (see module docstring)."""
        h: dict[str, str] = {}
        if self._steer:
            h["x-sawii-steer"] = ",".join(f"{ln}={msg}" for ln, msg in self._steer.items())
        if self._stop_lanes:
            h["x-sawii-stop-lane"] = ",".join(sorted(self._stop_lanes))
        return h

    def _steer_text(self) -> str:
        """Rail 1: the same steering as plain text any persona server can read."""
        lines = ["lane " + ln + ": " + msg for ln, msg in self._steer.items()]
        lines += ["stop lane " + ln + "." for ln in sorted(self._stop_lanes)]
        return "\n".join(lines)

    def _start_dispatch(self, call: ToolCall) -> None:
        """Spawn the background dispatch task for one delegated call. NO await here."""
        if call.lane_id:
            lane = self.lanes.get(call.lane_id)
            if lane is None:
                lane = Lane(lane_id=call.lane_id, label=call.tool)
                self.lanes[call.lane_id] = lane
                self.log.log("lane_started", session_id=self.session_id,
                             lane=call.lane_id, tool=call.tool, call_id=call.call_id)
            lane.calls.append(call.call_id)
        task = asyncio.create_task(self._dispatch_call(call))
        task.add_done_callback(lambda _t, cid=call.call_id: self._pending.pop(cid, None))
        self._pending[call.call_id] = task

    async def _dispatch_call(self, call: ToolCall) -> None:
        """Run one host tool, store its role=tool message. Mirrors backend _run_call:
        exceptions become an ERROR result string; the mind is never crashed by a lane."""
        try:
            args = json.loads(call.args_json or "{}")
            if not isinstance(args, dict):
                args = {}
        except ValueError:
            args = {}
        status = "ok"
        try:
            if self.registry.has(call.tool):
                result = await self.registry.invoke(call.tool, args, call, self.ctx)
                if not isinstance(result, str):
                    result = json.dumps(result if result is not None else "", ensure_ascii=False)
            else:
                status = "error"
                result = json.dumps({"status": "error",
                                     "error": "unknown tool " + repr(call.tool),
                                     "known_tools": self.registry.names()}, ensure_ascii=False)
            self._results[call.call_id] = self._tool_message(call.call_id, result)
            lane = self.lanes.get(call.lane_id or "")
            if lane is not None and lane.status != "stopped":
                lane.status = "done" if status == "ok" else "error"
                lane.ended_at = time.time()
                lane.last_message = result[:200]
            self.log.log("call_completed", session_id=self.session_id,
                         call_id=call.call_id, lane=call.lane_id,
                         tool=call.tool, status=status)
            self._record("call_completed", call_id=call.call_id,
                         lane=call.lane_id, status=status)
        except asyncio.CancelledError:
            self.log.log("call_stopped", session_id=self.session_id,
                         call_id=call.call_id, lane=call.lane_id)
            raise
        except Exception as exc:  # noqa: BLE001 — one lane failing never sinks the mind
            self._results[call.call_id] = self._tool_message(
                call.call_id, "ERROR: " + type(exc).__name__ + ": " + str(exc))
            lane = self.lanes.get(call.lane_id or "")
            if lane is not None:
                lane.status = "error"
                lane.ended_at = time.time()
            self.log.log("call_failed", session_id=self.session_id,
                         call_id=call.call_id, lane=call.lane_id, error=str(exc)[:300])
            self._record("call_failed", call_id=call.call_id, error=str(exc)[:200])

    async def _await_calls(self, call_ids: list[str], timeout_s: float = 300.0) -> None:
        """Turn-boundary sync for a batch of dispatched calls — the orchestrator's
        post-stream asyncio.wait, lifted. Called ONLY after the L stream closed."""
        tasks = [self._pending[cid] for cid in call_ids if cid in self._pending]
        if not tasks:
            return
        await asyncio.wait(tasks, timeout=timeout_s)

    def _tool_message(self, call_id: str, content: str) -> dict[str, Any]:
        """OpenAI-shape tool result; persona maps tool_call_id -> lane on its side."""
        return {"role": "tool", "tool_call_id": call_id,
                "content": content[: self.result_char_limit]}

    def _feed_results(self, call_ids: list[str]) -> list[dict[str, Any]]:
        """Consume completed results into history as role=tool messages (next turn)."""
        fed: list[dict[str, Any]] = []
        for cid in call_ids:
            msg = self._results.pop(cid, None)
            if msg is not None:
                self.history.append(msg)
                fed.append(msg)
                self._record("result_fed", call_id=cid, lane=lane_of(cid))
        return fed

    def _observe_lane_event(self, event: dict[str, Any], tool: bool = False) -> None:
        """Fold sawii_event / sawii_tool rows into local lane state (best-effort)."""
        if not isinstance(event, dict):
            return
        lid = event.get("lane") or event.get("lane_id") or event.get("ln")
        if not lid or not str(lid).lower().startswith("ln"):
            return
        lid = str(lid).lower()[:10]
        lane = self.lanes.get(lid)
        if lane is None:
            lane = Lane(lane_id=lid)
            self.lanes[lid] = lane
        if tool:
            name = event.get("name") or event.get("tool")
            if name:
                lane.label = str(name)
        ktype = event.get("kind")
        if not isinstance(ktype, str):
            ktype = event.get("type")
        if not isinstance(ktype, str):
            ktype = event.get("event")
        kind = (ktype or "").lower()
        if kind in ("verify", "done", "finished", "complete", "completed"):
            lane.status = "done"
            lane.ended_at = time.time()
        elif kind in ("hold", "wait", "blocked"):
            lane.status = "hold"
        msg = event.get("message")
        if not isinstance(msg, str):
            msg = event.get("text")
        if not isinstance(msg, str):
            msg = event.get("summary")
        if isinstance(msg, str):
            lane.last_message = msg[:200]

    def _record(self, kind: str, **fields: Any) -> None:
        """Timeline row + jsonl log row for every session-visible moment."""
        row = {"ts": round(time.time(), 4), "kind": kind}
        for k, v in fields.items():
            if isinstance(v, str):
                row[k] = v[:200]
            elif isinstance(v, (int, float, bool)) or v is None:
                row[k] = v
        self.timeline.append(row)
        if len(self.timeline) > 500:
            del self.timeline[:100]
        self.log.log(kind, session_id=self.session_id, **fields)


__all__ = [
    "PersonaClient", "PersonaSession", "ToolRegistry", "LaneLog", "Lane", "TurnResult",
    "TextDelta", "ToolCall", "LaneEvent", "Delegated", "TurnComplete", "ErrorEvent",
    "StreamEvent", "lane_of", "default_client",
    "HANDS_PERSONA_URL", "HANDS_PERSONA_KEY",
]
