/**
 * handsBus — tiny pub/sub so the sidebar listview can show live run titles
 * while a Thread page owns the state machine. Decoupled from React to stay
 * importable from plain node scripts and to keep zero-cost fan-out.
 */
const listeners = new Set();

export function publishHandsStatus(status) {
  listeners.forEach(function (fn) {
    try { fn(status); } catch (e) { /* one bad listener must not break the lane */ }
  });
}

export function subscribeHandsStatus(fn) {
  listeners.add(fn);
  return function () { listeners.delete(fn); };
}
