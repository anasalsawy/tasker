"""persona_host_sdk.strategies — the two integration modes over the same core.

MODE A — MODEL-ROLE SWAP (ModelSwapAdapter):
    A local OpenAI-compatible /v1/chat/completions endpoint wrapping a
    PersonaSession. Point ANY host's base_url at it and the host 'thinks' the
    persona IS its model. Persona's built-in tools keep running server-side;
    DELEGATED tool_calls are re-mapped onto host-facing names the host itself
    declared in the request's tools[], so the host executes them natively and
    answers return as ordinary role=tool follow-ups on the next request.

    SCHEMA-ECHO RULE (checked with the docs worker): every tool_call emitted to
    the host uses a name + argument shape present in the host's own declared
    tools[]. Persona lane identity survives the host round-trip because minted
    call ids keep the real persona format, "call_lnXXXXXXXX_n" — hosts that obey
    the OpenAI contract echo tool_call_id verbatim (Cursor / Goose / Klein do;
    Hermes TODO-live-verify). No side channel needed.

MODE B — TOOL-MIRROR (see cursor_task_shim.ToolMirrorAdapter):
    The adapter exposes ONE host-shaped subagent tool (Cursor 'Task', Goose
    'agent', Hermes 'delegate_task'). The host's local model calls it; the
    mirror executes by delegating to fresh persona lanes and can speak back on
    the shared timeline.

STRICT-OPENAI MODE:
    strict_openai=True keeps every wire object OpenAI-spec: no sawii_* fields in
    responses, steering via message text only. For hosts with strict schemas.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from typing import Any, AsyncIterator, Callable, Optional

from .core import (
    Delegated,
    ErrorEvent,
    LaneEvent,
    PersonaClient,
    PersonaSession,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolRegistry,
    TurnComplete,
    lane_of,
)

# ONE lane worth of tool calls may be in flight per swap-request; more are held
# for the host's next request (role=tool follow-up) to keep the host happy.
_MAX_SWAP_CALLS_PER_TURN = 8


def host_tool_index(tools: Optional[list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """name -> function spec, from an OpenAI request's tools[] (echo of truth)."""
    idx: dict[str, dict[str, Any]] = {}
    for spec in tools or []:
        fn = spec.get("function") if spec.get("type") == "function" else spec
        name = (fn or {}).get("name")
        if name:
            idx[str(name)] = fn or {}
    return idx


