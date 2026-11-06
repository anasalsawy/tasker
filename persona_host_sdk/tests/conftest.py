# tests/conftest.py — shared fixtures: fake persona SSE servers + frame builders.
# No live endpoints are hit by any test; zero spend.
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

SDK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SDK_ROOT))          # import persona_host_sdk by package name

from persona_host_sdk.core import (  # noqa: E402
    LaneLog, PersonaClient, PersonaSession, ToolRegistry, lane_of,
)

# ── frame builders (mirror backend test_persona_integration.py fixtures) ─────

def ndjson(items: list[dict[str, Any]]) -> bytes:
    """SSE body in the exact format the backend test fixture uses."""
    return ("\n".join(f"data: {json.dumps(x, ensure_ascii=False)}" for x in items)
            + "\ndata: [DONE]\n").encode()


def frame_delta(text: str) -> dict[str, Any]:
    return {"choices": [{"delta": {"content": text}, "finish_reason": None}]}


def frame_tool_call(index: int, call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"choices": [{"delta": {"tool_calls": [{
        "index": index, "id": call_id, "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }]}, "finish_reason": None}]}


def frame_done(sawii_text: str = "voice tail", finish: str = "stop") -> dict[str, Any]:
    return {"sawii_text": sawii_text, "choices": [{"delta": {}, "finish_reason": finish}]}


def frame_lane_event(**row: Any) -> dict[str, Any]:
    return {"sawii_event": row}


# ── canned frame sequences ───────────────────────────────────────────────────

@pytest.fixture
def three_lane_frames() -> list[dict[str, Any]]:
    """One turn: voice + 3 delegated tool_calls on distinct lanes."""
    return [
        frame_delta("Three in parallel. "),
        frame_tool_call(0, "call_lnaaaaaaa1_probe", "sleepy", {"url": "http://a/"}),
        frame_tool_call(1, "call_lnbbbbbbb2_probe", "sleepy", {"url": "http://b/"}),
        frame_tool_call(2, "call_lnccccccc3_probe", "sleepy", {"url": "http://c/"}),
        frame_done("three lanes started", finish="tool_calls"),
    ]


@pytest.fixture
def tool_followup_frames() -> list[dict[str, Any]]:
    """Follow-up turn (after role=tool results): closes clean."""
    return [
        frame_delta("All lanes finished — I kept talking."),
        frame_done("done"),
    ]


# ── the sleepy tool: 0.5 s each call; concurrency shows as wall-time ─────────

SLEEP = 0.5


@pytest.fixture
def sleepy_registry() -> ToolRegistry:
    reg = ToolRegistry()

    async def sleepy(args: dict) -> str:
        await asyncio.sleep(SLEEP)
        return "slept:" + str(args.get("url", ""))

    reg.register("sleepy", sleepy, description="sleepy page probe",
                 parameters={"type": "object", "properties": {"url": {"type": "string"}}})
    return reg


@pytest.fixture
def sleepy_registry_named() -> ToolRegistry:
    """Same tool, but declared under the host-flavoured name 'probe' for
    schema-echo tests (persona emits 'sleepy', host declares 'probe')."""

    async def sleepy(args: dict) -> str:
        await asyncio.sleep(SLEEP)
        return "probed:" + str(args.get("url", ""))

    reg = ToolRegistry()
    reg.register("probe", sleepy, description="host-side probe",
                 parameters={"type": "object", "properties": {"url": {"type": "string"}}})
    return reg


# ── fake persona: serves scripted SSE streams, records every request ────────

class FakePersona:
    """Turn-scripted SSE server. Each POST /v1/chat/completions consumes the
    next script (list of frame dicts). Records request bodies + headers."""

    def __init__(self, scripts: list[list[dict[str, Any]]], delay_first: float = 0.0):
        self.scripts = list(scripts)
        self.requests: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        self.delay_first = delay_first

    async def respond(self, request_body: dict[str, Any],
                      headers: dict[str, str]) -> bytes:
        self.requests.append(request_body)
        self.headers.append({k.lower(): v for k, v in headers.items()})
        if self.delay_first:
            await asyncio.sleep(self.delay_first)
            self.delay_first = 0.0
        if not self.scripts:
            return ndjson([{
                "error": {"message": "fake persona: no more scripted turns",
                         "code": "script_exhausted"}}])
        return ndjson(self.scripts.pop(0))


class FakeServer:
    """Minimal asyncio HTTP server that speaks just enough SSE for httpx."""

    def __init__(self, fake: FakePersona):
        self.fake = fake
        self.port = 0
        self._server = None

    async def start(self) -> str:
        async def client_connected(reader: asyncio.StreamReader,
                                   writer: asyncio.StreamWriter) -> None:
            try:
                raw = await reader.readuntil(b"\r\n\r\n")
                lines = raw.decode("utf-8", "replace").split("\r\n")
                header_map = {}
                for ln in lines[1:]:
                    if ":" in ln:
                        k, v = ln.split(":", 1)
                        header_map[k.strip().lower()] = v.strip()
                length = int(header_map.get("content-length", "0") or 0)
                body = await reader.readexactly(length) if length else b"{}"
                payload = json.loads(body.decode("utf-8"))
                sse = await self.fake.respond(payload, header_map)
                writer.write(b"HTTP/1.1 200 OK\r\n"
                             b"content-type: text/event-stream\r\n"
                             b"content-length: "
                             + str(len(sse)).encode()
                             + b"\r\n\r\n"
                             + sse)
                await writer.drain()
            except Exception:
                pass
            finally:
                try:
                    writer.close()
                except Exception:
                    pass

        self._server = await asyncio.start_server(client_connected, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return "http://127.0.0.1:%d" % self.port

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()


@pytest.fixture
async def fake_persona(monkeypatch):
    """Factory fixture: FakePersona(scripts) wired to a live local HTTP port.

    Usage:
        srv, base = await fake_persona([[frames...], [frames...]])
        client = PersonaClient(base_url=base, api_key="test")
    """
    running: list[FakeServer] = []

    async def make(scripts: list[list[dict[str, Any]]], delay_first: float = 0.0):
        fake = FakePersona(scripts, delay_first=delay_first)
        srv = FakeServer(fake)
        base = await srv.start()
        running.append(srv)
        return fake, base

    yield make

    for s in running:
        await s.stop()

