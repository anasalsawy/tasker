"""Persona chain client: utterance + ambient context -> streamed Hands reply.

Two routes (founder requirement 5):
    A) Tasker backend  POST {base}/aiagent/persona/{tid}/act
       Contract verified against backend/routers/aiagent/persona_orchestrator.py:
       request body is PersonaActRequest {text, tool_results, session_id, ...};
       SSE frames are "event: <n>\\ndata: <json>\\n\\n" with n in
         delta / lane / lane_tool / tool_call / delegated / tool_result / done / error
       This route needs a real thread id + user JWT (route is auth-guarded) ->
       set [backend] thread_id/token (or HANDS_SHELL_THREAD_ID / _TOKEN).
       Health probe: GET {base}/ (backend main.py answers {'message': now} at '/';
       404 still proves the server is alive). Cached 30 s.
    B) DL-Companion direct  POST {persona.base_url}/v1/chat/completions
       Bearer persona key (Hands persona id 60; same default as
       backend/persona_client.py, env-overridable SAWII_PERSONA_KEY), body
       {"model": "sawii-persona", "stream": true, "messages":[...]}. Plain
       "data: {...}" OpenAI-shape SSE + sawii_* extras; chunk parser mirrors
       PersonaClient._parse_chunk exactly (delta/tool_call/lane_event/
       delegated/done).

Context injection: compact block from shell.context.ContextSampler.summary() is
prefixed to the user content (persona-direct) or appended after it (backend
route), capped by http.context_prefix_max_chars.

Fire-and-forget: run_turn yields events on the CALLER chain thread; the HTTP
handler thread only enqueues (see chain.py).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterator

import httpx

from .config import ShellConfig

log = logging.getLogger("hands.persona")


# ---------------------------------------------------------------- SSE parsing

def sse_data_lines(resp_lines) -> Iterator[str]:
    """Yield payload strings from 'data:' SSE lines; stop at [DONE]."""
    for raw in resp_lines:
        line = raw.strip() if isinstance(raw, str) else raw.decode("utf-8", "ignore").strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        yield data


def sse_event_frames(text_iter) -> Iterator[tuple[str, str]]:
    """Parse full 'event:'+'data:' frames (Tasker backend style). text_iter yields
    lines; blank line terminates a frame."""
    event, datas = "delta", []
    for raw in text_iter:
        line = raw.strip() if isinstance(raw, str) else raw.decode("utf-8", "ignore").strip()
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            d = line[5:].strip()
            if d == "[DONE]":
                if datas:
                    yield event, "\n".join(datas)
                return
            datas.append(d)
        elif not line:
            if datas:
                yield event, "\n".join(datas)
            event, datas = "delta", []
    if datas:
        yield event, "\n".join(datas)


def parse_persona_chunk(chunk: dict[str, Any]) -> list[dict[str, Any]]:
    """Mirror backend/persona_client.py _parse_chunk event vocabulary:
    delta / tool_call / lane_event / lane_tool / delegated / done."""
    out: list[dict[str, Any]] = []
    if isinstance(chunk.get("sawii_event"), dict):
        out.append({"type": "lane_event", "event": chunk["sawii_event"]})
    if isinstance(chunk.get("sawii_tool"), dict):
        out.append({"type": "lane_tool", "event": chunk["sawii_tool"]})
    if chunk.get("sawii_status") == "delegated":
        out.append({"type": "delegated", "tools": []})
    for choice in chunk.get("choices") or []:
        delta = choice.get("delta") or {}
        if delta.get("content"):
            out.append({"type": "delta", "text": delta["content"]})
        for tc in delta.get("tool_calls") or []:
            fn = tc.get("function") or {}
            out.append({"type": "tool_call", "tool_call": {
                "id": tc.get("id") or "", "name": fn.get("name") or "",
                "arguments": fn.get("arguments") or "{}"}})
        if choice.get("finish_reason"):
            out.append({"type": "done", "text": chunk.get("sawii_text", ""),
                        "turn_id": chunk.get("sawii_turn"),
                        "metrics": chunk.get("sawii_metrics"),
                        "finish_reason": choice["finish_reason"]})
    if chunk.get("sawii_text") and not any(c.get("finish_reason")
                                            for c in chunk.get("choices") or []):
        out.append({"type": "done", "text": chunk["sawii_text"],
                    "turn_id": chunk.get("sawii_turn"),
                    "metrics": chunk.get("sawii_metrics"),
                    "finish_reason": "stop"})
    return out


def build_context_block(context_summary: str, max_chars: int) -> str:
    """The 'already knows you' prefix block. Empty-safe."""
    s = (context_summary or "").strip()
    if not s:
        return ""
    return ("[ambient-context device-local observed; window titles only, "
            "no file contents]\n" + s[:max_chars])


# ---------------------------------------------------------------- route probe

_backend_probe_cache: dict[str, Any] = {"ok": None, "checked_at": 0.0}
_PROBE_TTL_S = 30.0


def backend_reachable(cfg: ShellConfig, client: httpx.Client | None = None) -> bool:
    """Quick health check of the local Tasker backend (GET base+health_path).
    Cached ~30s so intent latency never pays TCP twice in a burst. ANY HTTP
    answer (even 401/404) means a server is there; only connection errors don't."""
    now = time.monotonic()
    c = _backend_probe_cache
    if c["ok"] is not None and (now - c["checked_at"]) < _PROBE_TTL_S:
        return bool(c["ok"])
    url = cfg.backend.base_url.rstrip("/") + cfg.backend.health_path
    own = client is None
    cli = client or httpx.Client(timeout=httpx.Timeout(2.5, connect=1.5))
    ok = False
    try:
        r = cli.get(url)
        ok = r.status_code < 500
    except Exception:
        ok = False
    finally:
        if own:
            cli.close()
    c.update(ok=ok, checked_at=now)
    return ok


