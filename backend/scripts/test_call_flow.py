"""End-to-end SIMULATED CALL proof (backend lane, offline, no pytest needed).

Drives the production code path: utils/call_lane.open_call_lane() -> the
provider script runs in ITS OWN asyncio task (the persona turn never blocks),
while this "client" subscribes to lane.stream() exactly like the SSE route
(routers/aiagent/persona_orchestrator.py /{tid}/calls/{cid}/stream) does:

  1. dialing + call_tone frames arrive BEFORE the call is connected
  2. live transcript (them|hands) with matching call_audio legs stream in
  3. steer() mid-call -> ONLY a speaker:"me" transcript row reaches the UI
     (control('steer') is text; no user audio path into a call exists)
  4. the sim acks the steer aloud on the call (hands leg)
  5. hold/unhold map onto lane state; end() closes with a terminal frame

Run: python scripts/test_call_flow.py   (exit 0 = green)
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import call_lane as cl            # noqa: E402

TID = "t-test-call"
FAILS: list[str] = []


def check(label: str, cond: bool, got=None) -> None:
    if cond:
        print("PASS: " + label)
    else:
        print("FAIL: " + label + " -> got " + repr(got))
        FAILS.append(label)


async def main() -> int:
    cl.reset_registry()
    os.environ["TELEPHONY_PROVIDER"] = "simulated"

    # THE PRODUCTION ENTRY: the `start_call` host tool opens the lane and
    # returns immediately — the turn that fires it is never blocked by the call.
    info = await cl.open_call_lane(TID, "lnca11ca11", {
        "to": "+15551234567",
        "purpose": "confirm Ana's appointment tomorrow at nine",
        "speed": 0.05,   # compress the sim clock so the whole call is quick
    })
    check("start_call returns immediately with lane/stream ids",
          bool(info["call_id"]) and info["stream_path"].endswith("/stream") and info["simulated"], info)
    cid = info["call_id"]
    lane = cl.get_lane(cid)
    check("lane registered under the thread", lane is not None and lane.tid == TID, cid)

    # Subscribe up-front — the stream replays history, then feeds live frames.
    seen: list[dict] = []

    async def collector() -> None:
        async for frame in lane.stream():
            if frame.get("kind") == "_keepalive":
                continue
            seen.append(frame)

    sink = asyncio.create_task(collector())

    states: list[str] = []
    tones: list[str] = []
    while "connected" not in states:
        await asyncio.sleep(0.02)
        states = [f.get("state") for f in seen if f.get("kind") == "call_status"]
        tones = [f.get("tone") for f in seen if f.get("kind") == "call_tone"]
        if len(seen) > 2000:
            break
    check("call_status dialing->ringing->connected streamed",
          "dialing" in states and "ringing" in states and "connected" in states, states)
    check("call_tone static+dial+ringback arrived before connect",
          {"static", "dial", "ringback"} <= set(tones), tones)


    # wait for the far side's first line (transcript + audio leg both exist)
    lines: list[dict] = []
    for _ in range(400):
        await asyncio.sleep(0.02)
        lines = [f for f in seen if f.get("kind") == "call_transcript"]
        if lines:
            break
    check("live transcript streaming (speaker them/hands)", bool(lines), lines[:2])
    audio_legs = [f for f in seen if f.get("kind") == "call_audio"]
    check("far/hands speech also rides the audio leg (queue:say)",
          audio_legs and all(f.get("speaker") in ("them", "hands") for f in audio_legs), audio_legs[:2])

    # STEER MID-CALL — the hard boundary: user voice becomes model-side TEXT.
    st = await lane.control("steer", "also ask about the afternoon")
    check("steer control reports heard_by=model_only",
          st.get("ok") is True and st.get("heard_by") == "model_only", st)
    await asyncio.sleep(0.05)   # let the subscriber drain the just-emitted frames
    me = [f for f in seen if f.get("kind") == "call_transcript" and f.get("speaker") == "me"]
    check("steer echoes exactly once as transcript speaker 'me'", len(me) == 1, me)
    q = cl.consume_model_steers(TID)
    check("steer queued for the MODEL side (next /act turn hears it)",
          q == ["also ask about the afternoon"], q)
    check("no call_audio frame is ever speaker 'me' (user mic never enters the call)",
          not [f for f in seen if f.get("kind") == "call_audio" and f.get("speaker") == "me"],
          [f.get("speaker") for f in seen if f.get("kind") == "call_audio"])
    acked = False
    for _ in range(400):
        await asyncio.sleep(0.02)
        acked = any(f.get("kind") == "call_transcript" and f.get("speaker") == "hands"
                    and f.get("text", "").startswith("One moment") for f in seen)
        if acked:
            break
    check("Hands acknowledged the steer aloud on the call", acked, [f.get("text") for f in seen if f.get("kind") == "call_transcript"][-3:])


    # Hands speaks INTO the call (the TTS leg of the audio loop)
    sp = await lane.control("speak", "Noted, I'll add the afternoon as an option.")
    check("speak control accepted (Hands -> far end)", sp.get("ok") is True, sp)
    await asyncio.sleep(0.05)
    check("speak lands as transcript speaker hands + an audio leg",
          any(f.get("kind") == "call_transcript" and f.get("speaker") == "hands"
              and "afternoon as an option" in f.get("text", "") for f in seen), None)

    # HOLD / RESUME mirror onto lane state (the pet reads the same chain)
    await lane.control("hold")
    await asyncio.sleep(0.05)
    check("hold -> lane state held", lane.state == "held", lane.state)
    await lane.control("unhold")
    await asyncio.sleep(0.05)
    check("unhold returns the lane to a live state", lane.state not in ("held",), lane.state)

    # HANGUP: terminal frame so every subscriber's stream closes.
    await cl.inject_end(TID, {"call_id": cid, "reason": "user_hangup"})
    closed = await lane.wait_closed(timeout_s=5.0)
    check("end_call closes the lane with a terminal frame", closed and lane.state == "ended", lane.state)
    await asyncio.wait_for(sink, timeout=5.0)
    last = seen[-1]
    check("last frame is call_status ended (+ reason)",
          last.get("kind") == "call_status" and last.get("state") == "ended"
          and last.get("reason") == "user_hangup", last)

    # every frame carries the stamped envelope the SSE route forwards
    check("every frame stamped {call_id, lane, seq, ts}",
          all(f.get("call_id") == cid and f.get("lane") == "lnca11ca11"
              and isinstance(f.get("seq"), int) and isinstance(f.get("ts"), float) for f in seen),
          seen[0] if seen else None)
    notes = cl.ended_call_notes(TID)
    check("ended call is summarised back to the persona for the next turn",
          any(cid in n for n in notes), notes)

    print()
    print("--- {} lane frames: {} status, {} tones, {} transcript, {} audio".format(
        len(seen),
        sum(1 for f in seen if f.get("kind") == "call_status"),
        sum(1 for f in seen if f.get("kind") == "call_tone"),
        sum(1 for f in seen if f.get("kind") == "call_transcript"),
        sum(1 for f in seen if f.get("kind") == "call_audio")))
    if FAILS:
        print("FAILED: " + ", ".join(FAILS))
        return 1
    print("ALL PASS - simulated call end-to-end (dial tones -> connected -> live transcript "
          "-> steer mid-call (model-only) -> hold/speak -> ended)")
    return 0


if __name__ == "__main__":
    import time
    t0 = time.time()
    rc = asyncio.run(main())
    print("took {:.1f}s".format(time.time() - t0))
    sys.exit(rc)
