# tests/test_task_mirror.py — CursorTaskShim end-to-end against a scripted
# fake persona: host-shaped Task calls run as headless persona lanes that
# themselves delegate 2 call_ln_* tool calls. Mirrored Task shape asserted.
from __future__ import annotations

import asyncio
import json
from typing import Any

from persona_host_sdk.core import PersonaClient, ToolRegistry
from persona_host_sdk.cursor_task_shim import (
    CursorTaskShim, GooseAgentShim, HermesTaskShim,
)
from persona_host_sdk.tests.conftest import frame_delta, frame_done, frame_tool_call


def lane_script(final_text: str = "Agent finished the audit.") -> list[list[dict[str, Any]]]:
    """Persona turn 1 delegates 2 sleepy calls. Turn 2: the lane final answer."""
    return [
        [
            frame_delta("On it. "),
            frame_tool_call(0, "call_lnaaaaaaaa_sleepy", "sleepy", {"url": "http://a/"}),
            frame_tool_call(1, "call_lnbbbbbbbb_sleepy", "sleepy", {"url": "http://b/"}),
            frame_done("lanes launched", finish="tool_calls"),
        ],
        [frame_delta(final_text), frame_done(final_text)],
    ]


def make_shim(base: str, registry) -> CursorTaskShim:
    return CursorTaskShim(client_factory=lambda: PersonaClient(base_url=base, api_key="t"),
                          registry=registry, session_id="host-e2e")


def sleepy_registry_slow() -> ToolRegistry:
    reg = ToolRegistry()

    async def sleepy(args: dict) -> str:
        await asyncio.sleep(5.0)
        return "slept:" + str(args.get("url", ""))

    reg.register("sleepy", sleepy, description="slow probe",
                 parameters={"type": "object", "properties": {"url": {"type": "string"}}})
    return reg


# ── static schema mirrors ────────────────────────────────────────────────────

def test_tool_spec_is_cursor_task_shape():
    spec = CursorTaskShim.tool_spec()
    fn = spec["function"]
    assert spec["type"] == "function" and fn["name"] == "Task"
    props = fn["parameters"]["properties"]
    assert set(props) == {"description", "prompt", "subagent_type", "run_in_background"}
    assert fn["parameters"]["required"] == ["description", "prompt", "subagent_type"]


def test_goose_and_hermes_specs():
    g = GooseAgentShim.tool_spec()["function"]
    assert g["name"] == "agent" and g["parameters"]["required"] == ["prompt"]
    h = HermesTaskShim.tool_spec()["function"]
    assert h["name"] == "delegate_task"
    assert "subagent_type" not in h["parameters"]["properties"]
    assert h["parameters"]["required"] == ["description", "prompt"]


# ── foreground Task: blocks just for that call, returns lane voice text ──────

async def test_foreground_task_call(fake_persona, sleepy_registry):
    fake, base = await fake_persona(lane_script())
    shim = make_shim(base, sleepy_registry)
    out = await shim.handle_call({"description": "audit", "prompt": "check two urls",
                                  "subagent_type": "generalPurpose"})
    assert "Agent finished the audit." in out
    assert len(fake.requests) == 2
    tools = [m for m in fake.requests[1]["messages"] if m.get("role") == "tool"]
    assert len(tools) == 2
    assert all("slept:http://" in m["content"] for m in tools)
    st = shim.status()
    assert st["active"] == 0 and len(st["lanes"]) == 1
    assert st["lanes"][0]["status"] == "done"
    await shim.aclose()

# ── background Task: returns task id WITHOUT awaiting the lane ───────────────

async def test_background_task_returns_immediately(fake_persona, sleepy_registry):
    fake, base = await fake_persona(lane_script())
    shim = make_shim(base, sleepy_registry)
    loop = asyncio.get_event_loop()
    t0 = loop.time()
    raw = await shim.handle_call({"description": "bg", "prompt": "go",
                                  "subagent_type": "explore", "run_in_background": True})
    spent = loop.time() - t0
    msg = json.loads(raw)
    assert msg["isQueued"] is True and msg["taskId"].startswith("mir")
    assert spent < 0.3, "run_in_background blocked on the lane"
    partial = ""
    for _ in range(40):
        partial = await shim.output_of("lnaaaaaaaa")
        if "unknown_task" not in partial:
            break
        await asyncio.sleep(0.05)
    assert "unknown_task" not in partial, "lane id never resolved"
    final = await shim.output_of(msg["taskId"], block_s=10)
    assert "Agent finished the audit." in final
    kinds = [r["kind"] for r in shim.shared_timeline]
    assert "mirror_text" in kinds and "mirror_done" in kinds
    await shim.aclose()

# ── stop verb breaks the lane locally and marks it stopped ───────────────────

async def test_stop_lane(fake_persona):
    reg = sleepy_registry_slow()
    fake, base = await fake_persona(lane_script())
    shim = make_shim(base, reg)
    raw = await shim.handle_call({"description": "kill", "prompt": "go",
                                  "subagent_type": "x", "run_in_background": True})
    tid = json.loads(raw)["taskId"]
    await asyncio.sleep(0.1)
    assert await shim.stop(tid) is True
    assert await shim.stop("mir999999") is False
    out = await shim.output_of(tid)
    assert out != ""
    assert any(r["kind"] == "mirror_stopped" or "stopped" in json.dumps(r, default=str)
               for r in shim.shared_timeline)
    await shim.aclose()