def invalidate_backend_probe() -> None:
    _backend_probe_cache.update(ok=None, checked_at=0.0)


# ---------------------------------------------------------------- turns


def stream_turn(cfg: ShellConfig, utterance: str, context_summary: str,
                session_id: str | None = None,
                client: httpx.Client | None = None) -> Iterator[dict[str, Any]]:
    """One persona turn -> stream of normalized events:
       {"type": delta|tool_call|lane_event|delegated|tool_result|done|error, ...}
    Chooses backend route (if reachable AND thread_id+token configured) else
    persona-direct. Transport failures NEVER raise out: they become an
    {"type":"error"} event plus an offline done so the shell degrades gracefully."""
    ctx = build_context_block(context_summary, cfg.http.context_prefix_max_chars)
    own = client is None
    cli = client or httpx.Client(timeout=httpx.Timeout(cfg.persona.timeout_s,
                                                       connect=8.0))
    used_backend = False
    try:
        used_backend = bool(cfg.backend.thread_id and cfg.backend.token
                            and backend_reachable(cfg, cli))
        if used_backend:
            yield from _stream_backend(cfg, cli, utterance, ctx, session_id)
        else:
            yield from _stream_direct(cfg, cli, utterance, ctx, session_id)
    except Exception as exc:
        log.warning("persona turn transport error: %s", exc)
        yield {"type": "error", "message": f"{type(exc).__name__}: {exc}"}
        yield {"type": "done",
               "text": "(offline) I'm here. My reply will finish when the "
                       "network is back.",
               "turn_id": None, "finish_reason": "offline_fallback",
               "metrics": None}
    finally:
        if own:
            cli.close()


def _prefix(utterance: str, ctx: str) -> str:
    return (ctx + "\n\nUser (voiced via shell): " + utterance) if ctx else utterance


def _stream_direct(cfg: ShellConfig, cli: httpx.Client, utterance: str,
                   ctx: str, session_id: str | None) -> Iterator[dict[str, Any]]:
    url = cfg.persona.base_url.rstrip("/") + "/v1/chat/completions"
    body = {"model": cfg.persona.model, "stream": True,
            "messages": [{"role": "user", "content": _prefix(utterance, ctx)}]}
    headers = {"Authorization": f"Bearer {cfg.persona.api_key}"}
    if session_id:
        headers["x-sawii-session-id"] = session_id[:128]
    with cli.stream("POST", url, json=body, headers=headers) as resp:
        resp.raise_for_status()
        for data in sse_data_lines(resp.iter_lines()):
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            for ev in parse_persona_chunk(chunk):
                yield ev


def _stream_backend(cfg: ShellConfig, cli: httpx.Client, utterance: str,
                    ctx: str, session_id: str | None) -> Iterator[dict[str, Any]]:
    url = (cfg.backend.base_url.rstrip("/") + cfg.backend.act_path_template
           .format(tid=cfg.backend.thread_id))
    text = utterance + ("\n\n" + ctx if ctx else "")
    body: dict[str, Any] = {"text": text, "tool_results": []}
    if session_id:
        body["session_id"] = session_id
    headers = {"Authorization": f"Bearer {cfg.backend.token}"}
    with cli.stream("POST", url, json=body, headers=headers) as resp:
        resp.raise_for_status()
        for event_name, data in sse_event_frames(resp.iter_lines()):
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            if event_name == "delta":
                yield {"type": "delta", "text": payload.get("text", "")}
            elif event_name == "lane":
                yield {"type": "lane_event", "event": payload}
            elif event_name == "lane_tool":
                yield {"type": "lane_tool", "event": payload}
            elif event_name == "tool_call":
                yield {"type": "tool_call", "tool_call": payload}
            elif event_name == "delegated":
                yield {"type": "delegated", "tools": payload.get("tools", [])}
            elif event_name == "tool_result":
                yield {"type": "tool_result", "result": payload}
            elif event_name == "done":
                yield {"type": "done", "text": payload.get("text", ""),
                       "turn_id": payload.get("turn_id"),
                       "finish_reason": "stop", "metrics": None,
                       "tools_pending_client": payload.get("tools_pending_client", [])}
            elif event_name == "error":
                yield {"type": "error", "message": payload.get("message",
                                                               "backend error")}


def collect_reply(cfg: ShellConfig, utterance: str, context_summary: str,
                  session_id: str | None = None,
                  client: httpx.Client | None = None) -> dict[str, Any]:
    """Full turn joined to text. Returns {text, events_n, tool_calls, error}.
    Used by the chain worker + tests."""
    parts: list[str] = []
    tools: list[dict] = []
    err: str | None = None
    n = 0
    for ev in stream_turn(cfg, utterance, context_summary, session_id, client):
        n += 1
        t = ev.get("type")
        if t == "delta":
            parts.append(ev.get("text", ""))
        elif t == "tool_call":
            tools.append(ev.get("tool_call", {}))
        elif t == "error":
            err = ev.get("message")
        elif t == "done" and ev.get("text"):
            if not parts:
                parts = [ev["text"]]
    return {"text": "".join(parts), "events_n": n, "tool_calls": tools,
            "error": err}


__all__ = ["stream_turn", "collect_reply", "backend_reachable",
           "invalidate_backend_probe", "build_context_block",
           "parse_persona_chunk", "sse_data_lines", "sse_event_frames"]
