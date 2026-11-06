# tests/test_core_sse.py — typed SSE parsing against conftest frame builders.
# Pure parser tests + one end-to-end stream over the fake persona server.
from __future__ import annotations

from typing import Any

from persona_host_sdk.core import PersonaClient, lane_of

from persona_host_sdk.tests.conftest import (
    frame_delta, frame_done, frame_lane_event, frame_tool_call, ndjson,
)

P = PersonaClient._parse_chunk  # static; no I/O needed


def test_delta_frame_becomes_text_event():
    evs = P(frame_delta("hello "))
    assert evs == [{"type": "delta", "text": "hello "}]


def test_tool_call_extracts_lane_from_id():
    evs = P(frame_tool_call(0, "call_lnaaaaaaa1_probe", "sleepy", {"url": "u"}))
    assert len(evs) == 1 and evs[0]["type"] == "tool_call"
    tc = evs[0]["tool_call"]
    assert tc["id"] == "call_lnaaaaaaa1_probe"
    assert tc["lane"] == "lnaaaaaaa1"
    assert tc["name"] == "sleepy"
    assert tc["arguments"] == '{"url": "u"}'


def test_lane_of_regex_accepts_hex_no_dash():
    assert lane_of("call_ln0a1b2c3d_task") == "ln0a1b2c3d"
    assert lane_of("call_host_task") is None
    assert lane_of("ln12345678") is None      # must be full call-id form


def test_host_local_call_has_no_lane():
    evs = P(frame_tool_call(0, "call_zzz11111_task", "Task", {"prompt": "x"}))
    assert evs[0]["tool_call"]["lane"] is None


def test_finish_frame_carries_sawii_text_and_reason():
    evs = P(frame_done("voice tail", finish="tool_calls"))
    done = [e for e in evs if e["type"] == "done"]
    assert done == [{"type": "done", "text": "voice tail", "turn_id": None,
                     "metrics": None, "finish_reason": "tool_calls"}]


def test_sawii_text_only_frame_also_closes_turn():
    evs = P({"sawii_text": "tail alone", "sawii_turn": "t9",
             "sawii_metrics": {"ms": 12}})
    assert len(evs) == 1
    assert evs[0]["type"] == "done" and evs[0]["turn_id"] == "t9"
    assert evs[0]["metrics"] == {"ms": 12}


def test_lane_event_and_delegated_frames():
    assert P(frame_lane_event(kind="beat", lane="lnaaaaaaa1")) == [
        {"type": "lane_event", "event": {"kind": "beat", "lane": "lnaaaaaaa1"}}]
    assert P({"sawii_tool": {"lane": "ln1"}}) == [
        {"type": "lane_tool", "event": {"lane": "ln1"}}]
    assert P({"sawii_status": "delegated"}) == [
        {"type": "delegated", "tools": []}]


def test_error_frame_yields_nothing_silent():
    # malformed JSON lines / non-dict payloads must never raise from the parser
    assert P({}) == []
    assert P({"choices": []}) == []


async def test_stream_turn_end_to_end_over_fake_server(fake_persona):
    frames: list[dict[str, Any]] = [
        frame_delta("Yo. "),
        frame_tool_call(0, "call_lnffffffff_probe", "sleepy", {"url": "http://x/"}),
        frame_done("streamed while lane ran", finish="tool_calls"),
    ]
    fake, base = await fake_persona([frames])
    client = PersonaClient(base_url=base, api_key="test")
    got = [ev async for ev in client.stream_turn(
        messages=[{"role": "user", "content": "go"}],
        tools=[{"type": "function", "function": {"name": "sleepy"}}],
        session_id="sse-test")]
    await client.aclose()
    kinds = [g["type"] for g in got]
    assert kinds == ["delta", "tool_call", "done"]
    assert got[1]["tool_call"]["lane"] == "lnffffffff"
    # server actually saw our OpenAI-shaped body + session header
    assert fake.requests[0]["model"] == "sawii-persona"
    assert fake.requests[0]["stream"] is True
    assert fake.requests[0]["messages"][0]["content"] == "go"
    assert fake.headers[0].get("x-sawii-session-id") == "sse-test"
    assert fake.headers[0].get("authorization") == "Bearer test"


async def test_done_sentinel_stops_stream(fake_persona):
    # body without explicit finish frame: [DONE] alone must terminate cleanly
    fake, base = await fake_persona([
        [{"choices": [{"delta": {"content": "tail"}, "finish_reason": None}]}]
    ])
    client = PersonaClient(base_url=base, api_key="test")
    got = []
    async for ev in client.stream_turn(messages=[{"role": "user", "content": "hi"}]):
        got.append(ev)
    await client.aclose()
    assert [g["type"] for g in got] == ["delta"]
