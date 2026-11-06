"""Routing contract tests — the "one owner per message" invariant.

Covers the material the user asked for:

  1. needs_user round-trip: a busy R lane raises a question on the bus, L sees
     it in its prompt, the human's answer is routed back to THAT lane only as
     `ln=<lane>=answer: ...` steering (rail 1 in the timeline text, rail 2 in
     the x-sawii-steer merge), and the open-need list is emptied deterministically.
  2. plain user message: nothing about it fans out to R lanes. The router tool
     refuses a steer that does not name ONE live lane, and the host prompt
     carries the addressing contract that says R lanes must not act on it.
  3. one owner: an ambiguous routing decision that could hit several lanes gets
     either one lane or a refusal — never a broadcast to every active lane.

Runs against the production module (utils.lane_bus) and the orchestrator's real
message builder — no HTTP, no live persona server.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from utils import lane_bus as lb                                    # noqa: E402
from routers.aiagent import persona_orchestrator as orch            # noqa: E402


class _Thread:
    def __init__(self, tid: str, title: str = "Hands"):
        self.id = tid
        self.title = title


class _Task:
    def __init__(self, text: str = "call the clinic"):
        self.task_text = text


@pytest.fixture(autouse=True)
def clean_bus():
    lb.reset_bus()
    yield
    lb.reset_bus()


LANE_A = "lnaaaa1111"
LANE_B = "lnbbbb2222"
TID = "t-route-test"


# ── 1. needs_user round-trip ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_needs_user_round_trip():
    """lane asks -> bus frame + L prompt block -> human answers -> ONE lane hears it."""
    lb.note_lane_activity(TID, LANE_A, "desktop_click")
    sub_q = lb.subscribe(TID)          # subscribe FIRST: the ask publishes live
    q = await orch._run_lane_tool(
        "needs_user",
        {"question": "Which clinic — downtown or north side?",
         "blocker": "the number differs", "choices": ["downtown", "north side"]},
        TID, lane_id=LANE_A)
    rec = json.loads(q)
    assert rec["ok"] and rec["lane"] == LANE_A, rec
    need_id = rec["need_id"]

    # the question is on the bus, and it is open for L to narrate
    frames = lb.drain(sub_q)
    assert any(f["kind"] == "lane_needs_user" and f["need_id"] == need_id
               for f in frames), frames
    assert [n["need_id"] for n in lb.open_needs(TID)] == [need_id]

    # L's per-turn context lists the need (never left unanswered in narration)
    block = lb.needs_block_for_prompt(TID)
    assert "needs_user" in block and need_id in block and LANE_A in block, block
    assert "MUST raise each one" in block

    # the human answers: routed to the asking lane and nowhere else
    ans = json.loads(await orch._run_lane_tool(
        "answer_lane_need", {"need_id": need_id, "text": "north side"}, TID, lane_id=LANE_A))
    assert ans["ok"] and ans["routed"] == "ln-steer" and ans["lane"] == LANE_A, ans
    assert lb.open_needs(TID) == []
    steers = lb.consume_lane_steers(TID)
    assert steers == [(LANE_A, "answer: north side")], steers

    # ...and it ships on the existing rails: timeline text `ln=<lane>=answer:`
    # (rail 1) plus the merged header string (rail 2).
    msgs = orch._build_messages(_Thread(TID), _Task(),
                                orch.PersonaActRequest(text="north side"),
                                [(LANE_A, "answer: north side")])
    steer_lines = [m for m in msgs if str(m.get("content", "")).startswith("[steering]")
                   and "ln=" in str(m.get("content", ""))]
    assert steer_lines and f"ln={LANE_A}=answer: north side" in steer_lines[0]["content"]
    header = orch._merge_steer(None, [(LANE_A, "answer: north side")])
    assert header == f"{LANE_A}=answer: north side", header


# ── 2. plain user message does not trigger action on R lanes ─────────────────

def test_plain_user_message_prompt_contract():
    """The host prompt tells R lanes an unaddressed turn is awareness only,
    and L (the router) MUST own it: no action prompt leaks to the lanes."""
    lb.note_lane_activity(TID, LANE_A)
    msgs = orch._build_messages(_Thread(TID), _Task("dial the clinic"),
                                orch.PersonaActRequest(text="what's the weather?"))
    sys_text = "\n".join(m["content"] for m in msgs if m["role"] == "system")

    # the R addressing rule is present verbatim
    assert "[lane addressing]" in sys_text
    assert "plain user message has" in sys_text and "do NOT start" in sys_text
    # L's router contract is present: classify every message, never broadcast
    assert "[lane routing]" in sys_text
    for kind in ("respond-in-chat", "steer-to-lane", "spawn-new-R", "surface-needs_user"):
        assert kind in sys_text, kind
    assert "NEVER broadcast" in sys_text
    # the plain user turn itself carries NO lane marker: no `ln=` means an R
    # lane has nothing to act on (that's the executable check, asserted below).
    user_turns = [m["content"] for m in msgs if m["role"] == "user"]
    assert user_turns and not any("ln=" in t for t in user_turns), user_turns
    assert lb.lane_addressed_to(user_turns[0], LANE_A) is False


@pytest.mark.asyncio
async def test_needs_user_is_not_broadcast():
    """One question listens on exactly the asking lane; the other lane is untouched."""
    lb.note_lane_activity(TID, LANE_A)
    lb.note_lane_activity(TID, LANE_B)
    rec = json.loads(await orch._run_lane_tool(
        "needs_user", {"question": "approve this file write?"}, TID, lane_id=LANE_B))
    routed = lb.needs_for_lane(TID, LANE_A)
    assert routed == [], routed
    assert lb.needs_for_lane(TID, LANE_B)[0]["need_id"] == rec["need_id"]
    out = json.loads(await orch._run_lane_tool(
        "answer_lane_need", {"need_id": rec["need_id"], "text": "yes"}, TID, lane_id=LANE_A))
    assert out["lane"] == LANE_B and out["ok"]
    assert lb.consume_lane_steers(TID) == [(LANE_B, "answer: yes")]


# ── 3. route_decision is validated data, not prose ────────────────────────────

@pytest.mark.asyncio
async def test_route_decision_steering_requires_one_live_lane():
    lb.note_lane_activity(TID, LANE_A, "desktop_type")
    lb.note_lane_activity(TID, LANE_B, "fetch_url")

    # ambiguous / unaddressed steering is REFUSED — the broadcast bug cannot happen
    bad = json.loads(await orch._run_lane_tool("route_decision", {"decision": "steer"}, TID))
    assert not bad["ok"] and set(bad["active_lanes"]) == {LANE_A, LANE_B}, bad

    ghost = json.loads(await orch._run_lane_tool(
        "route_decision", {"decision": "steer", "lane_id": "lndeadbeef",
                           "instruction": "use the afternoon slot"}, TID))
    assert not ghost["ok"] and "not an active lane" in ghost["error"], ghost

    ok = json.loads(await orch._run_lane_tool(
        "route_decision", {"decision": "steer", "lane_id": LANE_A,
                           "instruction": "use the afternoon slot"}, TID))
    assert ok["ok"] and ok["lane"] == LANE_A and ok["queued"], ok
    steers = lb.consume_lane_steers(TID)
    # ONE owner: the instruction belongs exclusively to LANE_A (never LANE_B).
    assert steers == [(LANE_A, "use the afternoon slot")], steers
    assert all(ln != LANE_B for ln, _ in steers), steers

    chat = json.loads(await orch._run_lane_tool("route_decision", {"decision": "chat"}, TID))
    assert chat["ok"] and chat["decision"] == "chat"
    new = json.loads(await orch._run_lane_tool("route_decision", {"decision": "new_task"}, TID))
    assert new["ok"] and new["decision"] == "new_task"

    # lane ids arrive as raw call ids too (persona_client shape)
    assert lb.normalize_lane(f"call_{LANE_A}_needs_user") == LANE_A


@pytest.mark.asyncio
async def test_route_decision_tool_schemas_registered():
    names = {t["function"]["name"] for t in orch.TASKER_TOOLS}
    assert {"needs_user", "answer_lane_need", "get_open_needs", "route_decision"} <= names
    assert {"needs_user", "answer_lane_need", "route_decision", "get_open_needs"} <= orch._LANE_TOOLS
    route = next(t for t in orch.TASKER_TOOLS if t["function"]["name"] == "route_decision")
    assert set(route["function"]["parameters"]["properties"]["decision"]["enum"]) == \
        set(lb.ROUTE_DECISIONS)


def test_bus_events_surface_for_the_client():
    q = lb.subscribe(TID)
    lb.publish(TID, {"kind": "lane_route", "lane": LANE_A, "instruction": "go"})
    frames = lb.drain(q)
    assert frames and frames[-1]["kind"] == "lane_route" and frames[-1]["seq"] >= 1
    lb.unsubscribe(TID, q)


def test_companion_predicate_matches_host_contract():
    """The companion-side executable rule agrees with the host's rail format."""
    for cand in (BACKEND.parents[1] / "sawii-persona" / "src",        # sibling repo checkout
                Path(BACKEND.parent).parent / "src"):                 # vendored inside tasker-github
        if (cand / "sawii_persona" / "kernel" / "lane_routing.py").exists():
            sys.path.insert(0, str(cand))
            break
    try:
        from sawii_persona.kernel import lane_routing as lr
    except ImportError:                                   # companion repo not present
        pytest.skip("sawii-persona kernel not importable from this checkout")
    plain = "what's the weather?"
    assert lr.may_act_on_user_turn(plain, LANE_A) is False
    assert lr.may_act_on_user_turn(plain, LANE_A, lobe="L") is True
    assert lr.may_act_on_user_turn(f"[steering] ln={LANE_A}=use the afternoon", LANE_A) is True
    assert lr.may_act_on_user_turn(f"[steering] ln={LANE_A}=use the afternoon", LANE_B) is False
    # the answer shape both sides use
    assert lr.split_steering(f"ln={LANE_A}=answer: north side") == \
        ([(LANE_A, "answer: north side")], [])
    prompt = lr.lane_prompt(LANE_B, lobe="R", task="dial the clinic")
    assert "[lane addressing]" in prompt and LANE_B in prompt
    assert "dial the clinic" in prompt


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
