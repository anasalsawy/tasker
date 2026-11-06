"""Scripted flow: fake audio frames -> WakePipeline fires -> ack under 1 s ->
chain delegates to a STUBBED persona stream -> intent completes. No mic, no
network, no tray. Mirrors what main.sim_say() does, asserting every seam."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shell.audio import silence_frames, synthetic_speech_frames   # noqa: E402
from shell.chain import Chain                                      # noqa: E402
from shell.config import ACK_DEADLINE_S, ShellConfig               # noqa: E402
from shell.notify import acknowledge                               # noqa: E402
from shell.wake import WakePipeline                                # noqa: E402
import shell.persona as persona_mod                                # noqa: E402


class AckSpy:
    def __init__(self):
        self.events = []
        self.in_callback_ok = []

    def __call__(self, ev):
        dt = acknowledge(engine=ev.engine, score=ev.score,
                         sound=False, tts_text=None)   # silent but real path
        self.events.append(ev)
        # ack_at is stamped by the pipeline AFTER this returns; assert on the
        # event push_frame() hands back, not on the live event here.
        self.in_callback_ok.append(dt <= ACK_DEADLINE_S)
        return dt


@pytest.fixture()
def cfg(monkeypatch, tmp_path):
    monkeypatch.setenv("HANDS_SHELL_PORT", "0")
    c = ShellConfig.load(ROOT / "config.toml")
    c.wake.engine = "simulated"
    c.ack_sound = False
    c.ack_tts = False
    c.context.persist_path = "var/state/context.jsonl"
    return c


def simulate_wake(cfg, ack: AckSpy) -> WakePipeline:
    from shell.wake import SimulatedEngine
    pipe = WakePipeline(cfg.wake, SimulatedEngine(cfg.wake), on_wake=ack)
    pipe.arm_text()
    for f in silence_frames(0.3) + synthetic_speech_frames(0.5):
        if pipe.push_frame(f):
            break
    assert ack.events, "scripted wake never fired"
    return pipe


def test_wake_ack_under_deadline(cfg):
    """Requirement: <1 s wake-to-proof-of-life on the mock pipeline."""
    ack = AckSpy()
    pipe = simulate_wake(cfg, ack)
    assert ack.in_callback_ok and all(ack.in_callback_ok)   # ack call itself fast
    # pipeline stamps ack_at right after the callback returns -> real latency
    assert pipe.last is ack.events[0]
    assert 0.0 <= pipe.last.ack_latency_s <= ACK_DEADLINE_S
    assert pipe.last.as_dict()["ack_under_deadline"] is True


def test_wake_then_delegate_flow(cfg, monkeypatch):
    """wake -> ack -> session -> Chain.submit -> stub SSE -> done snapshot."""
    ack = AckSpy()
    simulate_wake(cfg, ack)

    # stub persona transport: yields SSE-style events; asserts request shape
    seen: dict = {}

    def fake_stream_turn(c, utterance, context_summary, session_id=None,
                         client=None):
        seen["utterance"] = utterance
        seen["context"] = context_summary
        seen["session_id"] = session_id
        yield {"type": "delta", "text": "5 + 7 is "}
        yield {"type": "tool_call",
               "tool_call": {"id": "tc1", "name": "calculator",
                             "args": {"expr": "5+7"}}}
        yield {"type": "delta", "text": "12."}
        yield {"type": "done", "text": "5 + 7 is 12.", "turn_id": None,
               "finish_reason": "stub", "metrics": None}

    monkeypatch.setattr(persona_mod, "stream_turn", fake_stream_turn)
    monkeypatch.setattr("shell.chain.persona", persona_mod)

    chain = Chain(cfg, context_summary=lambda: "ambient: test window (chrome)")
    sid = chain.note_wake()                       # what post_wake does
    resp = chain.submit("what is 5 + 7", session_id=sid, source="wake-voice")
    done = chain.wait(resp.req_id, timeout_s=10.0)
    assert done is resp and done.status == "done", done.error
    assert done.text == "5 + 7 is 12."
    assert done.route == "persona-direct"          # no backend thread configured
    assert seen["utterance"] == "what is 5 + 7"
    assert "chrome" in seen["context"]             # ambient block flowed through
    assert seen["session_id"] == sid               # wake session linked the intent
    # tool recorded + parked (no task_executor_url in test config)
    assert len(done.tool_calls) == 1
    assert done.tool_calls[0]["name"] == "calculator"
    assert done.parked_tools == ["tc1"]


def test_wake_session_window_links_follow_up(cfg):
    """Intents right after a wake inherit its session_id (lane order)."""
    chain = Chain(cfg, context_summary=lambda: "", on_done=None)
    sid = chain.note_wake()
    assert chain.session_for_intent(None) == sid
    r = chain.submit("follow up", run=False)
    assert r.session_id == sid


def test_alternate_wake_words_fire(cfg):
    """Every configured wake phrase arms the simulated engine identically."""
    cfg.wake.words = ["hey tasker"]
    ack = AckSpy()
    pipe = simulate_wake(cfg, ack)
    assert pipe.last.engine == "simulated"
