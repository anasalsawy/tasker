#!/usr/bin/env node
/**
 * Plain-node golden-path runner for the Hands state machine.
 *
 * Zero deps, zero jsdom: requires the pure CommonJS reducer directly and
 * asserts the same two golden paths as src/state/handsMachine.test.js.
 * Exits non-zero with a diff-style message on the first failure.
 *
 *   node scripts/test_hands_machine.mjs
 */
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const machine = require(path.join(ROOT, 'desktop', 'neuralagent-app', 'src', 'state', 'handsMachine.js'));

const { initialState, reduce } = machine;

let passed = 0;
const failures = [];

function check(name, actual, expected, deep = false) {
  const a = deep ? JSON.stringify(actual) : actual;
  const e = deep ? JSON.stringify(expected) : expected;
  if (a === e) { passed += 1; console.log('  ok   ' + name); }
  else { failures.push(name + '\n    expected: ' + e + '\n    actual:   ' + a); console.log('  FAIL ' + name); }
}

function run(events, state) {
  return events.reduce((acc, ev) => reduce(acc, ev), state || initialState());
}

console.log('Hands state machine — golden paths (node ' + process.version + ')');

/* ── Path A: plain chat ("hi") never collapses into the execution pet ───── */
console.log('\n[A] chat-only conversation stays chat');

check('A0 default state is the slim bar', initialState().mode, 'bar');

const chatState = run([
  { kind: 'user_text', text: 'hi' },
  { kind: 'delta', text: 'Hey ' },
  { kind: 'delta', text: 'there!' },
  { kind: 'turn_done', text: 'Hey there!' },
]);
check('A1 "hi" -> chat after streamed reply', chatState.mode, 'chat');
check('A2 no lanes were created', chatState.laneOrder.length, 0);
check('A3 no tool counters moved', chatState.toolsTotal, 0);
check('A4 chat transcript intact', chatState.chat.map((m) => m.text), ['hi', 'Hey there!'], true);
check('A5 no shimmer', machine.selectIsShimmering(chatState), false);

const classifierChat = run([
  { kind: 'user_text', text: 'how are you' },
  { kind: 'chat_reply', text: 'Good — what should we do?' },
]);
check('A6 classifier chat_reply stays chat', classifierChat.mode, 'chat');

check('A7 collapse returns to bar', run([{ kind: 'user_text', text: 'hi' }, { kind: 'collapse' }]).mode, 'bar');

/* ── Path B: real task events collapse the surface into the pet ─────────── */
console.log('\n[B] task signals (tool_call / lane / delegated) enter pet');

const toolState = run([
  { kind: 'user_text', text: 'open chrome and save the brief' },
  { kind: 'delta', text: 'On it. ' },
  { kind: 'tool_call', id: 'call_ln1111aaaa_1', name: 'open_app', arguments: '{"app_name":"Chrome"}' },
]);
check('B1 tool_call -> pet (post-hoc gate)', toolState.mode, 'pet');
check('B2 current tool visible', toolState.currentTool, 'open_app');
check('B3 one active lane', machine.selectActiveLaneCount(toolState), 1);
check('B4 status line names lanes', machine.selectStatusLine(toolState).includes('1 lane live'), true);
check('B5 shimmer while active', machine.selectIsShimmering(toolState), true);
check('B6 voice text was never gated on recognition', toolState.chat.some((m) => m.role === 'hands'), true);

const laneState = run([
  { kind: 'lane', event: { lane: 'ln-a', type: 'beat' } },
  { kind: 'lane', event: { lane: 'ln-b', type: 'beat' } },
  { kind: 'lane_tool', name: 'read_file', lane: 'ln-a' },
  { kind: 'lane_tool', name: 'write_file', lane: 'ln-b' },
]);
check('B7 lane frames -> pet', laneState.mode, 'pet');
check('B8 activeLaneCount tracks N lanes', machine.selectActiveLaneCount(laneState), 2);
check('B9 lane order preserved', machine.selectLanes(laneState).map((l) => l.id), ['ln-a', 'ln-b'], true);

const delegatedState = run([
  { kind: 'user_text', text: 'do the whole refund thing' },
  { kind: 'chat_reply', text: 'Delegating that now.' },
  { kind: 'delegated' },
]);
check('B10 delegated -> pet', delegatedState.mode, 'pet');
check('B11 pre-tool pet shows planning', machine.selectStatusLine(delegatedState), 'Planning\u2026');

let finishState = run([
  { kind: 'tool_call', id: 'call_ln2222bbbb_1', name: 'click' },
  { kind: 'tool_call', id: 'call_ln2222bbbb_2', name: 'type' },
]);
finishState = reduce(finishState, { kind: 'tool_result', tool_call_id: 'call_ln2222bbbb_1', status: 'ok' });
check('B12 half progress after one result', Math.round(machine.selectProgress(finishState) * 100), 50);
finishState = reduce(finishState, { kind: 'tool_result', tool_call_id: 'call_ln2222bbbb_2', status: 'error' });
check('B13 no lanes left active after results', machine.selectActiveLaneCount(finishState), 0);
finishState = reduce(finishState, { kind: 'task_finished' });
check('B14 task_finished leaves pet', finishState.mode, 'chat');

const legacyState = run([
  { kind: 'user_text', text: 'clean my downloads' },
  { kind: 'agent_activity', action: 'click', message: 'Clicking Sort by date' },
]);
check('B15 legacy agent activity -> pet', legacyState.mode, 'pet');
check('B16 agent_exit hands control back', reduce(legacyState, { kind: 'agent_exit' }).mode, 'chat');

check('B17 lane id parsed from call id', machine.laneFromCallId('call_ln3ff9a1b2_9'), 'ln3ff9a1b2');

/* ── A10: recognition never blocks the reply path (ordering invariant) ──── */
console.log('\n[ordering] reply text lands BEFORE the task signal');
const ordered = run([
  { kind: 'delta', text: 'Sure, opening Chrome now. ' },   // voice/text first
  { kind: 'tool_call', id: 'call_ln9999ffff_1', name: 'open_app' }, // task proof after
]);
check('O1 first delta alone stays chat', reduce(initialState(), { kind: 'user_text', text: 'open chrome' })
  && reduce(run([{ kind: 'user_text', text: 'open chrome' }]), { kind: 'delta', text: 'Sure' }).mode, 'chat');
check('O2 pet only after tool frame', ordered.mode, 'pet');

/* ───────────────────────────────────────────────────────────────────────── */
console.log('\n' + passed + ' passed, ' + failures.length + ' failed');
if (failures.length) {
  console.error('\nFAILURES:\n' + failures.map((f) => '  - ' + f).join('\n'));
  process.exit(1);
}
