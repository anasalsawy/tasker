"""Persona orchestrator for Tasker — replaces the old consecutive two-step chain.

Old way: ask one agent for a subtask, then ask a different agent for actions on
that subtask, repeatedly — strict line, one thought at a time.

New way: ONE POST to DL-Companion (the unified mind — sawii-persona). The
persona's own R1..Rn fan out inside one turn; every tool_call carries its lane
id (call_lnXXXXXXXX_...) so Tasker runs all of them concurrently (one
asyncio.Task each — no queue, no cap) and sends the results back as 'tool' role
messages on the next turn. The persona's shared timeline keeps every lane's
mind in sync.

Thread model: each persona thread's state is rebuilt from `ThreadMessage` rows on
the server's side every turn — the desktop/browser client is thin: it just keeps
POSTing /act with the latest screen state + any completed tool results, and the
persona drives everyone forward in one continuous voice.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, and_, select

from db.database import get_session
from db.models import Thread, ThreadStatus, ThreadTask, ThreadTaskStatus
from dependencies.auth_dependencies import get_current_user_dependency
from db.models import User
from utils.agentic_tools import run_tool_server_side
from utils.procedures import CustomError

from persona_client import PersonaClient, lane_of, HANDS_PERSONA_KEY

log = logging.getLogger(__name__)

router = APIRouter(prefix="/aiagent/persona", tags=["persona"],
                   dependencies=[Depends(get_current_user_dependency)])


class PersonaActRequest(BaseModel):
    text: str = ""                                        # user voice; empty on tool-result follow-up turns
    screenshot_b64: Optional[str] = None                  # desktop+tab screen
    current_os: Optional[str] = None
    current_interactive_elements: Optional[list[dict]] = None
    current_running_apps: Optional[list[dict]] = None
    tool_results: list[dict[str, Any]] = []               # [{tool_call_id, name, result}]
    session_id: Optional[str] = None                      # carried over turns to tie R-lanes
    timezone: Optional[str] = None
    steer: Optional[str] = None                           # "lnXXXXXXXX=instruction" (call steering rail)


# ──────────────────────────────────────────────────────────────────────────────
# Persona-side context builder: one user message from the task + screen state,
# then each tool result as a separate `tool` role message (Persona lanes read
# their own results from the tool_call_id -> ln they own).

def _build_messages(
    thread: Thread,
    task: Optional[ThreadTask],
    req: PersonaActRequest,
) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = []

    # One concise host-side system context: who the persona is working for,
    # what the environment IS right now. Lane/tool fan-out lives in the
    # persona's OWN R-mind (server side); the host only tells it what's on screen.
    env_lines = [
        "You are driving a real user's task on my computer through Tasker.",
        "Current task: " + (task.task_text if task else "(none yet)"),
        "Thread tone: " + (thread.title or ""),
    ]
    if req.current_os:
        env_lines.append(f"OS: {req.current_os}")
    if req.current_running_apps:
        env_lines.append("Running apps: " + json.dumps(req.current_running_apps)[:1000])
    if req.current_interactive_elements:
        env_lines.append("Visible elements: " + json.dumps(req.current_interactive_elements)[:2000])

    msgs.append({"role": "system", "content": "\n".join(env_lines)})

    # Queued mid-call steers (user voice -> text -> MODEL only). At the start of
    # this turn the persona hears everything typed while a call lane was live.
    from utils import call_lane as _cl
    _call_steers = _cl.consume_model_steers(thread.id)

    if req.text.strip():
        msgs.append({"role": "user", "content": req.text})
    elif req.tool_results:
        # Tool-result follow-up turn: the persona keeps going from its own results.
        msgs.append({"role": "user", "content": "[tool results follow]"})

    # Rail 1 of steering (persona_host_sdk contract): lane instructions enter the
    # timeline as a user turn too, so any persona server reads them — while the
    # x-sawii-steer header is rail 2 for new servers. Call steering NEVER sounds
    # like far-end audio; the provider's speaker set never includes the user.
    steer_bits: list[str] = []
    if req.steer and req.steer.strip():
        steer_bits.append("ln=" + req.steer.strip()[:512])
    if _call_steers:
        steer_bits.extend("[call steer] " + s[:512] for s in _call_steers[:6])
    if steer_bits:
        msgs.append({"role": "user", "content": "[steering] " + " ; ".join(steer_bits)[:512]})

    # OpenAI-shape tool results: one message per completed call. Persona's own
    # code reads tool_call_id -> lane -> which R-line asked.
    for tr in req.tool_results:
        cid = str(tr.get("tool_call_id") or "")
        if not cid:
            continue
        result_text = tr.get("result")
        if not isinstance(result_text, str):
            result_text = json.dumps(result_text if result_text is not None else "", ensure_ascii=False)
        msgs.append({
            "role": "tool",
            "tool_call_id": cid,
            "content": result_text[:6000],
        })
    return msgs


# ──────────────────────────────────────────────────────────────────────────────
# Host tools the persona may ask for. These mirror the tools Tasker already
# exposes server-side (fetch_url, read_pdf, summarize_youtube_video) plus a stub
# for desktop actions the client app will execute. Persona decides; Tasker runs.

_SERVER_TOOL_NAMES = ("fetch_url", "read_pdf", "summarize_youtube_video")


TASKER_TOOLS: list[dict[str, Any]] = [
    {"type": "function", "function": {"name": "fetch_url", "description": "Fetch and summarize a URL.",
                                      "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "read_pdf", "description": "Extract text from a PDF (path or URL).",
                                      "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "url": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "summarize_youtube_video", "description": "Summarize a YouTube video.",
                                      "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    # Desktop / browser actions: executed by the desktop agent via /screenshot +
    # interactive-elements feedback loop. Names start with desktop_ so the
    # client clumps them into its own action batch.
    {"type": "function", "function": {"name": "desktop_click", "description": "Click a UI element by id.",
                                      "parameters": {"type": "object", "properties": {"element_id": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}}, "required": ["element_id"]}}},
    {"type": "function", "function": {"name": "desktop_type", "description": "Type text at the focused element.",
                                      "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "desktop_scroll", "description": "Scroll the active window.",
                                      "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down", "left", "right"]}, "amount": {"type": "number"}}, "required": ["direction"]}}},
    {"type": "function", "function": {"name": "desktop_open", "description": "Open an app or file on the user's machine.",
                                      "parameters": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}}},
    # Voice phone calls: server-side call LANES. lobe L (conversation) stays
    # free while the call runs; the client just subscribes to lane events.
    {"type": "function", "function": {"name": "start_call", "description": "Start a live voice phone call as an execution lane. Returns immediately with the lane/stream ids; call events (dialing, ringing, connected, transcript, ended) arrive on the lane SSE stream, not in this tool result.",
                                      "parameters": {"type": "object", "properties": {
                                          "to": {"type": "string", "description": "E.164 number to dial, e.g. +15551234567"},
                                          "purpose": {"type": "string", "description": "Why Hands is calling — drives what it says once connected."},
                                          "from": {"type": "string", "description": "Optional caller-id number."},
                                          "script": {"type": "array", "description": "Optional simulated-call script override: [{speaker:'them'|'hands', text}].",
                                                     "items": {"type": "object", "properties": {"speaker": {"type": "string"}, "text": {"type": "string"}}, "required": ["speaker", "text"]}},
                                          "speed": {"type": "number", "description": "Simulated time scale (0.1 fast..1 real). Ignored by real providers."}},
                                          "required": ["to"]}}},
    {"type": "function", "function": {"name": "say_on_call", "description": "Speak a line into the active call lane (Hands' voice to the far party).",
                                      "parameters": {"type": "object", "properties": {"text": {"type": "string"},
                                                                                      "call_id": {"type": "string"}, "lane": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "end_call", "description": "Hang up the active call lane.",
                                      "parameters": {"type": "object", "properties": {"call_id": {"type": "string"}, "lane": {"type": "string"}, "reason": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "get_calls", "description": "List this thread's call lanes (id, lane, state, number).",
                                      "parameters": {"type": "object", "properties": {}, "required": []}}},
]

# Host tools that run as server-side call-lane actions (not client actions).
_LANE_TOOLS = {"start_call", "say_on_call", "end_call", "get_calls"}


async def _run_server_tool(name: str, arguments: dict[str, Any]) -> str:
    """One server-side fetch; runs concurrently with desktop/browser taps."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, run_tool_server_side, name, arguments)


