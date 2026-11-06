# persona_host_sdk

Run the DL-Companion **Persona** (`sawii-persona`) as the *brain* of any agent host
— Cursor, Goose, Hermes, Klein, or anything speaking OpenAI-compatible endpoints or MCP —
while the host keeps its own hands. The persona streams its voice on **L** and delegates
work on **R** lanes (`call_(lnXXXXXXXX)_…` ids); your host executes the lanes. L never
awaits R. Results re-feed automatically at turn boundaries up to `max_turns`.

    core.py               PersonaClient / PersonaSession / ToolRegistry / typed SSE events
    strategies.py         Mode A: ModelSwapAdapter   Mode B: ToolMirrorAdapter
    cursor_task_shim.py   Cursor 'Task' / Goose 'agent' / Hermes 'delegate_task' mirrors
    mcp_bridge.py         stdio MCP server: persona_chat|delegate|status|output|stop|share_awaken
    tests/                28 offline tests (fake SSE persona server; no key, no network)

pip install -e .   (httpx is the only runtime dep; fastapi/uvicorn only for Mode A serving)

## Mode A — inference swap (host calls US as "the model")

`ModelSwapAdapter` serves `/v1/chat/completions` locally; point any host at it.
Persona tool-calls are **schema-echoed** onto the tool names/schema the host declared
(the `call_lnXXXXXXXX_` id is preserved so the host's role=tool roundtrip re-attaches).

```jsonc
// Goose — ~/.config/goose/config.yaml  custom_providers entry
{
  "GOOSE_PERSONA": {
    "api_base": "http://127.0.0.1:8321/v1",
    "api_key": "any-string",
    "context_length": 128000,
    "model_info": { "sawii-persona": { "required": false, "context_limit": 128000 } }
  }
}
```
```toml
# Hermes — model block (config.toml), served by:
#   python -c "import uvicorn; from persona_host_sdk.strategies import build_app; \
#              uvicorn.run(build_app(), host='127.0.0.1', port=8321)"
[model]
provider = "openai"
base_url  = "http://127.0.0.1:8321/v1"
model     = "sawii-persona"
api_key   = "any-string"
```

**Cursor caveat:** Cursor's chat path is *Responses API*, not chat/completions — Mode A
works everywhere that posts OpenAI `messages`+`tools` (Goose, Hermes, Klein, LiteLLM-style
routers, Open WebUI). For Cursor itself use Mode B below. (Klein/GHFalcon proxy configs are
the same `base_url` swap.)

## Mode B — host-native Task mirror (Cursor, or any host with a subagent tool)

`CursorTaskShim` impersonates the host's Task tool: the host model believes it spawned
subagents; each call actually runs a headless persona lane (own PersonaSession, persona
identity via session-bridged ids `host-…_mirNNNNNN`), with shared-timeline chatter visible
while the parent streams.

```python
from persona_host_sdk import PersonaClient, CursorTaskShim, ToolRegistry

reg = ToolRegistry()
reg.register("fetch_page", my_async_fetch, parameters={"type": "object",
            "properties": {"url": {"type": "string"}}})   # persona calls these

shim = CursorTaskShim(client_factory=lambda: PersonaClient(
    "https://dl-companion-production.up.railway.app", key), registry=reg)

# wire into the host where it dispatches 'Task':
result_text = await shim.handle_call({"description": "audit", "prompt": "…",
                                      "subagent_type": "generalPurpose",
                                      "run_in_background": False})
```

Goose: same shim as `agent` tool (`GooseAgentShim`); Hermes: `HermesTaskShim` (`delegate_task`).
Steering verbs the host believes it owns: `shim.output_of(ref)`, `shim.stop(ref)`,
`shim.steer(ref, "…")` — refs accept mirror id `mirNNNNNN`, persona lane `lnXXXXXXXX`,
or raw call id `call_lnXXXXXXXX_name`.

## Mode C — MCP bridge (any MCP host: Cursor, Claude Desktop, Windsurf, Zed…)

```jsonc
// Cursor: settings → MCP Servers (or .cursor/mcp.json in a project)
{
  "mcpServers": {
    "persona": {
      "command": "python",
      "args": ["-m", "persona_host_sdk.mcp_bridge"],
      "env": { "SAWII_PERSONA_URL": "https://dl-companion-production.up.railway.app",
               "SAWII_PERSONA_KEY": "sp_…" }
    }
  }
}
```

Tools: `persona_chat` (blocking mind turn), `persona_delegate` (fire-and-forget lane → id),
`persona_status` (lane + timeline snapshot), `persona_output`, `persona_stop`,
`persona_share_awaken` (shared-mind whisper). `persona_delegate` returns the lane id
*before* the lane does any work — poll `persona_output` like a host background task.

## Steering rails

`PersonaSession.steer_lane("ln…", txt)` ships instructions two ways next turn:
message text (always) + `x-sawii-steer` header (newer servers). `stop_lane()` cancels
local dispatch and synthesizes a `stopped` tool-result so the mind sees the break;
server-side continuation is TODO-live-verify (see tests/README note below).

`strict_openai=True` keeps history 100 % OpenAI-shaped (no sawii_* fields sent back).
Observability: every lifecycle row appends to JSONL (`log_path=`) — lane_started,
call_completed, steer_queued, lane_stopped… shared-mind demo grade.

## Tests

`python -m pytest persona_host_sdk/tests -q` → 28 passed, all offline: a loopback fake
persona streams the exact SSE contract (delta / tool_calls / sawii_event / sawii_text /
[DONE]) from `backend/test_persona_integration.py` fixtures. Wall-time asserts prove the
R lanes fan out in parallel and that L's first voice lands before any lane finishes.

## Live-verification TODO (needs the real endpoint)

- Confirm `x-sawii-steer` / stop headers land server-side (rails: header vs text, A/B it).
- Confirm lane id ↔ persona `sawii_turn` correlation on live lane_event rows.
- ModelSwapAdapter behind a real Goose session (schema-echo roundtrip with its builtin tools).
