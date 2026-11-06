/**
 * End-to-end fake-call harness for the Hands UI machine (plain node ESM).
 *
 * Replays the exact SSE frame shapes utils/call_lane.py stamps, so the whole
 * product loop is proven offline:
 *   affirmation (delta) -> dialing tones (call_tone) -> connected
 *   -> live transcript/audio frames -> mid-call STEER (speaker 'me'
 *   model-only; the user mic never becomes call audio) -> ended.
 *
 * Task gating must hold: plain chat never collapses the pet; ONE call frame does.
 * Run: node scripts/test_call_flow.mjs   (exit 0 = green, exit 1 = first failure)
 */
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const M = require(path.join(here, '..', 'src', 'state', 'handsMachine.js'));
const { initialState, reduce } = M;

function run(events, state) {
  return events.reduce(function (acc, ev) { return reduce(acc, ev); }, state || initialState());
}
function check(label, cond, got) {
  if (cond) { console.log('PASS: ' + label); return; }
  console.log('FAIL: ' + label + ' -> got ' + JSON.stringify(got));
  process.exit(1);
}

// 1. affirmation is plain chat -> NO collapse yet (task-gated UI rule)
let s = run([
  { kind: 'user_text', text: 'call Marcy and confirm tomorrow 9am' },
  { kind: 'delta', text: 'Calling Marcy now \u2014 I\u2019ll keep talking while it dials. ' },
]);
check('affirmation stays chat (never pets pre-task)', s.mode === 'chat', s.mode);

// 2. lane frames exactly as call_lane.py stamps them, in order
const CID = 'call_ln1111aaaa_c2_81';   // exactly what open_call_lane() builds
const LANE = 'ln1111aaaa';
const F = function (kind, seq, data) {
  return { kind: 'call_event', callKind: kind,
    event: Object.assign({ call_id: CID, lane: LANE, seq: seq, ts: 0 }, data) };
};

// dialing -> line static -> dial cadence -> ringing + ringback -> connected
s = run([
  F('call_status', 1, { state: 'dialing', to: '+15551234567' }),
  F('call_tone', 2, { tone: 'static', freqs: [], dur_s: 0.35, heard_by: 'user_only' }),
  F('call_tone', 3, { tone: 'dial', freqs: [350, 440], dur_s: 0.75, heard_by: 'user_only' }),
  F('call_status', 4, { state: 'ringing' }),
  F('call_tone', 5, { tone: 'ringback', freqs: [440, 480], dur_s: 4, heard_by: 'user_only' }),
  F('call_status', 6, { state: 'connected' }),
], s);

check('first call frame collapses the pet POST-HOC', s.mode === 'pet', s.mode);
check('call registered under its lane id', s.callOrder[0] === CID, s.callOrder);
const call = s.calls[CID];
check('call state = connected', call.state === 'connected', call.state);
check('tone count = 3 (static/dial/ringback)', call.tones === 3, call.tones);
check('lane chip mirrors the call', s.lanes[LANE].status === 'running' && /call/.test(s.lanes[LANE].label), s.lanes[LANE]);
check('active lane count includes the call', M.selectActiveLaneCount(s) === 1, M.selectActiveLaneCount(s));
check('call label carries state + number', M.selectCallLabel(s) === 'On call \u00b7 +15551234567', M.selectCallLabel(s));
check('still talking in chat while the call runs (L stays free)', s.chat.some(function (m) { return m.role === 'hands'; }), s.chat.length);

// ── 3. far-end speech: transcript + audio legs (client renders one, or the other)
s = run([
  F('call_transcript', 7, { speaker: 'them', text: 'Hello, this is Marcy speaking.' }),
  F('call_audio', 8, { speaker: 'them', format: 'queue:say', text: 'Hello, this is Marcy speaking.', duration_s: 1.6 }),
  F('call_transcript', 9, { speaker: 'hands', text: 'Hi Marcy, Hands calling for Ana about tomorrow at nine.' }),
  F('call_audio', 10, { speaker: 'hands', format: 'queue:say', text: 'Hi Marcy, Hands calling for Ana about tomorrow at nine.', duration_s: 2.1 }),
], s);
check('transcript rail captured', s.calls[CID].transcript.length === 2, s.calls[CID].transcript);
check('last seq stamped', s.calls[CID].seq === 10, s.calls[CID].seq);

// audio <-> transcript toggle is UI-local routing only (events keep flowing)
s = reduce(s, { kind: 'call_audio_mode', mode: 'transcript', call_id: CID });
check('toggle swaps to transcript mode', s.calls[CID].audioMode === 'transcript', s.calls[CID].audioMode);
s = reduce(s, { kind: 'call_audio_mode', mode: 'audio', call_id: CID });
check('toggle swaps back to live audio', s.calls[CID].audioMode === 'audio', s.calls[CID].audioMode);

// ── 4. STEER mid-call: user utterance -> control POST (TEXT ONLY).
//    The backend stamps speaker:'me' ONCE (utils/call_lane.py control('steer'));
//    the UI never injects a duplicate. Nothing here is an audio frame, so the
//    far party never hears the user — the mic->call path simply does not exist.
s = run([
  F('call_transcript', 11, { speaker: 'me', text: 'ask about the afternoon too' }),
  F('call_transcript', 12, { speaker: 'hands', text: 'One moment \u2014 ask about the afternoon too.' }),
  F('call_audio', 13, { speaker: 'hands', format: 'queue:say', text: 'One moment \u2014 ask about the afternoon too.', duration_s: 1.8 }),
], s);
const tr = s.calls[CID].transcript;
check('steer echoes ONCE as speaker me (model side only)', tr.filter(function (r) { return r.speaker === 'me'; }).length === 1, tr);
check('audio legs never append transcript rows (call_audio is output-only)', tr.filter(function (r) { return r.text === 'ask about the afternoon too'; }).length === 1, tr);
check('hands acked the steer aloud', /One moment/.test(tr[tr.length - 1].text), tr.slice(-2));
check('call still live after steering', M.selectActiveCall(s) !== null, s.currentCall);
check('status line still one live call', /^call On call/.test(M.selectStatusLine(s)), M.selectStatusLine(s));

// ── 5. HOLD mutes the far leg, resume restores, then the call ENDS ─────────
s = run([F('call_status', 14, { state: 'held' })], s);
check('held state maps lane chip to held', s.lanes[LANE].status === 'held', s.lanes[LANE].status);
s = run([F('call_status', 15, { state: 'unheld' })], s);
check('unheld returns the lane to running', s.lanes[LANE].status === 'running', s.lanes[LANE].status);
s = run([F('call_status', 16, { state: 'ended', reason: 'remote_hangup' })], s);
check('ended call leaves the active set', M.selectActiveCall(s) === null, M.selectActiveCall(s));
check('ended call marks its lane done', s.lanes[LANE].status === 'done', s.lanes[LANE].status);
check('call label reads ended', M.selectCallLabel(s) === 'Call ended \u00b7 +15551234567', M.selectCallLabel(s));

console.log('ALL PASS - fake call end-to-end (affirmation -> tones -> connected -> transcript swap -> steer mid-call -> ended)');