async def _run_lane_tool(name: str, arguments: dict[str, Any], tid: str,
                         lane_id: Optional[str] = None) -> str:
    """Call-lane tools: open/speak/end/poll lanes; the events themselves leave
    over the lane SSE stream so this turn never blocks on a phone call."""
    from utils import call_lane as cl
    if name == "start_call":
        info = await cl.open_call_lane(tid, lane_id, arguments)
        return json.dumps({"ok": True, **info}, ensure_ascii=False)
    if name == "say_on_call":
        return json.dumps(await cl.inject_say(tid, arguments), ensure_ascii=False)
    if name == "end_call":
        return json.dumps(await cl.inject_end(tid, arguments), ensure_ascii=False)
    if name == "get_calls":
        live = [{"call_id": ln.call_id, "lane": ln.lane, "state": ln.state,
                 "to": ln.handle.to, "seq": ln.seq}
                for ln in cl.lanes_for_thread(tid)]
        return json.dumps({"ok": True, "calls": live}, ensure_ascii=False)
    raise ValueError(f"Unsupported lane tool: {name}")


async def _run_call(call: dict[str, Any], tid: Optional[str] = None) -> dict[str, Any]:
    """Run one R-line's call. Lane identity stays attached to the result so the
    client can queue multiple lanes side by side."""
    name = call.get("name", "")
    args_str = call.get("arguments") or "{}"
    try:
        args = json.loads(args_str)
    except ValueError:
        args = {}
    try:
        if name in _SERVER_TOOL_NAMES:
            result = await _run_server_tool(name, args if isinstance(args, dict) else {})
            viewport = "server"
        elif name in _LANE_TOOLS:
            # Server-side call lane — runs independent of this turn (lobe L free).
            result = await _run_lane_tool(name, args if isinstance(args, dict) else {},
                                          tid or "", lane_of(call.get("id") or ""))
            viewport = "server"
        else:
            # Desktop / browser actions: return the whole call so the client
            # (Electron app) executes it and posts the next screenshot. No
            # result yet — the client will send it as the next /act tool_results.
            result = json.dumps({"ack": "needs_client_execution", "action": {
                "name": name, "arguments": args}}, ensure_ascii=False)
            viewport = "client"
        return {
            "tool_call_id": call.get("id"),
            "lane": lane_of(call.get("id") or ""),
            "name": name,
            "arguments": args,
            "result": result,
            "status": "ok",
            "executed_in": viewport,
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("persona tool call %s failed", call.get("id"))
        return {
            "tool_call_id": call.get("id"),
            "lane": lane_of(call.get("id") or ""),
            "name": name,
            "arguments": args,
            "result": f"ERROR: {exc}",
            "status": "error",
            "executed_in": "server",
        }


# ──────────────────────────────────────────────────────────────────────────────
# SSE encoder: one frame per event the client UI cares about.

def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/{tid}/act")
async def act(tid: str, req: PersonaActRequest, request: Request,
              db: Session = Depends(get_session),
              user: User = Depends(get_current_user_dependency)):
    instance = db.exec(select(Thread).where(and_(
        Thread.id == tid,
        Thread.user_id == user.id,
    ))).first()
    if not instance or instance.user_id != user.id:
        raise CustomError(status.HTTP_404_NOT_FOUND, "Thread not found")

    task = db.exec(select(ThreadTask).where(and_(
        ThreadTask.thread_id == tid,
        ThreadTask.status == ThreadTaskStatus.WORKING,
    ))).first()

    client = PersonaClient(
        base_url=os.getenv("SAWII_PERSONA_URL", "https://dl-companion-production.up.railway.app"),
        api_key=os.getenv("SAWII_PERSONA_KEY", "") or HANDS_PERSONA_KEY,
    )

    messages = _build_messages(instance, task, req)

    async def event_gen():
        full_text_parts: list[str] = []
        outstanding: list[asyncio.Task] = []
        call_tasks: dict[str, asyncio.Task] = {}
        calls_meta: dict[str, dict] = {}

        try:
            async for ev in client.stream_turn(messages=messages, tools=TASKER_TOOLS,
                                              session_id=req.session_id,
                                              tz=req.timezone,
                                              steer=req.steer):
                if ev["type"] == "delta":
                    full_text_parts.append(ev["text"])
                    yield _sse("delta", {"text": ev["text"]})
                elif ev["type"] == "lane_event":
                    yield _sse("lane", ev["event"])
                elif ev["type"] == "lane_tool":
                    yield _sse("lane_tool", ev["event"])
                elif ev["type"] == "tool_call":
                    call = ev["tool_call"]
                    call_id = call.get("id") or ""
                    calls_meta[call_id] = call
                    yield _sse("tool_call", call)
                    # Fire-and-forget: every lane's call starts its own asyncio
                    # task — concurrently, no queue.
                    t = asyncio.create_task(_run_call(call, tid))
                    call_tasks[call_id] = t
                    outstanding.append(t)
                elif ev["type"] == "delegated":
                    yield _sse("delegated", ev)
                elif ev["type"] == "done":
                    # Final personio reply — then we flush any still-running
                    # server-side results so the client can group them into the
                    # next /act turn's tool_results.
                    pass

            # After the stream closed: wait for every outstanding call (fast for
            # server tools; the client will hold desktop/browser ones until it
            # posts the next /act).
            pending_tools: list[dict[str, Any]] = []
            if outstanding:
                done, _ = await asyncio.wait(outstanding, timeout=30)
                for t in done:
                    r = t.result()
                    pending_tools.append(r)
                    yield _sse("tool_result", r)

            yield _sse("done", {
                "text": "".join(full_text_parts),
                "tools_pending_client": [r for r in pending_tools if r.get("executed_in") == "client"],
                "turn_id": None,
            })
        except Exception as exc:  # noqa: BLE001
            log.exception("persona act failed")
            yield _sse("error", {"message": str(exc)})
        finally:
            await client.aclose()

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ──────────────────────────────────────────────────────────────────────────────
# Call lane surfaces. The `start_call` tool result hands the client these paths.
# Frames on the stream are exactly the lane event kinds (see utils/call_lane.py):
#   event: call_status|call_tone|call_transcript|call_audio
#   data:  {kind, call_id, lane, seq, ts, ...payload}

class CallControlRequest(BaseModel):
    action: str                                  # speak | hold | unhold | steer | hangup
    text: str = ""


@router.get("/{tid}/calls")
async def list_calls(tid: str, db: Session = Depends(get_session),
                     user: User = Depends(get_current_user_dependency)):
    from utils import call_lane as cl
    return {"calls": [{"call_id": ln.call_id, "lane": ln.lane, "state": ln.state,
                       "to": ln.handle.to, "seq": ln.seq, "provider": ln.provider.name,
                       "started_at": ln.created_at}
                      for ln in cl.lanes_for_thread(tid)]}


@router.get("/{tid}/calls/{cid}/stream")
async def call_stream(tid: str, cid: str, request: Request,
                      user: User = Depends(get_current_user_dependency)):
    from utils import call_lane as cl
    lane = cl.get_lane(cid)
    if not lane or lane.tid != tid:
        raise CustomError(status.HTTP_404_NOT_FOUND, "Call lane not found")

    async def gen():
        try:
            async for frame in lane.stream():
                if request is not None and await request.is_disconnected():
                    return
                if frame.get("kind") == "_keepalive":
                    yield ": keepalive\n\n"
                    continue
                yield _sse(frame.get("kind", "call_status"), frame)
        except asyncio.CancelledError:
            return

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{tid}/calls/{cid}/control")
async def call_control(tid: str, cid: str, req: CallControlRequest,
                       user: User = Depends(get_current_user_dependency)):
    """The ONLY user-side inputs to a live call: speak (→TTS to far end),
    hold/unhold, steer (model-only; far party never hears the user), hangup."""
    from utils import call_lane as cl
    lane = cl.get_lane(cid)
    if not lane or lane.tid != tid:
        raise CustomError(status.HTTP_404_NOT_FOUND, "Call lane not found")
    out = await lane.control(req.action, req.text)
    if not out.get("ok"):
        raise CustomError(status.HTTP_400_BAD_REQUEST, out.get("error", "control failed"))
    return out
