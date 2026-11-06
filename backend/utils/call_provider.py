"""Telephony provider boundary for Hands voice calls + the offline SIMULATED provider.

Reality check (2026-11-06): neither this repo nor this machine carries ANY
telephony credential — no TWILIO_*/VONAGE_*/PLIVO_* in backend/.env or the
process env, no telephony SDK in either venv, and real Twilio Media Streams
also need a public HTTPS + WSS callback (this box sits behind NAT). So the
default provider is ``SimulatedCallProvider``: scripted dial tones + a fake
transcript + injected steer replies, which makes the FULL loop
(affirmation -> dialing tones -> connected -> live transcript -> steer mid-call
-> ended) testable offline, end to end.

Provider interface (CallProvider):

    attach(emit)         emitter: sync callable(event dict) — the lane stamps
                         call_id/lane/seq/ts and broadcasts
    start(handle)        place the call (async; must not block the turn)
    speak(text)          Hands -> far end: the TTS leg of the audio loop
    hold()/unhold()      mute/restore the far end
    steer(instruction)   USER voice -> model side ONLY. The far party never
                         hears the user's mic; nothing routes audio here.
    end(reason)          orchestrated hangup; far_hangup() on the other leg

Lane event schema — the exact dicts the SSE layer forwards (see
utils/call_lane.py and routers/aiagent/persona_orchestrator.py):

    {kind:"call_status",     state:"dialing"|"ringing"|"connected"|"held"|
                             "unheld"|"ended"|"failed", reason?}
    {kind:"call_tone",       tone:"static"|"dial"|"ringback"|"busy",
                             freqs:[Hz,...], cadence?:{on_s,off_s,pattern_s},
                             dur_s, heard_by:"user_only"}
    {kind:"call_transcript", speaker:"them"|"hands"|"me", text}
    {kind:"call_audio",      speaker:"them", format:"queue:say"|"mulaw:8000",
                             text?, audio_b64?, duration_s}

Audio-on-the-loop (product rule, enforced at this boundary):
  * Far-end speech reaches the user as realtime audio OR as transcript when the
    toggle is on — same event stream, the CLIENT decides which leg to render
    (audio "queue:say" rows synthesise with the local TTS voice in a different
    pitch than Hands; "mulaw:8000" rows decode G.711 frames — what a real
    Twilio stream sends).
  * Hands speech into the call = provider.speak() (TTS leg to the far side).
  * The user's mic NEVER enters the call: there is no audio path into a
    provider at all. Only steer() (text, model-side) and speak() content the
    model chose may ever sound on the call.

What a REAL Twilio media-stream call needs (stated loudly by
TwilioMediaStreamsProvider on construction so misconfig never silently degrades):
    1. Backend deps/creds: `twilio` SDK installed; TWILIO_ACCOUNT_SID,
       TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER in backend/.env; voice-enabled number.
    2. A public HTTPS webhook this server can answer:
       POST /call/twiml -> <Response><Dial><Number>{to}</Number></Dial> with
       <Connect><Stream url="wss://…/call/media"/></Connect>,StatusCallback;
       plus an inbound WebSocket route accepting twilio media-streams v1
       (events: connected/start/media/stop; media frames are base64 mulaw:8000).
    3. Up: twilio mulaw frames -> call_audio{speaker:"them",format:"mulaw:8000"};
       down: call_audio -> provider.write() into the live stream (Hands TTS PCM
       too — use an ultravoice/call-ready TTS with 8k mu-law output).
    4. STT of the far side (Twilio transcription add-on or Deepgram/AssemblyAI)
       -> call_transcript{speaker:"them"}; Hands-side LLM = the persona lane L
       (same mind), which steers via steer()/x-sawii-steer and speaks via speak().
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

Emitter = Callable[[dict[str, Any]], None]


@dataclass
class CallHandle:
    """Everything a provider needs to place one call."""
    call_id: str
    lane: str
    to: str
    frm: Optional[str] = None
    script: Optional[list[dict[str, Any]]] = None    # simulated only
    speed: float = 1.0                               # simulated time scale
    voice: str = ""                                  # reserved: TTS voice id


class CallProvider:
    """Duck-typed interface; ``name`` rides the start_call tool result."""

    name = "base"
    #: True => far audio arrives as mulaw media frames (a real media stream).
    supports_media_audio = False

    def __init__(self) -> None:
        self._emit: Emitter = lambda ev: None

    def attach(self, emit: Emitter) -> None:
        self._emit = emit

    async def start(self, handle: CallHandle) -> None:
        raise NotImplementedError

    async def speak(self, text: str) -> None:
        raise NotImplementedError

    def hold(self) -> None:
        pass

    def unhold(self) -> None:
        pass

    def steer(self, instruction: str) -> None:
        pass

    async def end(self, reason: str = "hangup") -> None:
        pass


# ── dial-tone helpers the client synth renders (no audio files needed) ────────
RINGBACK = {"tone": "ringback", "freqs": [440.0, 480.0],
            "cadence": {"on_s": 1.0, "off_s": 2.0, "pattern_s": 6.0},
            "dur_s": 4.0, "heard_by": "user_only"}
DIAL_EXPECTANT = {"tone": "dial", "freqs": [350.0, 440.0],
                  "cadence": {"on_s": 0.09, "off_s": 0.16, "pattern_s": 0.75},
                  "dur_s": 0.75, "heard_by": "user_only"}
LINE_STATIC = {"tone": "static", "freqs": [], "dur_s": 0.35,
               "heard_by": "user_only"}
BUSY = {"tone": "busy", "freqs": [480.0, 620.0],
        "cadence": {"on_s": 0.5, "off_s": 0.5, "pattern_s": 2.0},
        "dur_s": 2.0, "heard_by": "user_only"}


DEFAULT_SIM_SCRIPT: list[dict[str, str]] = [
    {"speaker": "them", "text": "Hello, this is Marcy speaking."},
    {"speaker": "hands", "text": "Hi Marcy, this is Hands calling for Ana about tomorrow's nine o'clock appointment, is that still on?"},
    {"speaker": "them", "text": "Let me check… yes, nine works. We'll hold the room."},
    {"speaker": "hands", "text": "Perfect — Ana will see you tomorrow at nine. Thank you, bye."},
]

STEER_ACK = "One moment — {short}."    # what Hands says aloud when steered
STEER_MODEL_NOTE = "[steered] {text}"  # note kept model-side


class SimulatedCallProvider(CallProvider):
    """Scripted call for offline testing.

    start(): dialing -> line static -> dial cadence -> ringing -> (patterned
    ringback) -> connected -> scripted them/hands lines spaced by pace_s.
    Each "them" line arrives BOTH as call_transcript and as call_audio
    (format queue:say) so the client can render audio OR transcript — exactly
    the two legs the UI toggle swaps between. steer() queues a model-side
    instruction; the sim makes Hands acknowledge it aloud on the next beat so
    the full-chain timing is visible in the transcript. end(): every event
    still flushes, so a scripted caller hangup is observed.
    """

    name = "simulated"
    supports_media_audio = False

    def __init__(self) -> None:
        super().__init__()
        self._task: Optional[asyncio.Task] = None
        self._ended = False
        self._spoke: list[str] = []
        self._pending_steers: list[str] = []
        self._wake = asyncio.Event()

    # -- controlling legs -----------------------------------------------------
    async def speak(self, text: str) -> None:
        self._spoke.append(text)
        # In sim the user also hears Hands' leg through queue:say (TTS),
        # so the full audio loop is testable both ways.
        self._emit({"kind": "call_audio", "speaker": "hands", "format": "queue:say",
                    "text": text, "duration_s": 0.0})

    def hold(self) -> None:
        self._emit({"kind": "call_status", "state": "held"})

    def unhold(self) -> None:
        self._emit({"kind": "call_status", "state": "unheld"})

    def steer(self, instruction: str) -> None:
        self._pending_steers.append(instruction or "")
        self._wake.set()

    async def end(self, reason: str = "hangup") -> None:
        await self._finish(reason)

    # -- main script ----------------------------------------------------------
    async def start(self, handle: CallHandle) -> None:
        self._task = asyncio.create_task(self._run(handle))

    def _pace(self, handle: CallHandle, secs: float) -> float:
        sp = max(0.05, min(float(handle.speed or 1.0), 10.0))
        return max(0.05, secs * sp)

    async def _sleep(self, handle: CallHandle, secs: float) -> None:
        remaining = self._pace(handle, secs)
        while remaining > 0 and not self._ended:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=min(remaining, 0.3))
            except asyncio.TimeoutError:
                pass
            self._wake.clear()
            remaining -= 0.3

    def _drain_steers(self, handle: CallHandle) -> None:
        while self._pending_steers and not self._ended:
            s = self._pending_steers.pop(0)
            # model-side ack spoken into the call (Hands' voice, never the user's)
            ack = STEER_ACK.format(short=s[:40])
            self._spoke.append(ack)
            self._emit({"kind": "call_transcript", "speaker": "hands", "text": ack})
            self._emit({"kind": "call_audio", "speaker": "hands", "format": "queue:say",
                        "text": ack, "duration_s": 0.0})

    async def _run(self, handle: CallHandle) -> None:
        em = self._emit
        try:
            em({"kind": "call_status", "state": "dialing"})
            em(dict(LINE_STATIC, kind="call_tone"))
            await self._sleep(handle, 0.35)
            if self._ended:
                return
            em(dict(DIAL_EXPECTANT, kind="call_tone"))
            await self._sleep(handle, 0.75)
            if self._ended:
                return
            em({"kind": "call_status", "state": "ringing"})
            em(dict(RINGBACK, kind="call_tone"))
            await self._sleep(handle, float(RINGBACK["dur_s"]))
            if self._ended:
                return
            if str(handle.to).strip().startswith(("busy", "999")):
                em(dict(BUSY, kind="call_tone"))
                await self._finish("busy")
                return
            em({"kind": "call_status", "state": "connected"})
            script = handle.script or DEFAULT_SIM_SCRIPT
            for line in script:
                if self._ended:
                    break
                self._drain_steers(handle)
                sp = line["speaker"]
                tx = line["text"]
                em({"kind": "call_transcript", "speaker": sp, "text": tx})
                em({"kind": "call_audio", "speaker": sp, "format": "queue:say",
                    "text": tx, "duration_s": round(0.05 * len(tx), 2)})
                await self._sleep(handle, 1.0 + 0.045 * len(tx))
            if not self._ended:
                em({"kind": "call_status", "state": "ended", "reason": "remote_hangup"})
                self._ended = True
        except asyncio.CancelledError:
            pass
        finally:
            self._ended = True

    async def _finish(self, reason: str) -> None:
        if self._ended:
            return
        self._ended = True
        self._emit({"kind": "call_status", "state": "ended", "reason": reason})
        if self._task and not self._task.done():
            self._task.cancel()


class TwilioMediaStreamsProvider(CallProvider):
    """Placeholder for the real provider — intentionally NOT wired.

    Constructing it raises with the FULL checklist so `TELEPHONY_PROVIDER=twilio`
    fails loudly instead of silently simulating. The module docstring lists what
    a real integration needs (SDK, creds, public TwiML webhook, inbound media WS,
    mulaw up/down legs, far-side STT, Hands-side TTS into write()).
    """

    name = "twilio_media_streams"
    supports_media_audio = True

    def __init__(self) -> None:
        missing = [k for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
                               "TWILIO_FROM_NUMBER") if not os.getenv(k, "").strip()]
        raise NotImplementedError(
            "Twilio Media Streams provider is not implemented in this repo. "
            "To go live you need: pip install twilio"
            + ("; set " + ", ".join(missing) if missing else "")
            + "; expose a public HTTPS TwiML webhook + inbound WSS media endpoint "
              "(see utils/call_provider.py docstring) and route media frames "
              "into call_audio{format:'mulaw:8000'}. "
              "Unset TELEPHONY_PROVIDER to use 'simulated'.")

    async def start(self, handle: CallHandle) -> None:  # pragma: no cover
        raise NotImplementedError


_PROVIDER_BY_NAME = {
    "": SimulatedCallProvider, "sim": SimulatedCallProvider,
    "simulated": SimulatedCallProvider,
    "twilio": TwilioMediaStreamsProvider,
    "twilio_media_streams": TwilioMediaStreamsProvider,
}


def build_provider(which: Optional[str] = None) -> CallProvider:
    """Factory honouring TELEPHONY_PROVIDER (default simulated)."""
    key = (which if which is not None else os.getenv("TELEPHONY_PROVIDER", "simulated"))
    key = str(key).strip().lower()
    ctor = _PROVIDER_BY_NAME.get(key)
    if ctor is None:
        raise ValueError(f"Unknown TELEPHONY_PROVIDER: {key!r} (use simulated|twilio)")
    return ctor()


__all__ = ["CallProvider", "SimulatedCallProvider", "TwilioMediaStreamsProvider",
           "CallHandle", "DEFAULT_SIM_SCRIPT", "build_provider",
           "LINE_STATIC", "DIAL_EXPECTANT", "RINGBACK", "BUSY"]
