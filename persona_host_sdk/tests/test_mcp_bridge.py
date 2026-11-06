# tests/test_mcp_bridge.py — MCP stdio JSON-RPC over the bridge. In-process
# _handle_line dispatch + one REAL subprocess-over-pipes test. Loopback only,
# no persona key, no external network.
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import persona_host_sdk.mcp_bridge as mb
from persona_host_sdk.core import PersonaClient
from persona_host_sdk.tests.conftest import (
    frame_delta, frame_done, frame_tool_call,
)

SDK = Path(__file__).resolve().parents[1].parent   # repo root


def _line(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _rpc(mid, method, params=None):
    m = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        m["params"] = params
    return m


async def test_initialize_handshake_shape():
    b = mb.PersonaBridge(client_factory=lambda: PersonaClient("http://127.0.0.1:1", "t"))
    out = json.loads(await mb._handle_line(b, _line(_rpc(1, "initialize"))))
    assert out["result"]["protocolVersion"] == mb.PROTOCOL_VERSION
    assert out["result"]["capabilities"]["tools"] == {}
    assert out["result"]["serverInfo"]["name"] == "persona-host-sdk"


async def test_tools_list_names():
    b = mb.PersonaBridge(client_factory=lambda: PersonaClient("http://127.0.0.1:1", "t"))
    out = json.loads(await mb._handle_line(b, _line(_rpc(2, "tools/list"))))
    names = {t["name"] for t in out["result"]["tools"]}
    assert names == {"persona_chat", "persona_delegate", "persona_status",
                     "persona_output", "persona_stop", "persona_share_awaken"}


async def test_notification_gets_no_response():
    b = mb.PersonaBridge(client_factory=lambda: PersonaClient("http://127.0.0.1:1", "t"))
    got = await mb._handle_line(b, _line({"jsonrpc": "2.0",
                                          "method": "notifications/initialized"}))
    assert got is None


async def test_unknown_method_is_jsonrpc_error():
    b = mb.PersonaBridge(client_factory=lambda: PersonaClient("http://127.0.0.1:1", "t"))
    out = json.loads(await mb._handle_line(b, _line(_rpc(9, "bogus/method"))))
    assert out["error"]["code"] == -32601


async def test_bad_json_is_parse_error():
    b = mb.PersonaBridge(client_factory=lambda: PersonaClient("http://127.0.0.1:1", "t"))
    out = json.loads(await mb._handle_line(b, "{not json"))
    assert out["error"]["code"] == -32700


async def test_persona_chat_roundtrip(fake_persona):
    fake, base = await fake_persona([[frame_delta("Hi there. "),
                                      frame_done("Hi there.")]])
    b = mb.PersonaBridge(client_factory=lambda: PersonaClient(base, "test"))
    out = json.loads(await mb._handle_line(b, _line(
        _rpc(3, "tools/call", {"name": "persona_chat",
                               "arguments": {"message": "hello-sawii"}}))))
    assert out["result"]["isError"] is False
    assert out["result"]["content"][0]["text"].strip() == "Hi there."
    assert fake.requests[0]["messages"][-1]["content"] == "hello-sawii"
    assert fake.headers[0]["authorization"] == "Bearer test"
    await b.aclose() if hasattr(b, "aclose") else None


async def test_persona_delegate_is_fire_and_forget(fake_persona):
    frames = [[frame_delta("delegating. "),
               frame_tool_call(0, "call_ln9999aaaa_sleepy", "sleepy", {"url": "u"}),
               frame_done("lane running", finish="tool_calls")],
              [frame_done("lane finished")]]
    fake, base = await fake_persona(frames)
    b = mb.PersonaBridge(client_factory=lambda: PersonaClient(base, "test"))
    out = json.loads(await mb._handle_line(b, _line(
        _rpc(4, "tools/call", {"name": "persona_delegate",
                               "arguments": {"task": "do it", "label": "L1"}}))))
    lane = out["result"]["content"][0]["text"]
    assert lane.startswith("ln"), lane            # id returns BEFORE lane work
    st = json.loads(await b.persona_status())
    assert lane in st["delegated_lanes"]
    # regression lock: _lane_run's on_event references TextDelta (was missing
    # from .core imports: NameError => lane_error immediately). Let the lane
    # task run its scripted turn and deny it ever errored that way.
    done_kinds = set()
    deadline = asyncio.get_running_loop().time() + 5.0
    while asyncio.get_running_loop().time() < deadline:
        st2 = json.loads(await b.persona_status())
        done_kinds = {r["kind"] for r in st2["timeline_tail"]}
        if {"lane_error", "lane_done", "lane_stopped"} & done_kinds:
            break
        await asyncio.sleep(0.05)
    assert "lane_error" not in done_kinds, sorted(done_kinds)
    stop_res = json.loads(await b.persona_stop(lane))
    assert stop_res["stopped"] is True


async def test_unknown_tool_is_error_not_crash():
    b = mb.PersonaBridge(client_factory=lambda: PersonaClient("http://127.0.0.1:1", "t"))
    out = json.loads(await mb._handle_line(b, _line(
        _rpc(5, "tools/call", {"name": "no_such_tool", "arguments": {}}))))
    assert out["error"]["code"] == -32602


def test_stdio_subprocess_end_to_end():
    # drive the real server: python -m persona_host_sdk.mcp_bridge over pipes.
    # Every wait is bounded: a wedged child must fail with stderr in the message,
    # never block the suite forever. Loopback URL = zero network, zero spend.
    env = dict(os.environ, SAWII_PERSONA_URL="http://127.0.0.1:9",
               SAWII_PERSONA_KEY="unused-test-key")
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "persona_host_sdk.mcp_bridge"], cwd=str(SDK),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", env=env)
    q_out: "queue.Queue[object]" = queue.Queue()
    err_lines: list[str] = []

    def _pump():                       # stdout -> queue (readline itself may block)
        while True:
            ln = proc.stdout.readline()
            q_out.put(ln or None)      # None marks child stdout EOF
            if not ln:
                return

    def _drain_stderr():               # never let a full stderr pipe wedge the child
        for ln in proc.stderr:
            err_lines.append(ln.rstrip())

    threading.Thread(target=_pump, daemon=True).start()
    threading.Thread(target=_drain_stderr, daemon=True).start()
    try:
        def send(obj):
            # payloads here are <400 B each, far under the 4-8 KB pipe buffer,
            # so these writes can never block; swallow the dead-pipe error and
            # let the next recv() surface it as a clean assertion.
            try:
                proc.stdin.write(json.dumps(obj) + "\n"); proc.stdin.flush()
            except OSError:
                pass

        def recv(what, timeout=15.0):
            try:
                line = q_out.get(timeout=timeout)
            except queue.Empty:
                raise AssertionError(
                    f"child never answered {what} in {timeout}s; "
                    f"rc={proc.poll()} stderr={err_lines[:20]}") from None
            if not line:
                raise AssertionError(
                    f"server died before answering {what}; stderr={err_lines[:20]}")
            return json.loads(line)

        send(_rpc(1, "initialize"))
        assert recv("initialize")["result"]["serverInfo"]["name"] == "persona-host-sdk"
        send(_rpc(2, "tools/list"))
        listing = recv("tools/list")["result"]["tools"]
        assert any(t["name"] == "persona_chat" for t in listing)
        send(_rpc(3, "tools/call", {"name": "persona_share_awaken",
                                    "arguments": {"text": "wake",
                                                  "whisper": False}}))
        call = recv("tools/call persona_share_awaken")["result"]
        assert call["isError"] is False
        assert "recorded" in call["content"][0]["text"]
        send(_rpc(4, "tools/call", {"name": "persona_status", "arguments": {}}))
        st = json.loads(recv("tools/call persona_status")["result"]["content"][0]["text"])
        assert "awaken" in json.dumps(st["timeline_tail"])
    finally:
        with contextlib.suppress(OSError, ValueError):
            proc.stdin.close()          # child treats EOF as shutdown
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)    # reap it; never orphan a wedged child
