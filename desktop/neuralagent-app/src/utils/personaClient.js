/**
 * Hands — DL-Companion persona stream client.
 *
 * POST {PERSONA_URL}/{tid}/act  (backend: routers/aiagent/persona_orchestrator.py)
 * SSE frames: `event: delta|lane|lane_tool|tool_call|tool_result|delegated|done|error`
 * then `data: {json}`.
 *
 * GET  {PERSONA_URL}/{tid}/calls/{cid}/stream — voice-call lane events
 * (frames: call_status|call_tone|call_transcript|call_audio) plus POST
 * …/calls/{cid}/control {action: speak|hold|unhold|steer|hangup, text}.
 *
 * Uses fetch + ReadableStream (EventSource cannot POST). Hand-rolled parser,
 * nothing heavy. Events are pushed to `onEvent` synchronously as they arrive so
 * the reducer can decide task-vs-chat POST-hOC — this module never awaits UI
 * work and the UI never awaits this module before speaking/typing.
 */

async function streamPersonaAct(baseUrl, tid, accessToken, payload, onEvent, signal) {
  const url = baseUrl.replace(/\/+$/, '') + '/' + encodeURIComponent(tid) + '/act';
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + accessToken,
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify(Object.assign({
      text: '', tool_results: [], timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    }, payload || {})),
    signal: signal || undefined,
  });
  if (!resp.ok || !resp.body) {
    let msg = 'Persona stream failed (' + resp.status + ')';
    try { msg = (await resp.json()).message || msg; } catch (e) { /* keep default */ }
    onEvent({ event: 'error', data: { message: msg } });
    return;
  }
  // Verification/ingestion hooks (history persistence etc.) belong to the caller
  // as fire-and-forget; this loop only parses frames and forwards them.
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let current = { event: 'message', data: '' };
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, idx).replace(/\r$/, '');
      buffer = buffer.slice(idx + 1);
      if (line === '') {
        if (current.data) {
          let parsed = null;
          try { parsed = JSON.parse(current.data); } catch (e) { parsed = { raw: current.data }; }
          try { onEvent({ event: current.event, data: parsed }); } catch (err) { /* UI must never kill the stream */ }
        }
        current = { event: 'message', data: '' };
      } else if (line.startsWith('event:')) {
        current.event = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        current.data += (current.data ? '\n' : '') + line.slice(5).trim();
      }
    }
  }
}

/**
 * Subscribe to one call lane's SSE stream (voice phone calls).
 * Reuses the exact frame parser above; onEvent frames are
 * { event: 'call_status'|'call_tone'|'call_transcript'|'call_audio', data }.
 * Resolves when the stream ends (server closed after 'ended' or abort).
 */
async function streamCallEvents(tid, callId, accessToken, onEvent, signal, baseUrl) {
  const url = (baseUrl || '').replace(/\/act\s*$/, '')
    + '/' + encodeURIComponent(tid) + '/calls/' + encodeURIComponent(callId) + '/stream';
  const resp = await fetch(url, {
    method: 'GET',
    headers: { 'Authorization': 'Bearer ' + accessToken, 'Accept': 'text/event-stream' },
    signal: signal || undefined,
  });
  if (!resp.ok || !resp.body) {
    let msg = 'Call stream failed (' + resp.status + ')';
    try { msg = (await resp.json()).message || msg; } catch (e) { /* keep default */ }
    onEvent({ event: 'call_error', data: { message: msg, call_id: callId } });
    return;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let current = { event: 'message', data: '' };
  const flush = function () {
    if (!current.data) { current = { event: 'message', data: '' }; return; }
    let parsed = null;
    try { parsed = JSON.parse(current.data); } catch (e) { parsed = { raw: current.data }; }
    try { onEvent({ event: current.event, data: parsed }); } catch (err) { /* UI never kills the stream */ }
    current = { event: 'message', data: '' };
  };
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, idx).replace(/\r$/, '');
      buffer = buffer.slice(idx + 1);
      if (line === '') { flush(); }
      else if (line.startsWith('event:')) { current.event = line.slice(6).trim(); }
      else if (line.startsWith('data:')) { current.data += (current.data ? '\n' : '') + line.slice(5).trim(); }
      // comment lines (": keepalive") are ignored
    }
  }
  flush();
}

/** POST a control action onto a live call. Fire-and-forget friendly. */
async function callControl(tid, callId, accessToken, action, text, baseUrl) {
  const url = (baseUrl || '').replace(/\/act\s*$/, '')
    + '/' + encodeURIComponent(tid) + '/calls/' + encodeURIComponent(callId) + '/control';
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + accessToken },
    body: JSON.stringify({ action: action, text: text || '' }),
  });
  if (!resp.ok) {
    let msg = 'Call control failed (' + resp.status + ')';
    try { msg = (await resp.json()).message || msg; } catch (e) { /* keep */ }
    throw new Error(msg);
  }
  return resp.json();
}

export { streamCallEvents, callControl };
export default streamPersonaAct;
