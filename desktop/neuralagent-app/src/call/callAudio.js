/**
 * Hands — call audio on the loop (client side renderer).
 *
 * Two legs, one crisp boundary:
 *   IN  (far party -> user ear): call_audio frames from the lane SSE.
 *       - format "queue:say": line of text the sim provides; rendered with the
 *         local TTS voice at a DIFFERENT pitch/rate than Hands so "them" is
 *         audibly a person on the phone, not the persona.
 *       - format "mulaw:8000": base64 G.711 mu-law — the EXACT frames a real
 *         Twilio media stream sends. Decoded via WebAudio into a buffer and
 *         played through an AudioBufferSourceNode (realtime, gapless per line).
 *   TONES (dialing texture -> user ear only): call_tone frames synth-rendered
 *       with oscillators (dial DTMF-ish cadence, ringback 440+480 1s/2s, busy
 *       0.5s/0.5s, static = filtered noise burst). These exist so the user
 *       hears line static + dialing before connect, exactly like a real
 *       handset — they NEVER touch the call.
 *
 * HARD RULE (product): the user's microphone is NOT reachable from this module.
 * No getUserMedia here, no inputs at all. Steering is text POSTs on the lane
 * control endpoint (and x-sawii-steer on the persona turn) — the far party can
 * only ever hear what provider.speak()/Hands' TTS deliberately sends.
 *
 * audioMode toggle (UI-local): 'audio' plays the legs above; 'transcript'
 * silences BOTH far-end audio and tones and the UI shows live text instead.
 * Same frames either way — the backend never changes for the swap.
 */

