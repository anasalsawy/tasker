/**
 * Hands — always-open voice lane (hands-free by default).
 *
 * No push-to-talk per turn. The mic stays open continuously; we endpoint with a
 * small RMS energy gate implemented with WebAudio (no new deps — the project has
 * no VAD library). Finalized utterances are handed to `onUtterance(text)` which
 * MUST be called fire-and-forget: nothing in this module ever awaits the reply
 * path, the classifier, or any ingestion — voice send/receive latency stays on
 * the voice path only.
 *
 * Browser-global based (AudioContext, SpeechRecognition, speechSynthesis) so it
 * can be feature-detected and unit-imported in Node with guard flags.
 */

(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(root);
  else root.HandsVoice = factory(root);
}(globalThis, function (root) {
  'use strict';

  var SR = (typeof window !== 'undefined') &&
    (window.SpeechRecognition || window.webkitSpeechRecognition);

  function RMSVad(options) {
    this.threshold = options.threshold || 0.012;   // speech RMS gate (tuned for mic noise floors)
    this.hangoverMs = options.hangoverMs || 700;   // silence before endpoint
    this.minSpeechMs = options.minSpeechMs || 250; // ignore clicks shorter than this
    this.maxUtteranceMs = options.maxUtteranceMs || 20000;
    this.frameMs = 20;
    this.speaking = false;
    this._silenceSince = 0;
    this._speechSince = 0;
  }
  RMSVad.prototype.level = function (buf) {
    var sum = 0;
    for (var i = 0; i < buf.length; i += 3) { var v = buf[i]; sum += v * v; }
    return Math.sqrt(sum / (buf.length / 3 + 1));
  };
  RMSVad.prototype.feed = function (rms, nowMs) {
    if (rms >= this.threshold) {
      if (!this.speaking) { this.speaking = true; this._speechSince = nowMs; }
      this._silenceSince = nowMs;
      return null;
    }
    if (!this.speaking) return null;
    if (nowMs - this._silenceSince >= this.hangoverMs) {
      var dur = nowMs - this._speechSince;
      this.speaking = false;
      return dur >= this.minSpeechMs ? { ended: true, durationMs: dur } : { ended: true, tooShort: true };
    }
    return null;
  };

  function createVoiceLane(opts) {
    opts = opts || {};
    var listeners = { utterance: [], level: [], state: [] };
    var recognition = null;
    var audioCtx = null, analyser = null, micStream = null, rafId = null;
    var vad = new RMSVad(opts.vad || {});
    var handsFree = opts.handsFree !== false; // DEFAULT: continuous open channel
    var running = false;
    var interimBuf = '';
    var lastFinal = '';
    var lastFinalAt = 0;
    var ttsOn = opts.tts !== false;
    var speakingTts = false;
    var suppressUntil = 0;

    function emit(kind, payload) {
      (listeners[kind] || []).forEach(function (fn) { try { fn(payload); } catch (e) { /* never block voice */ } });
    }

    function supports() {
      return !!(SR && (typeof AudioContext !== 'undefined' || typeof webkitAudioContext !== 'undefined'));
    }

    function startTts(text) {
      if (!ttsOn || !text || typeof speechSynthesis === 'undefined') return;
      try {
        var u = new SpeechSynthesisUtterance(text);
        u.rate = 1.03; u.pitch = 1.0;
        speakingTts = true;
        // While Hands talks, duck the VAD so TTS bleed-through doesn't self-trigger.
        u.onstart = function () { suppressUntil = Date.now() + 90000; emit('state', { tts: true }); };
        u.onend = function () {
          speakingTts = false;
          suppressUntil = Date.now() + 450;
          emit('state', { tts: false });
        };
        u.onerror = function () { speakingTts = false; emit('state', { tts: false }); };
        speechSynthesis.speak(u);
      } catch (e) { /* TTS is cosmetic; never break the lane */ }
    }

    function stopTts() {
      try { if (typeof speechSynthesis !== 'undefined') speechSynthesis.cancel(); } catch (e) {}
      speakingTts = false;
    }

    function finalize(text) {
      var trimmed = (text || '').trim();
      if (!trimmed) return;
      var now = Date.now();
      // Dedup guard: SR sometimes repeats the last final transcript.
      if (trimmed === lastFinal && now - lastFinalAt < 2500) return;
      lastFinal = trimmed; lastFinalAt = now;
      interimBuf = '';
      // OFF the critical path: caller decides what to await — we never do.
      emit('utterance', { text: trimmed });
    }

    function startRecognition() {
      if (!SR || recognition) return;
      recognition = new SR();
      recognition.continuous = true;      // open channel, not push-to-talk
      recognition.interimResults = true;
      recognition.lang = opts.lang || 'en-US';
      recognition.onstart = function () { emit('state', { listening: true }); };
      recognition.onend = function () {
        emit('state', { listening: false });
        if (running && handsFree) {
          // Chrome stops recognition on its own after silences — reopen immediately.
          try { recognition.start(); } catch (e) { recognition = null; setTimeout(startRecognition, 400); }
        } else { recognition = null; }
      };
      recognition.onerror = function (ev) {
        emit('state', { error: ev.error || 'recognition' });
        if (ev.error === 'not-allowed' || ev.error === 'service-not-allowed') { running = false; recognition = null; }
      };
      recognition.onresult = function (ev) {
        if (Date.now() < suppressUntil && !handsFree) return;
        var finalText = '';
        for (var i = ev.resultIndex; i < ev.results.length; i++) {
          var r = ev.results[i];
          if (r.isFinal) finalText += r.transcript;
          else interimBuf += r.transcript;
        }
        emit('level', { interim: interimBuf });
        if (finalText.trim()) finalize(finalText);
      };
      try { recognition.start(); } catch (e) { recognition = null; }
    }

    async function ensureMic() {
      if (micStream) return true;
      if (typeof navigator === 'undefined' || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return false;
      micStream = await navigator.mediaDevices.getUserMedia({ audio: {
        echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      } });
      var AC = typeof AudioContext !== 'undefined' ? AudioContext : root.webkitAudioContext;
      audioCtx = new AC();
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      audioCtx.createMediaStreamSource(micStream).connect(analyser);
      var buf = new Uint8Array(analyser.fftSize);
      var tick = function () {
        if (!analyser) return;
        analyser.getByteTimeDomainData(buf);
        var rms = vad.level(buf);
        var act = vad.feed(rms, Date.now());
        if (act) emit('level', { rms: rms, vad: act });
        else emit('level', { rms: rms });
        rafId = requestAnimationFrame(tick);
      };
      tick();
      return true;
    }

    var api = {
      supports: supports,
      isHandsFree: function () { return handsFree; },
      setHandsFree: function (value) {
        handsFree = !!value;
        emit('state', { handsFree: handsFree });
        if (handsFree && running) startRecognition();
      },
      /** Open the channel forever (barring permission errors). Idempotent. */
      open: async function () {
        if (running) return true;
        var mic = await ensureMic().catch(function () { return false; });
        running = true;
        emit('state', { open: true, mic: !!mic });
        startRecognition();
        return running;
      },
      close: function () {
        running = false;
        stopTts();
        if (recognition) { try { recognition.stop(); } catch (e) {} recognition = null; }
        if (rafId) cancelAnimationFrame(rafId);
        rafId = null;
        if (micStream) { micStream.getTracks().forEach(function (t) { t.stop(); }); micStream = null; }
        if (audioCtx) { audioCtx.close().catch(function () {}); audioCtx = null; }
        analyser = null;
        emit('state', { open: false });
      },
      /** Interrupt Hands' own voice (barge-in) — clear TTS queue instantly. */
      interrupt: function () { stopTts(); },
      speak: startTts,
      on: function (kind, fn) { listeners[kind] = listeners[kind] || []; listeners[kind].push(fn); return function () { api.off(kind, fn); }; },
      off: function (kind, fn) { listeners[kind] = (listeners[kind] || []).filter(function (f) { return f !== fn; }); },
    };
    return api;
  }

  return { createVoiceLane: createVoiceLane, RMSVad: RMSVad };
}));
