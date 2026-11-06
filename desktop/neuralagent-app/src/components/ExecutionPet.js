import React, { useState } from 'react';
import { FiActivity, FiSquare, FiRadio, FiPhone, FiPhoneOff, FiPhoneIncoming, FiVolume2, FiType, FiMic, FiPause, FiPlayCircle } from 'react-icons/fi';
import machine from '../state/handsMachine';

/**
 * ExecutionPet — the collapsed execution surface. Compact by construction:
 * a slim pill/bar that never obscures the user's screen. It shows:
 *   - N lanes active            (speed as the selling point)
 *   - current tool being run    (monospace accent)
 *   - a shimmer progress rail   (fed by tool_call/tool_result counts)
 *   - a call strip when this lane is a phone call (state + HOLD/TALK +
 *     audio<->transcript toggle) — same reducer, same event kinds.
 * Fed purely by the state machine; render is dumb + cheap.
 */
export default function ExecutionPet({ state, onStop, compact, call }) {
  const lanes = machine.selectLanes(state);
  const active = machine.selectActiveLaneCount(state);
  const progress = machine.selectProgress(state);
  const shimmer = machine.selectIsShimmering(state);
  const statusLine = machine.selectStatusLine(state);
  const activeCall = machine.selectActiveCall(state);
  // A pet with a live call lane also hosts the call surface logic.
  if (activeCall && call) {
    return <CallPet state={state} call={call} activeCall={activeCall} onStop={onStop} compact={compact} />;
  }

  return (
    <div className={'hands-pet ' + (compact ? 'hands-pet-compact ' : '') + (shimmer ? 'is-shimmering' : '')}
         role="status" aria-live="polite" aria-label="Hands execution status">
      <span className={'hands-pet-orb ' + (shimmer ? 'is-active' : 'is-idle')} aria-hidden="true">
        <FiActivity />
      </span>
      <div className="hands-pet-copy">
        <span className="hands-pet-title">{state.taskTitle || 'Hands'}</span>
        <span className="hands-pet-line">{statusLine}</span>
      </div>
      <div className="hands-pet-lanes" aria-hidden={compact}>
        {lanes.slice(0, 4).map(function (lane) {
          return <span key={lane.id} className={'hands-lane is-' + lane.status} title={lane.id + ' ' + (lane.label || '')}>
            <i />{lane.label || lane.id}
          </span>;
        })}
        {lanes.length > 4 && <span className="hands-lane is-more">+{lanes.length - 4}</span>}
      </div>
      <div className="hands-pet-progress" aria-hidden="true">
        <span className="hands-pet-progress-fill" style={{ width: Math.round(progress * 100) + '%' }} />
      </div>
      {!compact && onStop && active > 0 && (
        <button className="hands-pet-stop" onClick={onStop} aria-label="Stop execution" title="Stop execution">
          <FiSquare />
        </button>
      )}
    </div>
  );
}

/**
 * CallPet — the execution pet while one of the lanes is a phone call.
 * Same visuals as the plain pet (orb, shimmer, lane chips, progress rail),
 * plus a live call strip: state word, last transcript line (or the live
 * transcript rail when the toggle is on), HOLD/TALK mic-style control row
 * and the audio <-> transcript toggle. `call` is useHands().callApi.
 */