(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(root);
  else root.HandsCallAudio = factory(root);
}(globalThis, function (root) {
  'use strict';

  // Linear G.711 mu-law expansion (decoder only — we never encode here).
  // Canonical Sun/BellCore formula: sample = ((2*m + 33) << e) - 33, sign
  // inverted vs the complemented code byte.
  function ulawExp(b) {
    var c = (~b) & 0xff;
    var sign = c & 0x80;
    var e = (c >> 4) & 0x07;
    var m = c & 0x0f;
    var v = ((2 * m + 33) << e) - 33;
    return sign ? v : -v;
  }

  function createCallAudio(options) {
    options = options || {};
    var TTST = (typeof speechSynthesis !== 'undefined');
    var audioCtx = null;
    var master = null;
    var mode = options.mode || 'audio';          // 'audio' | 'transcript'
    var muted = false;                            // HOLD kills far-end playback
    var currentTts = null;
    var speakingFar = false;
    var toneNodes = [];

    function ctx() {
      if (typeof AudioContext === 'undefined' && typeof root.webkitAudioContext === 'undefined') return null;
      if (!audioCtx) {
        var AC = typeof AudioContext !== 'undefined' ? AudioContext : root.webkitAudioContext;
        audioCtx = new AC();
        master = audioCtx.createGain();
        master.gain.value = options.volume == null ? 0.9 : options.volume;
        master.connect(audioCtx.destination);
      }
      if (audioCtx.state === 'suspended') { try { audioCtx.resume(); } catch (e) {} }
      return audioCtx;
    }

    function stopAll() {
      toneNodes.forEach(function (n) { try { n.stop(); } catch (e) {} });
      toneNodes = [];
      if (TTST) { try { speechSynthesis.cancel(); } catch (e) {} }
      speakingFar = false;
    }

    // ── tones: synthesized for the USER's ear only ─────────────────────────
    var TONE_FREQS = {
      dial: [350, 440], ringback: [440, 480], busy: [480, 620], static: null,
    };
    var TONE_CADENCE = {
      dial: { on: 0.09, off: 0.16 }, ringback: { on: 1.0, off: 2.0 }, busy: { on: 0.5, off: 0.5 },
    };

    function playTone(frame) {
      if (mode !== 'audio' || muted) return;
      var ac = ctx();
      if (!ac) return;
      var dur = Math.max(0.15, Math.min(6, frame.dur_s || 1));
      var t0 = ac.currentTime;
      if (frame.tone === 'static') {
        var len = Math.floor(ac.sampleRate * 0.3);
        var buf = ac.createBuffer(1, len, ac.sampleRate);
        var d = buf.getChannelData(0);
        for (var i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * 0.18;
        var src = ac.createBufferSource(); src.buffer = buf;
        var hp = ac.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 1200;
        src.connect(hp); hp.connect(master); src.start(t0);
        return;
      }
      var freqs = TONE_FREQS[frame.tone] || [440];
      var cad = frame.cadence || TONE_CADENCE[frame.tone] || { on: dur, off: 0 };
      var cycOn = Math.max(0.03, cad.on_s != null ? cad.on_s : cad.on);
      var cycOff = Math.max(0, cad.off_s != null ? cad.off_s : cad.off);
      var cycle = cycOn + cycOff || 1;
      var cycles = Math.max(1, Math.round(dur / cycle));
      for (var c2 = 0; c2 < cycles; c2++) {
        var start = t0 + c2 * cycle;
        freqs.forEach(function (f) {
          var oscNode = ac.createOscillator();
          oscNode.type = 'sine'; oscNode.frequency.value = f;
          var g = ac.createGain();
          g.gain.setValueAtTime(0, start);
          g.gain.linearRampToValueAtTime(0.22, start + 0.015);
          g.gain.setValueAtTime(0.22, start + cycOn - 0.015);
          g.gain.linearRampToValueAtTime(0.0001, start + cycOn);
          oscNode.connect(g); g.connect(master);
          oscNode.start(start); oscNode.stop(start + cycOn + 0.02);
          toneNodes.push(oscNode);
        });
      }
      setTimeout(function () { toneNodes = []; }, (dur + 0.4) * 1000);
    }

    // ── far-end audio frames ────────────────────────────────────────────────
    function playQueueSay(frame) {
      if (mode !== 'audio' || muted) return;
      if (!TTST || !frame.text) return;
      try {
        if (currentTts) { try { speechSynthesis.cancel(); } catch (e) {} }
        var u = new SpeechSynthesisUtterance(frame.text);
        // Different voice colour than Hands (who uses rate 1.03 pitch 1.0):
        u.pitch = frame.speaker === 'hands' ? 0.72 : 0.85;
        u.rate = frame.speaker === 'hands' ? 1.0 : 0.94;
        speakingFar = true;
        currentTts = u;
        u.onend = function () { speakingFar = false; };
        u.onerror = function () { speakingFar = false; };
        speechSynthesis.speak(u);
      } catch (e) { /* cosmetic leg; transcript frame already showed the line */ }
    }

    function playMulaw(frame) {
      if (mode !== 'audio' || muted || !frame.audio_b64) return;
      var ac = ctx();
      if (!ac) return;
      try {
        var bin = atob(frame.audio_b64);
        var n = bin.length;
        var buf = ac.createBuffer(1, Math.max(1, n), 8000);
        var d = buf.getChannelData(0);
        for (var i = 0; i < n; i++) d[i] = ulawExp(bin.charCodeAt(i) & 0xff) / 32768;
        var src = ac.createBufferSource(); src.buffer = buf;
        src.connect(master);
        src.start(ac.currentTime + 0.001);
        toneNodes.push(src);
      } catch (e) { /* keep the lane alive */ }
    }

    function handleAudioFrame(frame) {
      if (frame.format === 'mulaw:8000') return playMulaw(frame);
      return playQueueSay(frame);
    }

    var api = {
      /** One raw lane frame from the call SSE. Synchronous, cheap, never throws up. */
      feed: function (frame) {
        try {
          if (!frame) return;
          if (frame.kind === 'call_tone') playTone(frame);
          else if (frame.kind === 'call_audio') handleAudioFrame(frame);
        } catch (e) { /* audio is cosmetic; the transcript rail is truth */ }
      },
      getMode: function () { return mode; },
      setMode: function (m) {
        mode = m === 'transcript' ? 'transcript' : 'audio';
        if (mode === 'transcript') stopAll();
      },
      setMuted: function (m) { muted = !!m; if (muted) stopAll(); },
      stop: stopAll,
      supportsAudio: function () {
        return typeof AudioContext !== 'undefined' || typeof root.webkitAudioContext !== 'undefined';
      },
    };
    return api;
  }

  return { createCallAudio: createCallAudio, ulawExpand: ulawExp };
}));
