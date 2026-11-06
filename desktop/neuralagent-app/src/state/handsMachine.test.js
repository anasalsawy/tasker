/**
 * Golden paths for the Hands UI state machine.
 *
 * Path A — plain chat ('hi') NEVER collapses into the execution pet.
 * Path B — a real task (lane / tool_call / delegated frames) DOES enter the pet
 *          and tracks active lanes + progress.
 *
 * The reducer is pure CommonJS (state/handsMachine.js), so this runs under
 * `react-scripts test` and also under the plain-node runner in
 * scripts/test_hands_machine.mjs without any DOM or React.
 */
const machine = require('./handsMachine');

const { initialState, reduce } = machine;

function run(events, state) {
  return events.reduce((acc, ev) => reduce(acc, ev), state || initialState());
}

describe('Hands state machine', () => {
  describe('golden path A: "hi" stays chat', () => {
    test('idle bar is the default state', () => {
      expect(initialState().mode).toBe('bar');
      expect(initialState().lanes).toEqual({});
    });

    test('typing or speaking "hi" enters chat, never pet', () => {
      const s = run([
        { kind: 'user_text', text: 'hi' },
        { kind: 'delta', text: 'Hey ' },
        { kind: 'delta', text: 'there!' },
        { kind: 'turn_done', text: 'Hey there!' },
      ]);
      expect(s.mode).toBe('chat');
      expect(s.laneOrder).toHaveLength(0);
      expect(s.toolsTotal).toBe(0);
      expect(s.chat.map((m) => m.text)).toEqual(['hi', 'Hey there!']);
    });

    test('a chat reply from the classifier keeps the surface in chat', () => {
      const s = run([{ kind: 'user_text', text: 'how are you' },
                     { kind: 'chat_reply', text: 'Good — what should we do?' }]);
      expect(s.mode).toBe('chat');
      expect(machine.selectIsShimmering(s)).toBe(false);
      expect(machine.selectStatusLine(s)).toBeNull();
    });

    test('pet is sticky once real work started: chat after a tool still shows pet', () => {
      const s = run([
        { kind: 'tool_call', id: 'call_ln0000abcd_1', name: 'click', arguments: '{}' },
        { kind: 'user_text', text: 'thanks' },
      ]);
      expect(s.mode).toBe('pet');
    });

    test('collapse returns to the slim idle bar', () => {
      const s = run([{ kind: 'user_text', text: 'hi' }, { kind: 'collapse' }]);
      expect(s.mode).toBe('bar');
    });
  });

  describe('golden path B: a task collapses into the pet', () => {
    test('a single tool_call is the post-hoc task gate', () => {
      const s = run([
        { kind: 'user_text', text: 'open chrome and save the brief' },
        { kind: 'delta', text: 'On it. ' },
        { kind: 'tool_call', id: 'call_ln1111aaaa_1', name: 'open_app', arguments: '{"app_name":"Chrome"}' },
      ]);
      expect(s.mode).toBe('pet');
      expect(s.currentTool).toBe('open_app');
      expect(s.toolsTotal).toBe(1);
      expect(machine.selectActiveLaneCount(s)).toBe(1);
      expect(s.taskTitle).toBe('open chrome and save the brief');
      expect(machine.selectStatusLine(s)).toContain('1 lane live');
      expect(machine.selectIsShimmering(s)).toBe(true);
      // Chat kept flowing the whole time — the reply was not gated on recognition.
      expect(s.chat.some((m) => m.role === 'hands')).toBe(true);
    });

    test('lane frames across lanes track N active lanes', () => {
      const s = run([
        { kind: 'lane', event: { lane: 'ln-a', type: 'beat' } },
        { kind: 'lane', event: { lane: 'ln-b', type: 'beat' } },
        { kind: 'lane_tool', name: 'read_file', lane: 'ln-a' },
        { kind: 'lane_tool', name: 'write_file', lane: 'ln-b' },
      ]);
      expect(s.mode).toBe('pet');
      expect(machine.selectLanes(s).map((l) => l.id)).toEqual(['ln-a', 'ln-b']);
      expect(machine.selectActiveLaneCount(s)).toBe(2);
      expect(machine.selectStatusLine(s)).toContain('2 lanes live');
    });

    test('delegated frames enter the pet with no lanes yet', () => {
      const s = run([
        { kind: 'user_text', text: 'do the whole refund thing' },
        { kind: 'chat_reply', text: 'Delegating that now.' },
        { kind: 'delegated' },
      ]);
      expect(s.mode).toBe('pet');
      expect(s.delegated).toBe(true);
      expect(s.laneOrder).toHaveLength(0);
      expect(machine.selectStatusLine(s)).toBe('Planning…');
    });

    test('tool_result completes lanes, advances progress, and ends the task', () => {
      let s = run([
        { kind: 'tool_call', id: 'call_ln2222bbbb_1', name: 'click' },
        { kind: 'tool_call', id: 'call_ln2222bbbb_2', name: 'type' },
      ]);
      s = reduce(s, { kind: 'tool_result', tool_call_id: 'call_ln2222bbbb_1', status: 'ok' });
      expect(machine.selectProgress(s)).toBeCloseTo(0.5);
      s = reduce(s, { kind: 'tool_result', tool_call_id: 'call_ln2222bbbb_2', status: 'error' });
      expect(s.toolsError).toBe(1);
      expect(machine.selectActiveLaneCount(s)).toBe(0);
      expect(machine.selectIsShimmering(s)).toBe(false);
      s = reduce(s, { kind: 'task_finished' });
      expect(s.mode).toBe('chat');
      expect(s.currentTool).toBeNull();
    });

    test('lane id is derived from the call id prefix', () => {
      expect(machine.laneFromCallId('call_ln3ff9a1b2_9')).toBe('ln3ff9a1b2');
      const s = reduce(initialState(), { kind: 'tool_call', id: 'call_ln44aa55bb_1', name: 'scroll' });
      expect(machine.selectLanes(s).map((l) => l.id)).toEqual(['ln44aa55bb']);
    });

    test('legacy desktop-agent activity is also a post-hoc task signal', () => {
      const s = run([
        { kind: 'user_text', text: 'clean my downloads folder' },
        { kind: 'agent_activity', action: 'click', message: 'Clicking Sort by date' },
      ]);
      expect(s.mode).toBe('pet');
      expect(s.currentTool).toBe('click');
      expect(machine.selectActiveLaneCount(s)).toBe(1);
      const done = reduce(s, { kind: 'agent_exit' });
      expect(done.mode).toBe('chat');
    });

    test('unknown events are inert (the reducer never throws on noise)', () => {
      const base = initialState();
      expect(reduce(base, null)).toBe(base);
      expect(reduce(base, {})).toBe(base);
      expect(reduce(base, { kind: 'what_is_this' })).toBe(base);
    });
  });
});
