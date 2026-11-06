# UI_SPEC_HANDS — task-gated state machine

Product rule: **the surface shape is decided AFTER the answer starts, from
stream evidence.** "hi" never puts Hands into an execution posture; a real
task collapses the UI into a compact pet only once the stream proves work.

## States

| State | Face | Electron overlay geometry |
|---|---|---|
| `idle-bar` | slim glass pill, 60×60 corner chip — the default face, never obscures the screen | `OVERLAY.idle` |
| `chat-mode` | conversation thread + composer, mic / background / thinking toggles; no execution chrome | `OVERLAY.chat` 376×64; `chatSuggestions` 376×392 only when suggestions show |
| `execution-pet` | ExecutionPet strip: title, status line, lane chips (≤4+more), progress rail, shimmer, stop | `OVERLAY.pet` 320×64, corner-pinned |

Pure reducer: `desktop/neuralagent-app/src/state/handsMachine.js`
(`initialState` / `reduce` / selectors). No React, no DOM — CommonJS so
`scripts/test_hands_machine.mjs` requires it directly.

## Transition map (event → mode)

| Source frame | reducer event | escalation |
|---|---|---|
| user text / voice utterance | `user_text` | bar→chat (local echo, no network gate) |
| SSE `delta` | `delta` | bar→chat; streaming append; text is NOT a task signal |
| legacy classify `response` | `chat_reply` | stays chat |
| SSE `tool_call` | `tool_call` | **→ pet** (the real post-hoc gate); lane id from `call_ln########_` |
| SSE `lane` (beat/hold/verify/steer/done) | `lane` | **→ pet**; lane chips update |
| SSE `lane_tool` | `lane_tool` | **→ pet**; per-lane current tool |
| SSE `delegated` | `delegated` | **→ pet** with `Planning…` until first tool |
| SSE `tool_result` | `tool_result` | resolves lane; shimmer stops when all lanes terminal |
| SSE `done` | `turn_done` | records `tools_pending_client` ("N on-device"); chat may continue |
| IPC `ai-agent-status` (TASKER_EVENT) | `agent_activity` | **→ pet** (legacy agent only runs for real tasks) |
| IPC `ai-agent-exit` | `agent_exit` | pet → chat |
| stop / completion | `task_finished` | pet → chat |
| operator pin | `collapse` | any → bar |

Unknown frames are inert; the reducer cannot crash on backend noise (tested).

## Post-hoc rule (hard contract)

1. Voice/text output never awaits classification. Overlay `dispatchUser()` and
   Thread `sendMessage()` (persona profile) echo locally, start the persona SSE
   immediately, and run legacy `/threads` classify fire-and-forget alongside.
2. `chat→pet` only on `tool_call` / `lane` / `lane_tool` / `delegated` /
   `agent_activity` / `task_recognized` (classifier `desktop_task` or launched
   agent thread — both arrive post-reply). Escalation per turn is one-way until
   a terminal event.
3. Renderer pushes mode via IPC `set-overlay-mode` (`preload.js`
   `setOverlayMode` → `main.js applyOverlayBounds`); OS window obeys the
   machine, chat never grows execution chrome.
4. `state/handsBus.js` pub/sub mirrors live run titles into TaskerSidebar
   while a Thread page owns the machine.

## Voice lane (always-open)

`src/voice/voiceLane.js`: continuous SpeechRecognition + WebAudio RMS
endpointing (threshold 0.012, hangover 700 ms, min speech 250 ms, max 20 s),
auto-reopen after Chrome's silence stop, TTS self-trigger ducking, 2.5 s dedup
guard, barge-in `interrupt()`. Utterances fire-and-forget into the same path
as typed text. Persisted toggle: electron-store `_NA_HANDS_FREE`, default ON
(IPC `get/set-hands-free-value`).

## Tray / shell notes

- Overlay window: frameless, transparent, always-on-top, skip-taskbar; sizes
  live in `main.js` `OVERLAY` constants; corner-pinned bottom-right with 25 px
  margin on the primary display workArea.
- `expandOverlay(hasSuggestions)` / `minimizeOverlay()` keep legacy behavior;
  `applyOverlayBounds()` composes expanded × suggestions × preferred mode.
- Legacy desktop agent stdout bridge: lines starting `TASKER_EVENT:` are
  parsed in `main.js` and fanned to both windows as `ai-agent-status`.

## Visible execution = speed made legible

Status line: `N lane(s) live · X/Y steps · running {tool} · K on-device`
(`selectStatusLine`). Shimmer while any lane is live or statements resolve.
Progress rail: toolsDone/toolsTotal clamped 0–1.

## Tests

- Jest: `src/state/handsMachine.test.js` →
  `npx react-scripts test --testPathPattern handsMachine --watchAll=false --ci`
- Plain node, zero deps: `node scripts/test_hands_machine.mjs`
- Goldens: chat "hi" stays chat (0 lanes, no shimmer); tool/lane/delegated
  enter pet and track `activeLanes`; resolution returns to bar/chat.
