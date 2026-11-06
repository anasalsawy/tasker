"""persona_host_sdk.cursor_task_shim — TOOL-MIRROR for Cursor's native 'Task' tool.

The host's own model believes it just spawned Cursor subagents. Each Task call
is executed instead by a headless persona lane: its own PersonaSession (same
persona identity + role-contiguous session bridge) that thinks on DL-Companion
and executes through the tool callbacks you hand the shim. Lanes can speak back
through the shared timeline (shared_timeline rows appear while the parent host
is still streaming its own L).

Shims included:
    CursorTaskShim  name='Task'           {description, prompt, subagent_type, run_in_background}
    GooseAgentShim  name='agent'          {name, prompt, description}
    HermesTaskShim  name='delegate_task'  {description, prompt, run_in_background}

Steering verbs (host believes it owns the subagent):
    shim.spawn(...)            -> start a lane, returns immediately (bg) or task (fg semantics)
    shim.handle_call(args)     -> execute one host-shaped Task tool call, blocking, result str
    shim.output(ref, block_s)  -> partial tail while running / full output when done
    shim.stop(ref)             -> stop_lane over the lane's persona session
    shim.steer(ref, text)      -> queue steering for the lane's next persona turn
                                  (x-sawii header + lane-referencing text rail)
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any, Callable, Optional

from .core import PersonaClient, PersonaSession, TextDelta, ToolRegistry, lane_of
from .strategies import ToolMirrorAdapter


class CursorTaskShim(ToolMirrorAdapter):
    """Task-shaped mirror. Instantiate with the host's subagent tool name/spec
    pair you want to impersonate; default = Cursor 'Task'."""

    tool_name = "Task"

    def __init__(self, client_factory: Optional[Callable[[], PersonaClient]] = None,
                 registry: Optional[ToolRegistry] = None,
                 session_id: Optional[str] = None,
                 shared_timeline: Optional[list[dict[str, Any]]] = None,
                 log_path: Optional[str] = None,
                 strict_openai: bool = False,
                 **session_kw: Any):
        super().__init__(client_factory=client_factory, registry=registry,
                         session_id=session_id, shared_timeline=shared_timeline,
                         log_path=log_path, strict_openai=strict_openai,
                         **session_kw)

    @classmethod
    def tool_spec(cls) -> dict[str, Any]:
        """Exact Cursor Task shape (verified via cursor tool schema on this machine)."""
        return {
            "type": "function",
            "function": {
                "name": cls.tool_name,
                "description": ("Launch a persona-backed subagent in an isolated "
                                "context. Same contract as the host-native Task."),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string", "description": "3-5 word task label"},
                        "prompt": {"type": "string", "description": "Instructions for the subagent"},
                        "subagent_type": {"type": "string", "description": "Agent type to emulate"},
                        "run_in_background": {"type": "boolean",
                                              "description": "Return a task id immediately"},
                    },
                    "required": ["description", "prompt", "subagent_type"],
                },
            },
        }

    async def handle_call(self, args: dict[str, Any]) -> str:
        """Execute one host-shaped Task call. Blocking for THAT tool call only —
        sibling lanes keep running free (host tool contract, not an L stream)."""
        prompt = str(args.get("prompt") or args.get("message") or "")
        desc = str(args.get("description") or prompt[:60])
        bg = bool(args.get("run_in_background"))
        lane = self.spawn(prompt, description=desc)
        if bg:
            return json.dumps({
                "isQueued": True, "taskId": lane.lane_id,
                "message": "persona lane queued: " + desc[:80],
                "lane_id": lane.lane_id,
            }, ensure_ascii=False)
        res = await self.collect(lane.lane_id)
        text = res.get("text") or ""
        if not text and res.get("lane_results"):
            text = json.dumps(res["lane_results"], ensure_ascii=False)[:4000]
        return text or json.dumps({"status": "no_output", "lane": lane.lane_id})

    async def output_of(self, lane_ref: str, block_s: float = 0.0) -> str:
        """Cursor Task-output semantics: empty/partial while running, full text
        when done. lane_ref = our mirror id OR a persona call id (call_ln...)."""
        mid = self._resolve(lane_ref)
        lane = self.mirror_lanes.get(mid) if mid else None
        if lane is None:
            return json.dumps({"status": "unknown_task", "ref": lane_ref})
        if block_s > 0 and not lane.done:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(lane.task), timeout=block_s)
        if lane.done:
            text = getattr(lane.result, "text", "") if lane.result is not None else ""
            return text if text else json.dumps(
                {"status": "done_no_text", "lane": mid,
                 "tail": lane.output_tail[-10:]}, ensure_ascii=False)
        return "running (" + lane.description + "):\n" + "\n".join(lane.output_tail[-6:])

    async def stop(self, lane_ref: str) -> bool:
        mid = self._resolve(lane_ref)
        if mid and mid in self.mirror_lanes:
            return await super().stop(mid)
        return False

    def steer(self, lane_ref: str, text: str) -> bool:
        """Modification verb: queue steering on the lane's own persona session —
        ships as x-sawii header AND lane-referencing text on its next turn."""
        mid = self._resolve(lane_ref)
        lane = self.mirror_lanes.get(mid) if mid else None
        if lane is None:
            return False
        ln = lane_of(text_ref := lane_ref) or _guess_lane(lane)
        lane.session.steer_lane(ln or "ln00000000", text)
        self.shared_timeline.append({"ts": time.time(), "kind": "mirror_steered",
                                     "mirror": mid, "text": text[:200]})
        return True

    def _resolve(self, lane_ref: str) -> Optional[str]:
        """Accept our mirror id, a persona call id, or a lane id -> mirror id."""
        if lane_ref in self.mirror_lanes:
            return lane_ref
        for mid, lane in self.mirror_lanes.items():
            for cid, ln in lane.session.lanes.items():
                if cid == lane_ref or ln.lane_id == lane_ref:
                    return mid
            if lane_ref in lane.session._pending or lane_ref in lane.session._results:
                return mid
        return None


def _guess_lane(lane: Any) -> str:
    for cid in lane.session.lanes:
        return cid
    for cid in list(lane.session._pending) + list(lane.session._results):
        return lane_of(cid) or cid
    return ""
class GooseAgentShim(CursorTaskShim):
    """Goose-style: headless one-shot agent extraction loop takes {name, prompt}."""

    tool_name = "agent"

    @classmethod
    def tool_spec(cls) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.tool_name,
                "description": "Run a persona-backed agent loop for one instruction.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Short agent label"},
                        "prompt": {"type": "string", "description": "Instruction"},
                    },
                    "required": ["prompt"],
                },
            },
        }


class HermesTaskShim(CursorTaskShim):
    """Hermes 'delegate_task': same Task shape minus subagent_type."""

    tool_name = "delegate_task"

    @classmethod
    def tool_spec(cls) -> dict[str, Any]:
        base = CursorTaskShim.tool_spec()
        fn = base["function"]
        fn["name"] = cls.tool_name
        props = fn["parameters"]["properties"]
        props.pop("subagent_type", None)
        fn["parameters"]["required"] = ["description", "prompt"]
        return base


__all__ = ["CursorTaskShim", "GooseAgentShim", "HermesTaskShim"]


