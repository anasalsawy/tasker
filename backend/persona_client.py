"""Client for the DL-Companion Persona (sawii-persona) — the unified mind Tasker attaches to.

Persona is one identity per app. Tasker carries its own persona (created once on
DL-Companion via /admin/personas) so all R-lines share one SharedTimeline: voice,
memory, lanes, verifier — one mind for this app.

Turn contract (the only endpoint this client calls):
    POST {base_url}/v1/chat/completions
    Authorization: Bearer {api_key}              <- the persona key
    {"model": "sawii-persona", "stream": true, "messages": [...], "tools": [...]}

SSE frames:
    choices[0].delta.content        -> voice (L) chunks, stream straight to user
    choices[0].delta.tool_calls     -> host-side calls; each has id "call_lnXXXXXXXX_..."
    sawii_status: "delegated"       -> a following tool chunk is handed to a host background agent
    sawii_event                     -> R-lane rows (beat/hold/verify/steer) for optional UI
    finish_reason + sawii_text      -> final voice string
    [DONE]                          -> close

After a turn emits tool_calls, the host runs them (concurrently — one asyncio.Task each),
then sends the results back as {"role":"tool", "tool_call_id":"call_ln...", "content":...}
messages on the next turn. The lane id "lnXXXXXXXX" inside every call id is how the
Persona keeps each line's shared mind ordered.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any, AsyncIterator, Optional

import httpx

# ``call_(lnXXXXXXXX)_`` -> the lane that owns the call. L keeps no lane id.
_LANE_IN_ID = re.compile(r"^call_(ln[0-9a-f]{8})_", re.IGNORECASE)


def lane_of(call_id: str) -> Optional[str]:
    m = _LANE_IN_ID.match(call_id or "")
    return m.group(1) if m else None


class PersonaClient:
    """Async streaming client for DL-Companion's OpenAI-compatible /v1/chat/completions."""

    def __init__(self, base_url: str, api_key: str, timeout_s: float = 180.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s
        self._client: Optional[httpx.AsyncClient] = None

    async def _get(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_s, connect=15.0),
                headers={"Authorization": f"Bearer {self.api_key}"},
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
        steer: Optional[str] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream one Persona turn. Yields typed events:

            {"type": "delta",       "text": "..."}              voice chunks
            {"type": "tool_call",   "tool_call": {...}}         one hop of an R-line
            {"type": "lane_event",  "event": {...}}              sawii_event row (beat/hold/steer)
            {"type": "delegated",   "tools": [...]}              R handed this batch to a host agent
            {"type": "done",        "text": "...", "turn_id": "...", "metrics": {...}}
        """
        body: dict[str, Any] = {
            "model": "sawii-persona",
            "stream": True,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
        if tz:
            body["timezone"] = tz[:64]
        headers: dict[str, str] = {}
        if session_id:
            headers["x-sawii-session-id"] = session_id[:128]
        if steer:
            # "lnXXXXXXXX=instruction" (comma-joined) — the persona server's own
            # mid-task steering rail; read by the model, never by a call's far end.
            headers["x-sawii-steer"] = steer[:512]

        client = await self._get()
        url = f"{self.base_url}/v1/chat/completions"
        async with client.stream("POST", url, json=body, headers=headers) as resp:
            resp.raise_for_status()
            async for raw in resp.aiter_lines():
                if not raw:
                    continue
                if not raw.startswith("data:"):
                    continue
                data = raw[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                for ev in self._parse_chunk(chunk):
                    yield ev

    def _parse_chunk(self, chunk: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        # sawii lanes/kernels rows
        if "sawii_event" in chunk and isinstance(chunk["sawii_event"], dict):
            out.append({"type": "lane_event", "event": chunk["sawii_event"]})
        if "sawii_tool" in chunk and isinstance(chunk["sawii_tool"], dict):
            out.append({"type": "lane_tool", "event": chunk["sawii_tool"]})
        if "sawii_status" in chunk:
            st = chunk["sawii_status"]
            if st == "delegated":
                # dl-companion emitted "delta.tool_calls" too — parse below; only mark delegation.
                out.append({"type": "delegated", "tools": []})
        # OpenAI delta
        for choice in (chunk.get("choices") or []):
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                out.append({"type": "delta", "text": content})
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
        # Some frames only carry sawii_text (no choices) — treat as done.
        if chunk.get("sawii_text") and not any(c.get("finish_reason") for c in (chunk.get("choices") or [])):
            out.append({
                "type": "done",
                "text": chunk["sawii_text"],
                "turn_id": chunk.get("sawii_turn"),
                "metrics": chunk.get("sawii_metrics"),
                "finish_reason": "stop",
            })
        return out


# Hands — Tasker's Persona identity on DL-Companion (persona id 60, created once
# via /admin/personas). Hardcoded so it is never asked for again. This key is the
# identity; Ring it only if a real compromise occurs, and rotate via a new persona.
HANDS_PERSONA_KEY = "sp_sltCBbGrfWzwyiQBUthGNQSE0NxbQNBy-PV673fH6U4"


def default_client() -> PersonaClient:
    base = os.getenv("SAWII_PERSONA_URL", "https://dl-companion-production.up.railway.app").strip()
    key = os.getenv("SAWII_PERSONA_KEY", HANDS_PERSONA_KEY).strip() or HANDS_PERSONA_KEY
    return PersonaClient(base, key)


__all__ = ["PersonaClient", "lane_of", "default_client"]
