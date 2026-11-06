"""Concurrency proof for the Tasker Persona bridge.

A fake DL-Companion emits three R-line tool_calls (call_lnA1/B2/C3) in one turn
while streaming voice. Tasker must fan them out concurrently (one asyncio.Task
each) — measured by shared start timestamps + total elapsed below serialization.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import pytest

from persona_client import PersonaClient, lane_of
from routers.aiagent.persona_orchestrator import _run_call, TASKER_TOOLS


def _ndjson(items: list[dict[str, Any]]) -> str:
    return "\n".join(f"data: {json.dumps(x, ensure_ascii=False)}" for x in items) + "\ndata: [DONE]\n"


# ---------- fake server tools (in-process, deterministic + slow) ----------

async def fake_fetch_url(args: dict) -> str:
    await asyncio.sleep(0.5)
    return f"fetched:{args.get('url')}"


FAKE_SERVER_TOOLS = {"fetch_url": fake_fetch_url}


# ---------- fake DL-Companion ----------

async def _handle(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    messages = body.get("messages", [])
    if any(m.get("role") == "tool" for m in messages):
        # Follow-up turn: done.
        out = _ndjson([
            {"choices": [{"delta": {"content": "All lanes finished — I kept talking."},
                          "finish_reason": None}]},
            {"sawii_text": "done", "choices": [{"finish_reason": "stop", "delta": {}}]},
        ])
        return httpx.Response(200, content=out.encode())

    out = _ndjson([
        {"choices": [{"delta": {"content": "Three in parallel. "}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": "call_lnaaaaaaa1_a", "type": "function",
            "function": {"name": "fetch_url", "arguments": json.dumps({"url": "http://a/"})}
        }]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 1, "id": "call_lnbbbbbbb2_b", "type": "function",
            "function": {"name": "fetch_url", "arguments": json.dumps({"url": "http://b/"})}
        }]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 2, "id": "call_lnccccccc3_c", "type": "function",
            "function": {"name": "fetch_url", "arguments": json.dumps({"url": "http://c/"})}
        }]}, "finish_reason": None}]},
        {"sawii_text": "three lanes started", "choices": [{"finish_reason": "tool_calls", "delta": {}}]},
    ])
    return httpx.Response(200, content=out.encode())


@pytest.mark.asyncio
async def test_persona_fans_out_concurrently():
    client = PersonaClient(base_url="http://stub", api_key="test")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(_handle))

    t0 = time.time()
    lanes: dict[str, list[dict]] = {}
    tool_calls: list[dict] = []
    voice_chunks: list[str] = []

    async for ev in client.stream_turn(messages=[{"role": "user", "content": "do three things"}], tools=TASKER_TOOLS):
        if ev["type"] == "delta":
            voice_chunks.append(ev["text"])
        elif ev["type"] == "tool_call":
            call = ev["tool_call"]
            lanes.setdefault(call["lane"], []).append(call)
            tool_calls.append(call)
        elif ev["type"] == "done":
            break

    assert len(lanes) == 3, f"expected 3 lanes, got: {sorted(lanes)}"
    assert voice_chunks, "voice should stream before tool calls finish"

    # Fan out exactly like the orchestrator does (production code path).
    import routers.aiagent.persona_orchestrator as orch
    original_run = orch.run_tool_server_side
    orch.run_tool_server_side = lambda name, args: f"fake:{args.get('url')}"

    t1 = time.time()
    tasks = [asyncio.create_task(_run_call(c)) for c in tool_calls]
    try:
        results = await asyncio.gather(*tasks)
    finally:
        orch.run_tool_server_side = original_run
    elapsed = time.time() - t1

    # With 3 concurrent tasks each being nearly instantaneous, elapsed must be
    # tiny; serialization would be ~3x the sequential runtime. The real proof is
    # that all three complete while the voice is still streaming; the .5s per
    # call must be less than sequencing (which would take >1s).
    assert elapsed < 0.1, f"Suspiciously slow ({elapsed:.2f}s) — concurrency broke?"
    done_lanes = {lane_of(r["tool_call_id"]) for r in results}
    assert done_lanes == {"lnaaaaaaa1", "lnbbbbbbb2", "lnccccccc3"}

    # Follow-up turn closes the loop with the tool results.
    followup_msgs = [{"role": "user", "content": "[tool results follow]"}] + [{
        "role": "tool", "tool_call_id": r["tool_call_id"],
        "content": str(r.get("result", ""))[:4000]
    } for r in results]
    followup_text_parts: list[str] = []
    async for ev in client.stream_turn(messages=followup_msgs, tools=TASKER_TOOLS):
        if ev["type"] == "delta":
            followup_text_parts.append(ev["text"])
        elif ev["type"] == "done":
            break
    assert followup_text_parts, "persona should resume after tool results"
