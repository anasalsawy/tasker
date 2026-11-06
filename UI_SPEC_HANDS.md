# UI_SPEC_HANDS — the task-gated face of Hands

Product rule in one line: **the shape of the surface is decided AFTER the
answer starts, from stream evidence — never before it.** Plain conversation
("hi") must never put the app into an execution posture; a real task must
visibly collapse the surface into a compact, non-obscuring execution pet as
soon as the stream proves work has begun.

## The three states

| State | Face | Window (Electron overlay) | Shown when |
|---|---|---|---|
| `bar` (idle) | slim glass pill, 60×60 corner chip | `OVERLAY.idle` | app start, after `collapse`, after `task_finished` on closed overlay |
| `chat` | conversation thread; expanded panel has chat log + composer + mic/background/thinking toggles; **no execution chrome** | `OVERLAY.chat` 376×64 collapsed-height, `chatSuggestions` 376×392 when suggested tasks show | user text/delta/`chat_reply` with zero task evidence |
| `pet` (execution) | ExecutionPet strip: task title, status line (`N lanes live · X/Y steps · running <tool> · Z on-device`), per-lane chips (≤4 + "+n"), progress rail, shimmer, stop button | `OVERLAY.pet` 320×64, corner-pinned, always-on-top, never covers the working area | a tool_call/lane/delegated/agent_activity signal, post-hoc |

States live in `desktop/neuralagent-app/src/state/handsMachine.js` — a pure
CommonJS reducer, no React, no DOM: `initialState()` / `reduce(state, ev)` /
selectors `selectLanes`, `selectActiveLaneCount`, `selectProgress`,
`selectIsShimmering`, `selectStatusLine`.

## Event → transition map

SSE frames from `POST /aiagent/persona/{tid}/act` (parser:
`src/utils/personaClient.js`; mapper: `src/hooks/useHands.js` →
`mapPersonaEvent`):

| SSE / IPC frame | reducer event | bar→ | chat→ | pet→ | notes |
|---|---|---|---|---|---|
| — | `user_text` | chat | chat | pet (stay) | local echo first, zero network, NEVER awaits classifier |
| `delta` | `delta` | chat | chat (append/stream) | pet (stay) | streaming voice/text; text flowing is NOT a task signal |
| *(legacy `POST /threads` reply `response`)* | `chat_reply` | chat | chat | pet (stay) | classifier answered conversationally |
| *(legacy reply `type: desktop_task`)* | `task_recognized` | **pet** | **pet** | pet | the only pre-first-tool escalation allowed, and it arrives post-reply |
| `tool_call` | `tool_call` | **pet** | **pet** | pet | the real gate: a hop executed = work is happening; lane id parsed from `call_ln########_` prefix |
| `tool_result` | `tool_result` | bar (no-op gate) | chat | pet | advances done/errors counters, clears lane's currentTool |
| `lane` (beat/hold/verify/steer/done) | `lane` | **pet** | **pet** | pet | lane status chips update; lane keyed by `event.lane` |
| `lane_tool` | `lane_tool` | **pet** | **pet** | pet | per-lane current tool line |
| `delegated` | `delegated` | **pet** | **pet** | pet | R1 handed a batch to a host agent; pet shows `Planning…` until first tool |
| `done` (turn close) | `turn_done` | — | — | pet | records `tools_pending_client` as on-device debt; chat may continue over it |
| `error` | `chat_reply ⚠` | chat | chat | chat exit only if lane closed | errors never trap the pet open |
| IPC `ai-agent-status` (legacy TASKER_EVENT lines from `desktop/aiagent/main.py`, bridged in `desktop/main.js`) | `agent_activity` | **pet** | **pet** | pet | agent process only runs for real tasks |
| IPC `ai-agent-exit` | `agent_exit` | chat | chat | **chat** | "Execution finished — back to you." |
| — | `task_finished` | chat | chat | **chat** | stop button / completion |
| — | `collapse` | **bar** | **bar** | **bar** | operator pin demand |
| — | `show_suggestions` | — | toggle | — | window may grow to `chatSuggestions` height |

Unknown/inert frames return state unchanged — the reducer cannot crash on
backend noise (tested).

## The post-hoc rule (hard contract)

1. Voice/text output NEVER waits on task classification. `dispatchUser()`
   (Overlay) and `sendMessage()` (Thread, persona profile) echo the user
   locally, then fan out: persona SSE streaming begins immediately while the
   legacy `/threads` classify call runs fire-and-forget alongside. No
   `await` on the reply path touches: the classifier, ingestion, verification,
   or lane bookkeeping.
2. Escalation `chat→pet` happens ONLY on: `tool_call`, `lane_tool`, `lane`,
   `delegated`, `agent_activity`, `task_recognized` (legacy classifier field
   or launched desktop-agent thread). Entropy flows one way per turn;
   de-escalation is `task_finished`/`agent_exit`, manual `collapse` always.
3. The window geometry obeys the mode: renderer pushes mode to main via
   `set-overlay-mode` IPC (`preload.js` → `electronAPI.setOverlayMode`);
   `desktop/main.js` `applyOverlayBounds()` resizes the overlay — pet is a
   320×64 corner strip, chat keeps the slim footprint, and the 60×60 idle
   chip is the default face that never obscures the screen.
4. Cross-surface sync: `state/handsBus.js` pub/sub feeds the sidebar
   (`TaskerSidebar.js` live tags) while a Thread page owns the machine.

## Voice lane (always-open, hands-free default)

`src/voice/voiceLane.js`: continuous `SpeechRecognition` + WebAudio RMS
endpointing (hangover 700ms, min-speech 250ms, max 20s), auto-reopen after
Chrome's silence stops, TTS ducking to avoid self-trigger, dedup guard, and
`on('utterance')` delivery that MUST be fire-and-forget. Toggle persisted in
electron-store key `_NA_HANDS_FREE` (default true). Barge-in: `interrupt()`
clears TTS queue instantly.

## Visible execution status = speed made legible

Pet line format: `{N} lanes live · {done}/{total} steps · running {tool} · {k} on-device`
(from `selectStatusLine`). Shimmer while any lane is non-terminal or
pending client tools. Progress rail = done/total clamped 0–1.

## Tests

- Jest: `desktop/neuralagent-app/src/state/handsMachine.test.js`
  (`npm test -- --watchAll=false` from `desktop/neuralagent-app`)
- Plain node, zero deps: `node scripts/test_hands_machine.mjs` (repo root)
- Golden paths both assert: **A** `"hi"` + streamed reply ⇒ stays `chat`,
  zero lanes, no shimmer; **B** `tool_call`/`lane`×2/`delegated` ⇒ `pet`,
  `activeLanes` tracked, status line lists lanes, `task_finished` ⇒ `chat`.
