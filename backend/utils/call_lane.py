"""CallLane — one live phone call as an execution-R lane.

Shape mirrors persona_orchestrator (task type -> lane -> SSE events -> thin
client):

  * The persona R-line calls host tool `start_call`; `_run_call` (orchestrator)
    creates a CallLane here. The lane is an asyncio-side entity: it owns its
    provider, broadcasts lane events to any number of subscribers, and keeps a
    replay window so a surface attaching mid-call sees what happened.
  * Events stream on GET /aiagent/persona/{tid}/calls/{call_id}/stream as SSE
    frames whose names ARE the lane event kinds:

      call_status     {state: dialing|ringing|connected|held|unheld|ended|failed, reason?}
      call_tone       {tone: static|dial|ringback|busy|disconnect, dur_s}
      call_transcript {speaker: them|hands|me, text}
      call_audio      {speaker: them|hands, format, duration_s, audio_b64}

    every frame also carries {call_id, lane, seq, ts}.

  * `steer(instruction)` is the ONLY inbound user-voice path. It enters the
    MODEL side (provider + x-sawii-steer on the next turn) — the far party
    never hears the user's mic. Hard boundary lives here.

Registry is per-thread so cancel/inspection can find a thread's live calls.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import time
from typing import Any, AsyncIterator, Optional

from utils.call_provider import (CallHandle, CallProvider, build_provider)

log = logging.getLogger(__name__)

MAX_HISTORY = 400          # replay window per lane (frames)
MAX_LANES_KEPT = 12        # finished lanes pruned from registry
_seq = itertools.count(1)


class CallLane:
    """One call in flight. Provider events -> stamped -> broadcast."""

    def __init__(self, call_id: str, lane: str, tid: str, provider: CallProvider,
                 handle: CallHandle):
        self.call_id = call_id
        self.lane = lane
        self.tid = tid
        self.provider = provider
        self.handle = handle
        self.seq = 0
        self.created_at = time.time()
        self.state = "starting"
        self.history: list[dict[str, Any]] = []
        self._subs: set[asyncio.Queue] = set()
        self._task: Optional[asyncio.Task] = None
        self._closed_evt = asyncio.Event()

    # ── broadcasting ─────────────────────────────────────────────────────────

    def emit(self, ev: dict[str, Any]) -> None:
        """Sync emitter handed to the provider. Stamps + broadcasts + records."""
        kind = ev.get("kind") or "call_status"
        self.seq += 1
        frame = dict(ev)
        frame.update({"call_id": self.call_id, "lane": self.lane,
                      "seq": self.seq, "ts": round(time.time(), 3)})
        if kind == "call_status":
            self.state = str(frame.get("state") or self.state)
            if self.state in ("ended", "failed"):
                self._closed_evt.set()
        self.history.append(frame)
        if len(self.history) > MAX_HISTORY:
            del self.history[:len(self.history) - MAX_HISTORY]
        for q in list(self._subs):
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                pass  # slow subscriber drops; history replay covers it

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        """Replay history, then live frames, until terminal (or cancelled)."""
        for frame in list(self.history):
            yield frame
        if self.state in ("ended", "failed"):
            return
        q = self.subscribe()
        try:
            while True:
                try:
                    frame = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield frame
                    if frame.get("kind") == "call_status" and \
                       str(frame.get("state")) in ("ended", "failed"):
                        return
                except asyncio.TimeoutError:
                    yield {"kind": "_keepalive"}
        finally:
            self.unsubscribe(q)

    # ── lifecycle / controls ─────────────────────────────────────────────────

    async def start(self) -> None:
        self.provider.attach(self.emit)
        await self.provider.start(self.handle)

    async def control(self, action: str, text: str = "") -> dict[str, Any]:
        a = (action or "").strip().lower()
        if a in ("speak", "say"):
            if not text.strip():
                return {"ok": False, "error": "speak needs text"}
            await self.provider.speak(text.strip())
            self.emit({"kind": "call_transcript", "speaker": "hands", "text": text.strip()})
            return {"ok": True, "action": a}
        if a in ("hold", "unhold"):
            (self.provider.hold if a == "hold" else self.provider.unhold)()
            self.emit({"kind": "call_status",
                       "state": "held" if a == "hold" else "unheld"})
            return {"ok": True, "action": a}
        if a == "steer":
            # user voice -> model side ONLY. Echo for the UI transcript rail.
            self.emit({"kind": "call_transcript", "speaker": "me", "text": text})
            self.provider.steer(text)
            # Queue for the persona model: the next /act turn on this thread
            # reads consume_model_steers() and hears it (never via call audio).
            _PENDING_MODEL.setdefault(self.tid, []).append(text)
            return {"ok": True, "action": a, "heard_by": "model_only"}
        if a in ("hangup", "end"):
            await self.end("hangup")
            return {"ok": True, "action": "ended"}
        return {"ok": False, "error": f"unknown control action: {action}"}

    async def end(self, reason: str = "hangup") -> None:
        await self.provider.end(reason)
        # provider emits its own ended frame; make sure it exists even if lazy:
        if self.state not in ("ended", "failed"):
            self.emit({"kind": "call_status", "state": "ended", "reason": reason})

    async def wait_closed(self, timeout_s: float = 60.0) -> bool:
        try:
            await asyncio.wait_for(self._closed_evt.wait(), timeout_s)
            return True
        except asyncio.TimeoutError:
            return False


# ── registry ──────────────────────────────────────────────────────────────────

_LANES: dict[str, CallLane] = {}
#: tid -> [steer text] queued for the MODEL side, drained once on the next turn.
_PENDING_MODEL: dict[str, list[str]] = {}


def consume_model_steers(tid: str) -> list[str]:
    """Pop and return the thread's pending user-steer lines (model hears them)."""
    return _PENDING_MODEL.pop(tid, [])