def _remap_arguments(spec: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Fit persona args onto the host tool's declared schema (best-effort rename by
    required properties; unknown extras live UNDER 'extra' only if allowed)."""
    params = ((spec or {}).get("parameters") or {})
    props = params.get("properties") or {}
    out: dict[str, Any] = {}
    if not props:
        return args
    lower = {k.lower(): k for k in props}
    for key, val in args.items():
        if key in props:
            out[key] = val
        elif key.lower() in lower:
            out[lower[key.lower()]] = val
    return out


def sse_frame(obj: dict[str, Any]) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


class ModelSwapAdapter:
    """Mode A wrapper. Own the HTTP layer yourself (or use serve() in examples)."""

    def __init__(self, client: Optional[PersonaClient] = None, **session_kw: Any):
        self.client = client
        self.session_kw = session_kw
        self._sessions: dict[str, PersonaSession] = {}

    def session_for(self, request_id: Optional[str]) -> PersonaSession:
        """Swap mode is STATEFUL across requests: key sessions by conversation id."""
        rid = request_id or "default"
        if rid not in self._sessions:
            self._sessions[rid] = PersonaSession(client=self.client, **self.session_kw)
        return self._sessions[rid]

    async def stream_completion(
        self,
        body: dict[str, Any],
        *,
        conversation_id: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Handle one OpenAI-shaped chat.completions body; yield raw SSE lines.

        Incoming messages are replayed into the session so a host that resends
        full history each request stays coherent (the session dedupes by feeding
        only what it hasn't seen — hosts often include old turns again).
        """
        messages = body.get("messages") or []
        tools = body.get("tools")
        strict = bool(body.get("persona_strict_openai")) or bool(self.session_kw.get("strict_openai"))
        sess = self.session_for(conversation_id)
        host_idx = host_tool_index(tools)
        self._sync_history(sess, messages)

        chat_id = "chatcmpl-persona-" + uuid.uuid4().hex[:12]
        created = int(time.time())
        model_name = str(body.get("model") or "sawii-persona")
        def chunk(delta: dict[str, Any], finish: Optional[str] = None) -> str:
            return sse_frame({
                "id": chat_id, "object": "chat.completion.chunk",
                "created": created, "model": model_name,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            })

        yield chunk({"role": "assistant"})
        pending_maps: dict[str, str] = {}   # persona call_id -> host-facing tool name
        emitted_calls: list[dict[str, Any]] = []

        async for ev in sess.stream_turn():
            if isinstance(ev, TextDelta):
                yield chunk({"content": ev.text})
            elif isinstance(ev, ToolCall):
                host_name = self._pick_host_name(ev, host_idx)
                pending_maps[ev.call_id] = host_name
                if len(emitted_calls) < _MAX_SWAP_CALLS_PER_TURN:
                    args = self._host_args(ev, host_name, host_idx)
                    emitted_calls.append({"id": ev.call_id, "type": "function",
                                          "function": {"name": host_name,
                                                       "arguments": args}})
                    yield chunk({"tool_calls": [{
                        "index": len(emitted_calls) - 1, "id": ev.call_id,
                        "type": "function",
                        "function": {"name": host_name, "arguments": args},
                    }]})
            elif isinstance(ev, LaneEvent) and not strict:
                yield sse_frame({"sawii_event": ev.event})   # extra top-level KEY, not in choices
        finish = "tool_calls" if pending_maps else "stop"
        # NOTE: lanes may still be running in background right now — by design.
        # finish_reason=tool_calls hands execution to the HOST (it IS the executor
        # in swap mode); persona-side dispatch results for host-owned calls get
        # dropped at the next _sync_history (host returns them as role=tool).
        yield chunk({}, finish=finish)
        yield "data: [DONE]\n\n"

    # ── mapping helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _pick_host_name(ev: ToolCall, host_idx: dict[str, dict[str, Any]]) -> str:
        """Schema-echo rule: only emit tool names the HOST itself declared.

        1. persona-side tool name already declared -> verbatim.
        2. else prefer common subagent-ish host names (Task/delegate_task/agent).
        3. else if the host declared exactly one tool -> that one.
        4. else passthrough (a strict host answers with a structured tool error;
           the mind survives — errors are results too).
        """
        if ev.tool in host_idx:
            return ev.tool
        for pref in ("Task", "task", "delegate", "delegate_task", "agent"):
            if pref in host_idx:
                return pref
        if len(host_idx) == 1:
            return next(iter(host_idx))
        return ev.tool

    @staticmethod
    def _host_args(ev: ToolCall, host_name: str,
                   host_idx: dict[str, dict[str, Any]]) -> str:
        """Re-shape persona args to the host tool's declared schema (the echo)."""
        try:
            raw = json.loads(ev.args_json or "{}")
        except ValueError:
            raw = {"task": ev.args_json}
        if not isinstance(raw, dict):
            raw = {"task": str(raw)}
        spec = host_idx.get(host_name) or {}
        props = (spec.get("parameters") or {}).get("properties") or {}
        if props and host_name != ev.tool:
            task_text = (raw.get("prompt") or raw.get("task") or raw.get("url")
                         or json.dumps(raw, ensure_ascii=False))
            mapped: dict[str, Any] = {}
            if "description" in props:
                mapped["description"] = "persona lane " + (ev.lane_id or "-")
            if "prompt" in props:
                mapped["prompt"] = str(task_text)
            if "message" in props:
                mapped["message"] = str(task_text)
            for k, v in raw.items():
                if k in props and k not in mapped:
                    mapped[k] = v
            return json.dumps(mapped, ensure_ascii=False)
        return json.dumps(_remap_arguments(spec, raw), ensure_ascii=False)

    async def stop_lane(self, conversation_id: Optional[str], ref: str) -> bool:
        sess = self._sessions.get(conversation_id or "default")
        return await sess.stop_lane(ref) if sess else False

    async def aclose(self) -> None:
        for sess in self._sessions.values():
            await sess.aclose()

    @staticmethod
    def _sync_history(sess: PersonaSession, messages: list[dict[str, Any]]) -> None:
        """Append host-provided history the session hasn't seen yet.

        Hosts resend the whole thread every request; the session may already hold
        the same turns (swap mode keeps server-side state too). Compare from the
        tail inward: find the longest prefix of incoming messages already equal to
        session history, then append the rest verbatim.
        """
        hist = sess.history
        n = 0
        while n < len(messages) and n < len(hist):
            a, b = messages[n], hist[n]
            if a.get("role") != b.get("role"):
                break
            if a.get("content") != b.get("content") and not (
                    a.get("role") == "tool" and a.get("tool_call_id") == b.get("tool_call_id")):
                break
            if a.get("role") == "assistant" and bool(a.get("tool_calls")) != bool(b.get("tool_calls")):
                break
            n += 1
        if n < len(messages):
            tail_missing = messages[n:]
            # Content drift of an early system prompt: trust the HOST's copy.
            if tail_missing and tail_missing[0].get("role") == "system":
                sess.history = list(messages)
                sess.timeline.append({"ts": time.time(), "kind": "history_resync"})
            else:
                for m in tail_missing:
                    sess.history.append(dict(m))
                sess.timeline.append({"ts": time.time(), "kind": "history_appended",
                                      "count": len(tail_missing)})
