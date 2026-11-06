/**
 * Hands state machine golden-path harness (plain node ESM, zero deps).
 * The reducer is pure CommonJS: createRequire loads it directly, no transform.
 * Run: node scripts/test_hands_machine.mjs   (exit 0 = green, exit 1 = first failure)
 */
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const M = require(path.join(here, '..', 'src', 'state', 'handsMachine.js'));

const { initialState, reduce, laneFromCallId, selectStatusLine, selectIsShimmering } = M;

function run(events) {
  return events.reduce(function (acc, ev) { return reduce(acc, ev); }, initialState());
}

function check(label, cond, got) {
  if (cond) {
    console.log('PASS: ' + label);
    return;
  }
  console.log('FAIL: ' + label + ' -> got ' + JSON.stringify(got));
  process.exit(1);
}
// 1 - idle starts as the slim bar
check('initialState mode === bar', initialState().mode === 'bar', initialState().mode);

// 2 - plain chat NEVER enters pet: user_text + deltas stay bar/chat
const chatOnly = run([
  { kind: 'user_text', text: 'hi there' },
  { kind: 'delta', text: 'Hey! ' },
  { kind: 'delta', text: 'What can I do for you?' },
]);
check('user_text + deltas stay != pet', chatOnly.mode !== 'pet', chatOnly.mode);
check('chat path lands in chat', chatOnly.mode === 'chat', chatOnly.mode);
check('chat path spawns no lanes', chatOnly.laneOrder.length === 0, chatOnly.laneOrder);
check('chat path counts no tools', chatOnly.toolsTotal === 0, chatOnly.toolsTotal);
check('statusLine null outside pet', selectStatusLine(chatOnly) === null, selectStatusLine(chatOnly));
check('no shimmer on plain chat', selectIsShimmering(chatOnly) === false, selectIsShimmering(chatOnly));

// 3 - a real tool_call POST-HOC gates the pet; lane parses from the call id
const toolS = run([
  { kind: 'user_text', text: 'open chrome and save the brief' },
  { kind: 'delta', text: 'On it. ' },
  { kind: 'tool_call', id: 'call_lndeadbeef_123456', name: 'open_app', arguments: '{"app_name":"Chrome"}' },
]);
check('tool_call call_lndeadbeef_123456 enters pet', toolS.mode === 'pet', toolS.mode);
check('lane lndeadbeef parsed from call id', laneFromCallId('call_lndeadbeef_123456') === 'lndeadbeef', laneFromCallId('call_lndeadbeef_123456'));
check('tool_call created that lane', toolS.laneOrder.indexOf('lndeadbeef') >= 0, toolS.laneOrder);

// 4 - delegated enters pet, task_finished leaves pet for chat
const delS = reduce(initialState(), { kind: 'delegated' });
check('delegated enters pet', delS.mode === 'pet', delS.mode);
const finS = reduce(delS, { kind: 'task_finished' });
check('task_finished leaves pet to chat', finS.mode === 'chat', finS.mode);

// 5 - selectStatusLine renders only in pet
check('statusLine non-null in pet', typeof selectStatusLine(delS) === 'string' && selectStatusLine(delS).length > 0, selectStatusLine(delS));
check('statusLine null in bar', selectStatusLine(initialState()) === null, selectStatusLine(initialState()));

// 6 - shimmer: rail pulses while a tool is outstanding, stills once every
//     call resolves (toolsDone >= toolsTotal and no active lanes)
const shA = reduce(initialState(), { kind: 'tool_call', id: 'call_lncafe0001_1', name: 'click', arguments: '{}' });
check('shimmer true during tool', selectIsShimmering(shA) === true, selectIsShimmering(shA));
check('shimmer tracks toolsDone < toolsTotal', shA.toolsDone === 0 && shA.toolsTotal === 1, [shA.toolsDone, shA.toolsTotal]);
const shB = reduce(shA, { kind: 'tool_result', tool_call_id: 'call_lncafe0001_1', status: 'ok' });
check('toolsDone >= toolsTotal after result', shB.toolsDone >= shB.toolsTotal, [shB.toolsDone, shB.toolsTotal]);
check('shimmer false after result settles', selectIsShimmering(shB) === false, selectIsShimmering(shB));

console.log('ALL PASS - hands machine golden paths verified');
