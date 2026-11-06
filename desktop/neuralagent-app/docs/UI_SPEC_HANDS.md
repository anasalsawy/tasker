# UI Spec — Hands (bar | chat | pet)

Source of truth: `src/state/handsMachine.js` — a pure CommonJS reducer + selectors,
no React, no DOM. Golden-path harness: `scripts/test_hands_machine.mjs`
(plain node ESM; exit 0 green, exit 1 first failure). React wiring lives in
`src/hooks/useHands.js` (SSE from `src/utils/personaClient.js` + legacy Electron
TASKER_EVENTs -> dispatch); consumers: `views/Thread.js`, `views/Overlay.js`,
`views/Home.js`, `components/ExecutionPet.js`, with sidebar live-run titles fanned
out through `src/state/handsBus.js` (`publishHandsStatus`).

## The three modes

| mode   | face | entered by |
|--------|------|------------|
| `bar`  | slim idle pill (`HandsBar`) — mic-level dot, no conversation surface | `initialState()`; `collapse` event |
| `chat` | normal conversation: user echo + streamed `hands` replies | first `user_text` / `delta` / `chat_reply` from bar; `task_finished` and `agent_exit` leave pet back to chat |
| `pet`  | compact execution surface (`ExecutionPet`): task title, status line, up to 4 lane chips (+N), shimmer progress rail, stop button | task signals only — see the gate below |

Pet is sticky while a task is live: once inside, `user_text` / `chat_reply` keep
`mode: 'pet'` (a mid-run follow-up never yanks the UI out of execution).

## Task-gated collapse rule (the load-bearing one)

Plain chat NEVER enters pet. No text content — greetings, questions, even
"delete every file"-style requests — escalates the UI at parse time. The classifier
is never on the conversation path. Pet is entered ONLY post-hoc, when real work
signals arrive on the stream:

- `tool_call` — one hop of an R-line. `mode -> 'pet'` immediately, lane from
  `ev.lane` or parsed from the call id (`laneFromCallId`: /^call_(ln[0-9a-f]{8})_/i,
  e.g. `call_lndeadbeef_123456` -> lane `lndeadbeef`), toolsTotal++.
- `lane` — sawii_event row (beat/hold/verify/steer/done) -> pet, lane status updated.
- `lane_tool` — lane-level tool row -> pet, lane label = shortLabel(name, args).
- `delegated` — R handed a batch to a host agent -> pet with zero lanes ("Planning…"
  window), `delegated: true`.
- `task_recognized` — explicit task-intent field (legacy `type === 'desktop_task'`).
- `agent_activity` — legacy desktop-agent TASKER_EVENT (the agent only runs for real
  tasks) -> pet on synthetic lane `ln-desktop`.

Everything else (`user_text`, `delta`, `chat_reply`, `turn_done`) is
bar->chat at most. `turn_done` never leaves pet on its own — pending client tools
(`tools_pending_client`) keep execution alive until the final tool_result arrives.

**Zero latency on the conversation path:** voice/text streaming is never awaited on
recognition. `delta` chunks render the moment they arrive; the task verdict is
derived from events that land AFTER the stream started. `collapse` returns to bar
by operator request; `task_finished` / `agent_exit` return pet -> chat.

## Always-open voice lane L

`src/voice/voiceLane.js` keeps the mic channel open hands-free by default
(`continuous = true`, auto-reopen after Chrome stops on silence). Endpointer is a
WebAudio RMS gate (threshold ~0.012, 700 ms hangover, 250 ms min speech, 20 s cap).
Utterances fire `onUtterance(text)` **fire-and-forget** -> `user_text` + a /act turn.
Nothing in voice awaits the reply path or recognition. `interrupt()` supports barge-in;
TTS self-bleed does not re-trigger (suppressUntil guard + ducking while speaking).

## Concurrent R lanes

`state.lanes` maps lane id -> {id,status,currentTool,calls,done,errors,label}; `laneOrder`
keeps render order. Status: idle/running/held/verified/steered -> active; done/error ->
terminal. `selectActiveLaneCount` is the headline; pet renders first 4 chips + `+N` overflow.
`selectProgress` = `min(1, toolsDone / toolsTotal)` for the fill rail width.

## Shimmer rules (`selectIsShimmering`)

Shimmer = the animated overlay on the pet progress rail + pulsing orb
(`.hands-pet.is-shimmering`). Pure function of state:

- `mode !== 'pet'` -> false (bar and chat never shimmer).
- `outstanding` -> active lanes > 0 OR pendingClientTools > 0 OR toolsDone < toolsTotal -> true.
- `planning` -> turnActive && toolsTotal === 0 && no lanes (delegated, pre-tool window) -> true.
- Terminal results settle it: once every tool_call resolved (toolsDone >= toolsTotal) and
  lanes are done/error, the rail goes still while still in pet.

## Pet status line (`selectStatusLine`)

Returns null outside pet. In pet the format is `' · '`-joined fragments:

- `toolsTotal === 0` and no lanes -> `"Planning…"`.
- `"<N> lane(s) live"` when active lanes > 1 -> "N lanes live", else "N lane live".
- `"<toolsDone>/<toolsTotal> steps"` when toolsDone > 0.
- `"running <currentTool>"` when state.currentTool is set.
- `"<N> on-device"` when pendingClientTools > 0.
- none of the above -> `"Wrapping up…"`.

Example: `"2 lanes live · 7/9 steps · running click · 1 on-device"`.