# ──────────────────────────────────────────────────────────────────────────────
# MODE B — TOOL-MIRROR base class. Concrete host shapes live beside this file:
# cursor_task_shim.py implements the Cursor 'Task' shape over PersonaSession.

class MirrorLane:
    """One mirrored subagent: a headless persona session running one task."""

    def __init__(self, lane_id: str, description: str, session: PersonaSession,
                 task: asyncio.Task, started_at: float):
        self.lane_id = lane_id
        self.description = description
        self.session = session
        self.task = task
        self.started_at = started_at
        self.output_tail: list[str] = []
        self.result: Optional[Any] = None
        self.done = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "description": self.description[:200],
            "status": "done" if self.done else ("cancelled" if self.task.cancelled()
                                                else ("running" if not self.task.done() else "finished")),
            "started_at": self.started_at,
            "elapsed_s": round(time.time() - self.started_at, 2),
            "output_tail": self.output_tail[-8:],
            "result_chars": len(str(self.result or "")),
        }


class ToolMirrorAdapter:
    """Base for host-shaped subagent mirrors.

    Subclasses set `tool_name` + `tool_spec()` matching the HOST'S native
    subagent launcher and map its arguments to persona delegation via
    `spawn(prompt_text)`. Each mirror lane is its OWN PersonaSession (its own
    headless mind-thread on the same persona identity + session bridge), runs
    run() in the background, and pushes its L tail into `shared_timeline` so the
    parent host sees subagent chatter — the host believes it spawned natives.
    """

    tool_name = "subagent"

    def __init__(self, client_factory: Optional[Callable[[], PersonaClient]] = None,
                 registry: Optional[ToolRegistry] = None,
                 session_id: Optional[str] = None,
                 shared_timeline: Optional[list[dict[str, Any]]] = None,
                 log_path: Optional[str] = None,
                 strict_openai: bool = False,
                 **session_kw: Any):
        self.client_factory = client_factory
        self.registry = registry
        self.session_id = session_id
        self.shared_timeline: list[dict[str, Any]] = shared_timeline if shared_timeline is not None else []
        self.log_path = log_path
        self.strict_openai = strict_openai
        self.session_kw = session_kw
        self.mirror_lanes: dict[str, MirrorLane] = {}
        self._counter = 0

    @classmethod
    def tool_spec(cls) -> dict[str, Any]:
        """OpenAI function spec of the HOST-shaped tool. Override in subclasses."""
        return {
            "type": "function",
            "function": {
                "name": cls.tool_name,
                "description": "Spawn a persona-backed subagent to run a delegated task.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "What the subagent should do"},
                        "description": {"type": "string", "description": "Short label"},
                    },
                    "required": ["prompt"],
                },
            },
        }

    def spawn(self, prompt: str, description: str = "") -> MirrorLane:
        """Start one mirrored lane and return immediately (host thinks it fired a
        run_in_background subagent). Other lanes and the parent L never wait."""
        self._counter += 1
        mirror_id = "mir{:06d}".format(self._counter)
        sess = PersonaSession(
            client=self.client_factory() if self.client_factory else None,
            registry=self.registry,
            session_id="{}_{}".format(self.session_id or "mirror", mirror_id),
            log_path=self.log_path or None,
            strict_openai=self.strict_openai, **self.session_kw,
        )
        lane_desc = (description or prompt)[:80]
        task = asyncio.ensure_future(
            self._run_lane(sess, prompt, mirror_id, lane_desc))
        lane = MirrorLane(mirror_id, lane_desc, sess, task, time.time())
        self.mirror_lanes[mirror_id] = lane
        return lane

    async def _run_lane(self, sess: PersonaSession, prompt: str, mirror_id: str,
                        description: str) -> None:
        """Headless persona run. Every L delta lands on shared_timeline so the
        parent sees subagent chatter LIVE — no consumer of the parent stream
        ever awaits this coroutine."""
        def on_ev(ev: StreamEvent) -> None:
            lane = self.mirror_lanes.get(mirror_id)
            if isinstance(ev, TextDelta):
                self.shared_timeline.append(
                    {"ts": time.time(), "kind": "mirror_text", "mirror": mirror_id,
                     "text": ev.text[:400], "description": description})
                if lane is not None:
                    lane.output_tail.append(ev.text[:400])
                    if len(lane.output_tail) > 64:
                        del lane.output_tail[:16]
            elif isinstance(ev, LaneEvent):
                self.shared_timeline.append(
                    {"ts": time.time(), "kind": "mirror_lane_event", "mirror": mirror_id,
                     "event": _shallowish(ev.event)})
        try:
            result = await sess.run(prompt, on_event=on_ev)
            lane = self.mirror_lanes.get(mirror_id)
            if lane is not None:
                lane.result = result
                lane.done = True
            self.shared_timeline.append({"ts": time.time(), "kind": "mirror_done",
                                         "mirror": mirror_id, "turns": result.turns,
                                         "chars": len(result.text or "")})
        except asyncio.CancelledError:
            lane = self.mirror_lanes.get(mirror_id)
            if lane is not None:
                lane.done = True
            self.shared_timeline.append({"ts": time.time(), "kind": "mirror_stopped",
                                         "mirror": mirror_id})
            raise
        except Exception as exc:  # noqa: BLE001 — mirror error is a result, not a crash
            lane = self.mirror_lanes.get(mirror_id)
            if lane is not None:
                lane.done = True
            self.shared_timeline.append({"ts": time.time(), "kind": "mirror_error",
                                         "mirror": mirror_id, "error": str(exc)[:200]})

    def status(self, mirror_id: Optional[str] = None) -> dict[str, Any]:
        """Summary of mirror lanes + shared timeline tail — persona_status friendly."""
        if mirror_id is not None:
            lane = self.mirror_lanes.get(mirror_id)
            return lane.as_dict() if lane else {"lane_id": mirror_id, "status": "unknown"}
        out = {"lanes": [l.as_dict() for l in self.mirror_lanes.values()],
               "active": sum(1 for l in self.mirror_lanes.values() if not l.done),
               "timeline_tail": self.shared_timeline[-20:]}
        return out

    async def collect(self, mirror_id: str, timeout_s: float = 300.0) -> dict[str, Any]:
        """Await ONE lane's completion (a spin-off of the result tool). Other
        lanes keep running; this only blocks the caller's tool call, not any L."""
        lane = self.mirror_lanes.get(mirror_id)
        if lane is None:
            return {"lane_id": mirror_id, "status": "unknown"}
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(lane.task), timeout=timeout_s)
        res = lane.result
        return {
            "lane_id": lane.lane_id, "description": lane.description,
            "status": "done" if lane.done else "running",
            "text": getattr(res, "text", None) or "",
            "turns": getattr(res, "turns", 0),
            "lane_results": getattr(res, "lane_results", []),
        }

    async def stop(self, mirror_id: str) -> bool:
        """Stop a mirror lane: cancels its persona session (host-side breaker)."""
        lane = self.mirror_lanes.get(mirror_id)
        if lane is None:
            return False
        if not lane.task.done():
            lane.task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await lane.task
        lane.done = True
        self.shared_timeline.append({"ts": time.time(), "kind": "mirror_stopped",
                                     "mirror": lane.lane_id})
        return True

    async def aclose(self) -> None:
        for lane in self.mirror_lanes.values():
            if not lane.task.done():
                lane.task.cancel()
            await lane.session.aclose()


def _shallowish(d: Any) -> Any:
    if isinstance(d, dict):
        out: dict[str, Any] = {}
        for k, v in list(d.items())[:8]:
            if isinstance(v, (str, int, float, bool)) or v is None:
                out[k] = v[:120] if isinstance(v, str) else v
        return out
    return str(d)[:120]