def _prune_locked() -> None:
    closed = [cid for cid, ln in _LANES.items() if ln.state in ("ended", "failed")]
    if len(closed) > MAX_LANES_KEPT:
        for cid in closed[:-MAX_LANES_KEPT]:
            _LANES.pop(cid, None)


async def open_call_lane(tid: str, lane_id: Optional[str], arguments: dict[str, Any]) -> dict[str, Any]:
    """Create + start a CallLane from `start_call` tool arguments.

    Arguments shape: {"to": "+15551234567", "purpose"?, "script"?
    [{"speaker":"them|hands","text":...}], "speed"?, "provider"?}
    No telephony creds exist in this environment, so provider defaults to the
    offline simulation (utils/call_provider.py); passing provider:"twilio"
    raises a clear NotImplementedError listing what the real legs need.
    """
    to = str(arguments.get("to") or arguments.get("number") or "").strip()
    if not to:
        raise ValueError("start_call needs a 'to' number")
    call_id = "call_" + (lane_id or "ln-main") + "_c" + format(next(_seq), "x") + str(int(time.time()) % 100000)
    provider = build_provider() if not arguments.get("provider") else _provider_by_name(str(arguments["provider"]))
    handle = CallHandle(
        call_id=call_id,
        lane=lane_id or "ln-main",
        to=to,
        frm=arguments.get("from"),
        script=arguments.get("script"),
        speed=float(arguments.get("speed") or 1.0),
    )
    ln = CallLane(call_id, handle.lane, tid, provider, handle)
    _LANES[call_id] = ln
    _prune_locked()
    ln._task = asyncio.create_task(ln.start())
    log.info("call lane opened %s lane=%s to=%s provider=%s", call_id, handle.lane, to, provider.name)
    return {
        "call_id": call_id,
        "lane": handle.lane,
        "provider": provider.name,
        "simulated": provider.name == "simulated",
        "dialing": to,
        "stream_path": f"/aiagent/persona/{tid}/calls/{call_id}/stream",
        "control_path": f"/aiagent/persona/{tid}/calls/{call_id}/control",
    }


def _provider_by_name(which: str) -> CallProvider:
    return build_provider(which)


def get_lane(call_id: str) -> Optional[CallLane]:
    return _LANES.get(call_id)


def lanes_for_thread(tid: str) -> list[CallLane]:
    return [ln for ln in _LANES.values() if ln.tid == tid]


def steer_lanes(tid: str, lane_id: Optional[str], instruction: str) -> dict[str, Any]:
    """Route a user-voice steering line into matching call lane(s) on this
    thread. Only the model/provider side hears it — never the far party."""
    targets = [ln for ln in lanes_for_thread(tid)
               if ln.state not in ("ended", "failed")
               and (not lane_id or ln.lane == lane_id)]
    for ln in targets:
        asyncio.ensure_future(ln.control("steer", instruction))
    return {"lanes": [ln.lane for ln in targets], "calls": [ln.call_id for ln in targets]}


async def inject_say(tid: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """`say_on_call` host tool: Hands speaks a line into the call (TTS leg)."""
    text = str(arguments.get("text") or "").strip()
    call_id = str(arguments.get("call_id") or "").strip()
    lane_id = str(arguments.get("lane") or "").strip() or None
    target = get_lane(call_id) if call_id else None
    if target is None:
        cand = [ln for ln in lanes_for_thread(tid)
                if ln.state not in ("ended", "failed") and (not lane_id or ln.lane == lane_id)]
        target = cand[-1] if cand else None
    if target is None or not text:
        return {"ok": False, "error": "no live call or empty text"}
    return await target.control("speak", text)


async def inject_end(tid: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """`end_call` host tool: Hands hangs up the call (orchestrated end)."""
    call_id = str(arguments.get("call_id") or "").strip()
    target = get_lane(call_id) if call_id else None
    if target is None:
        cand = [ln for ln in lanes_for_thread(tid)
                if ln.state not in ("ended", "failed")
                and (not arguments.get("lane") or ln.lane == str(arguments["lane"]))]
        target = cand[-1] if cand else None
    if target is None:
        return {"ok": False, "error": "no live call to end"}
    await target.end(str(arguments.get("reason") or "hangup"))
    return {"ok": True, "call_id": target.call_id, "ended": True}


def ended_call_notes(tid: str) -> list[str]:
    """One-line summaries of recently ended calls for the next /act turn, so the
    persona actually knows how its call finished."""
    notes = []
    for ln in lanes_for_thread(tid):
        if ln.state in ("ended", "failed"):
            notes.append("call " + ln.call_id + f" ({ln.handle.to}) -> {ln.state}"
                         + (f" reason={ln.history[-1].get('reason')}" if ln.history and
                            ln.history[-1].get("reason") else ""))
    return notes[:4]


def reset_registry() -> None:   # tests
    _LANES.clear()
    _PENDING_MODEL.clear()


__all__ = ["CallLane", "open_call_lane", "get_lane", "lanes_for_thread",
           "steer_lanes", "inject_say", "inject_end", "ended_call_notes",
           "consume_model_steers", "reset_registry"]