export function CallPet({ state, call, activeCall, onStop, compact }) {
  const [talking, setTalking] = useState(false);
  const lanes = machine.selectLanes(state);
  const progress = machine.selectProgress(state);
  const shimmer = machine.selectIsShimmering(state);
  const statusLine = machine.selectStatusLine(state);
  const transcriptMode = activeCall.audioMode === 'transcript';
  const held = activeCall.state === 'held';
  const ended = activeCall.state === 'ended' || activeCall.state === 'failed';
  const last = (activeCall.transcript || []).slice(-1)[0];

  const toggleAudio = function () {
    call && call.setAudioMode(transcriptMode ? 'audio' : 'transcript', activeCall.call_id);
  };
  const toggleHold = function () {
    if (!call) return;
    (held ? call.unhold(activeCall.call_id) : call.hold(activeCall.call_id)).catch(function () {});
  };
  // TALK: user's next utterance routes to callApi.steer — the model hears it,
  // the far party never does. The host wires recognition through onTalkChange.
  const toggleTalk = function () {
    const next = !talking;
    setTalking(next);
    if (call && call.onTalkChange) call.onTalkChange(activeCall.call_id, next);
  };

  return (
    <div className={'hands-pet hands-pet-call ' + (compact ? 'hands-pet-compact ' : '') + (shimmer ? 'is-shimmering' : '')}
         role="status" aria-live="polite" aria-label="Hands call status">
      <span className={'hands-pet-orb is-active ' + (ended ? 'is-ended' : '')} aria-hidden="true">
        {ended ? <FiPhoneOff /> : <FiPhone />}
      </span>
      <div className="hands-pet-copy">
        <span className="hands-pet-title">{machine.selectCallLabel(state) || 'Call'}</span>
        <span className="hands-pet-line">{statusLine}</span>
      </div>

      {transcriptMode && (
        <div className={'hands-call-transcript' + (compact ? ' is-compact' : '')} aria-label="Live call transcript">
          {(activeCall.transcript || []).slice(compact ? -1 : -3).map(function (row, i) {
            return <span key={i} className={'hands-call-line is-' + row.speaker}>
              <span className="hands-call-speaker">{row.speaker === 'me' ? 'you\u2192model' : row.speaker}</span>
              {row.text}
            </span>;
          })}
        </div>
      )}
      {!transcriptMode && last && (
        <div className="hands-call-caption" aria-hidden="true">{last.speaker === 'them' ? '"' + last.text + '"' : (last.speaker === 'me' ? '(you \u2192 model) ' : '') + last.text}</div>
      )}

      <div className="hands-pet-lanes" aria-hidden={compact}>
        {lanes.slice(0, 4).map(function (lane) {
          return <span key={lane.id} className={'hands-lane is-' + lane.status} title={lane.id + ' ' + (lane.label || '')}>
            <i />{lane.label || lane.id}
          </span>;
        })}
      </div>
      <div className="hands-pet-progress" aria-hidden="true">
        <span className="hands-pet-progress-fill" style={{ width: Math.round(progress * 100) + '%' }} />
      </div>

      {!ended && (
        <div className="hands-call-controls" role="group" aria-label="Call controls">
          <button className={'hands-call-btn ' + (held ? 'is-on' : '')} onClick={toggleHold}
                  aria-label={held ? 'Take off hold' : 'Hold the call'} title={held ? 'Resume' : 'Hold'}>
            {held ? <FiPlayCircle /> : <FiPause />}
          </button>
          <button className={'hands-call-btn ' + (talking ? 'is-on' : '')} onClick={toggleTalk}
                  aria-label="Talk to Hands (only the model hears you)" title="Steer Hands mid-call">
            <FiMic />
          </button>
          <button className="hands-call-btn" onClick={toggleAudio}
                  aria-label="Toggle call audio vs live transcript"
                  title={transcriptMode ? 'Live text on \u2014 tap to hear audio' : 'Call audio on \u2014 tap for live text'}>
            {transcriptMode ? <FiType /> : <FiVolume2 />}
          </button>
          <button className="hands-call-btn is-danger" onClick={function () { call && call.hangup(activeCall.call_id); }}
                  aria-label="End call" title="End call">
            <FiPhoneIncoming style={{ transform: 'rotate(135deg)' }} />
          </button>
        </div>
      )}
      {!compact && onStop && !ended && (
        <button className="hands-pet-stop" onClick={onStop} aria-label="Stop execution" title="Stop execution">
          <FiSquare />
        </button>
      )}
    </div>
  );
}

/** Slim idle bar — the default face of the product. Never obscures the screen. */
export function HandsBar({ onExpand, micLevel, listening, running, title }) {  return (
    <button className={'hands-bar ' + (running ? 'is-running' : '') + (listening ? 'is-listening' : '')}
            onClick={onExpand} aria-label={title || 'Open Hands'}>
      <span className={'hands-bar-orb ' + (running ? 'is-active' : '')} aria-hidden="true">
        <FiRadio />
      </span>
      <span className="hands-bar-name">{title || 'Hands'}</span>
      {listening && (
        <span className="hands-bar-mic" aria-hidden="true"
              style={{ transform: 'scale(' + (1 + Math.min(1, micLevel * 6)) + ')' }} />
      )}
    </button>
  );
}
