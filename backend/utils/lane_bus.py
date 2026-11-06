"""lane_bus — host-side event bus between persona execution lanes (R) and lobe L.

Why this exists
---------------
Every lane shares ONE conversation timeline (unity of mind). That is good for
awareness but bad for ownership: a plain user message (no lane id) lands in the
shared history and any R lane could act on it — two lanes doing the same
instruction, or one lane ignoring what was meant for it. So user conversation
reaches ONLY L directly; L is the router. R lanes act on user input only through
the existing lane-addressed steering rail (`ln=<lane-id>=<instruction>`, rail 1
of the persona_host_sdk contract).

This module is the host side of that routing:

  * `ask_user(...)`      — a busy R lane's `needs_user` host tool registers an
    open question and publishes a frame on the bus. It NEVER blocks the turn:
    the answer comes back later as `ln=<lane>=answer: ...` steering.
  * `needs_block_for_prompt(tid)` — lobe L's per-turn system context lists the
    open questions so L narrates them to the user (never leave one unanswered).
  * `answer_need(tid, need_id, text)` — marks the need answered and queues the
    answer as lane steering; `_build_messages` (orchestrator) folds it into the
    next turn's `[steering] ln=<lane>=...` line and the x-sawii-steer header.
    The answer goes to ONE lane — never a fresh broadcast user message.
  * `route_decision(...)` — the structured (deterministic) router tool: L's
    classify-every-user-message decision arrives as a tool call
    {decision: chat|steer|new_task|surface_need, lane_id, instruction}. A steer
    to an unknown lane is REFUSED with the live lane list, which is what makes
    "pick ONE owner, never broadcast" a code invariant, not a prose vibe.
  * `subscribe/publish/drain` — plain in-process pubsub (mirrors the persona
    server's mind.Bus): the orchestrator forwards frames on /act as
    `event: lane_tool` rows and on the persistent GET /{tid}/lane_events SSE.

Lane ids are the `ln<8 hex>` inside `call_lnXXXXXXXX_...` (see persona_client.
lane_of); `normalize_lane()` also accepts a raw call id and uppercase variants.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import re
import time
from typing import Any, Optional

log = logging.getLogger(__name__)

#: max open needs listed in one prompt block (noise guard — never loses one)
MAX_NEEDS_PER_BLOCK = 8
#: live lanes remembered per thread for route_decision validation
MAX_ACTIVE_LANES = 16
#: bus frames per subscriber queue (slow consumer drops; prompt listings remain)
BUS_QUEUE_SIZE = 256

_LANE_IN_CALL_ID = re.compile(r"^call_(ln[0-9a-f]{6,8})(?:_|$)", re.IGNORECASE)
_LANE_TOKEN = re.compile(r"^(ln)?([0-9a-f]{6,8})$", re.IGNORECASE)
#: a "[steering] ln=<id>=..." line addressed to `lane` — the ONLY user voice an R lane acts on
_STEER_LINE = re.compile(r"\bln=([A-Za-z0-9]+)=")

_seq = itertools.count(1)

# tid -> set[asyncio.Queue]  (frames queued for SSE surfaces)
_SUBS: dict[str, set[asyncio.Queue]] = {}
# tid -> per-thread frame sequence stamp
_bus_seq: dict[str, int] = {}
# need_id -> record dict
_NEEDS: dict[str, dict[str, Any]] = {}
# tid -> [[lane, text, ts]] queued lane steering (drained once per turn)
_PENDING_STEERS: dict[str, list[list[Any]]] = {}
# tid -> [{"lane":..., "last_tool":..., "ts":...}] newest last
_ACTIVE_LANES: dict[str, list[dict[str, Any]]] = {}


# ── lane id helpers ───────────────────────────────────────────────────────────

def normalize_lane(raw: Optional[str]) -> Optional[str]:
    """'lnabcd1234' | 'LNABCD1234' | 'call_lnabcd1234_needs_user' -> 'lnabcd1234'."""
    if not raw:
        return None
    s = str(raw).strip()
    m = _LANE_IN_CALL_ID.match(s)
    if m:
        return m.group(1).lower()
    m = _LANE_TOKEN.match(s)
    if not m:
        return None
    body = m.group(2).lower()
    return body if body.startswith("ln") else "ln" + body


def lane_addressed_to(text: str, lane: str) -> bool:
    """True if a persona turn line addresses `lane` via the ln= steering rail.

    Plain user messages have no ln= marker, so R lanes must not treat them as
    instructions; only `[steering] ln=<lane>=...` (rail 1) or the host-side
    equivalent counts as being spoken to.
    """
    if not text:
        return False
    target = normalize_lane(lane) or str(lane or "").strip().lower()
    if not target:
        return False
    return any(m.group(1).lower() == target for m in _STEER_LINE.finditer(text))


# ── bus (pubsub) ──────────────────────────────────────────────────────────────

def subscribe(tid: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=BUS_QUEUE_SIZE)
    _SUBS.setdefault(tid, set()).add(q)
    return q


def unsubscribe(tid: str, q: asyncio.Queue) -> None:
    _SUBS.get(tid, set()).discard(q)


def publish(tid: str, frame: dict[str, Any]) -> None:
    """Stamp + fan a frame out. Never blocks a lane; slow subscribers drop."""
    _bus_seq[tid] = _bus_seq.get(tid, 0) + 1
    frame = {**frame, "tid": tid, "seq": _bus_seq[tid], "ts": round(time.time(), 3)}
    for q in list(_SUBS.get(tid, ())):
        try:
            q.put_nowait(frame)
        except asyncio.QueueFull:
            pass  # the durable copy is _NEEDS + the next turn's prompt block


def drain(q: asyncio.Queue) -> list[dict[str, Any]]:
    """Everything currently queued, oldest first (used by the /act SSE loop)."""
    out: list[dict[str, Any]] = []
    while True:
        try:
            out.append(q.get_nowait())
        except asyncio.QueueEmpty:
            return out


# ── active lane bookkeeping (route_decision's single-owner invariant) ────────

def note_lane_activity(tid: str, lane: Optional[str], tool: str = "") -> None:
    """Remember a lane as live when one of its host tool calls runs."""
    if not tid:
        return
    ln = normalize_lane(lane)
    if not ln:
        return
    rows = _ACTIVE_LANES.setdefault(tid, [])
    rows[:] = [r for r in rows if r["lane"] != ln]
    rows.append({"lane": ln, "last_tool": str(tool or "")[:60], "ts": time.time()})
    if len(rows) > MAX_ACTIVE_LANES:
        del rows[:len(rows) - MAX_ACTIVE_LANES]


def active_lanes(tid: str, limit: int = 6) -> list[str]:
    """Most recently active first — what a router steer may target."""
    return [r["lane"] for r in reversed(_ACTIVE_LANES.get(tid, []))][:limit]


def active_lanes_note(tid: str) -> str:
    """The live-lane roster a `route_decision(steer)` may legally target."""
    rows = list(reversed(_ACTIVE_LANES.get(tid, [])))[:MAX_ACTIVE_LANES]
    if not rows:
        return ("[live lanes] none right now — a plain user message is yours to "
                "answer in chat or to spawn a NEW R lane for (route_decision "
                "new_task). Do not steer a lane that does not exist.")
    bits = "; ".join(f"{r['lane']} (last: {r['last_tool'] or 'work'})" for r in rows)
    return ("[live lanes] " + bits + " — steer exactly ONE of these; the roster is "
            "what route_decision validates against.")


# ── lane-side steering queue (answers + confirmed router steers) ─────────────

def queue_lane_steer(tid: str, lane: Optional[str], text: str) -> Optional[str]:
    """Queue one instruction for exactly ONE lane; returns the normalized lane.

    `lane=None` is a broadcast (call-steer lines the persona hears thread-wide)
    and is kept for the legacy [call steer] rail. Router answers NEVER pass
    None — L picks one owner.
    """
    t = str(text or "").strip()
    if not t:
        return None
    ln = normalize_lane(lane)
    _PENDING_STEERS.setdefault(tid, []).append([ln, t[:512], time.time()])
    return ln


def consume_lane_steers(tid: str, limit: int = 8) -> list[tuple[Optional[str], str]]:
    """Pop everything queued since last turn as [(lane|None, text)] oldest-first."""
    return [(ln, txt) for ln, txt, _ in _PENDING_STEERS.pop(tid, [])][:limit]


# ── needs_user — the R lane's "I need the human" rail ────────────────────────

def ask_user(tid: str, lane: Optional[str], question: str = "", *,
             blocker: str = "", context: str = "", choices: Optional[list] = None,
             timeout_s: Optional[float] = None) -> dict[str, Any]:
    """Register an open question from a busy lane and publish it on the bus.

    Non-blocking by design: the lane keeps running (it should stay polite and
    useful while waiting); the answer returns to THIS lane as
    `ln=<lane>=answer: ...` steering on a later turn — never as a new broadcast
    user message.
    """
    ln = normalize_lane(lane)
    q = str(question or "").strip() or str(blocker or "").strip()
    if not q:
        raise ValueError("needs_user needs a 'question' (or 'blocker')")
    need_id = "need_" + format(next(_seq), "x") + str(int(time.time()) % 100000)
    rec = {
        "need_id": need_id, "tid": tid, "lane": ln,
        "question": q[:512], "blocker": str(blocker or "").strip()[:512],
        "context": str(context or "").strip()[:512],
        "choices": [str(c)[:120] for c in (choices or [])][:8],
        "status": "open", "asked_at": time.time(),
        "answered_at": None, "answer": None,
        "timeout_s": float(timeout_s) if timeout_s else None,
    }
    _NEEDS[need_id] = rec
    if ln:
        note_lane_activity(tid, ln, "needs_user")
    publish(tid, {"kind": "lane_needs_user", **{k: rec[k] for k in (
        "need_id", "lane", "question", "blocker", "context", "choices", "asked_at")}})
    log.info("lane %s asks the user (%s): %s", ln, need_id, q[:80])
    return dict(rec)


def open_needs(tid: str) -> list[dict[str, Any]]:
    """Open questions on this thread, oldest first (nothing gets lost)."""
    return [r for r in sorted(_NEEDS.values(), key=lambda r: r["asked_at"])
            if r["tid"] == tid and r["status"] == "open"]


def get_need(tid: str, need_id: str) -> Optional[dict[str, Any]]:
    """One need on this thread, open or answered (HTTP surfaces, tests)."""
    rec = _NEEDS.get(str(need_id or "").strip())
    if rec is None or rec["tid"] != tid:
        return None
    return dict(rec)


def needs_block_for_prompt(tid: str) -> str:
    """L-conversation surface: the open needs L MUST narrate this turn.

    Empty string when there is nothing pending. Every line carries its need_id
    and lane so the answer can be routed back deterministically.
    """
    rows = open_needs(tid)[:MAX_NEEDS_PER_BLOCK]
    if not rows:
        return ""
    lines = ["[lane needs_user] Your execution lanes are waiting on the human. "
             "You (L) MUST raise each one in your next conversational reply — "
             "never leave a needs_user question unanswered in narration. When the "
             "human answers, route it with answer_lane_need(need_id, text) or a "
             "[steering] ln=<lane>=answer: ... line back to THAT lane only."]
    for r in rows:
        bits = [f"need_id={r['need_id']}", f"lane={r['lane'] or 'unknown'}",
                f"question: {r['question']}"]
        if r.get("blocker"):
            bits.append(f"blocker: {r['blocker']}")
        if r.get("choices"):
            bits.append("choices: " + " | ".join(r["choices"]))
        if r.get("context"):
            bits.append("context: " + r["context"])
        lines.append("- " + "; ".join(bits))
    return "\n".join(lines)


def answer_need(tid: str, need_id: str, text: str) -> dict[str, Any]:
    """The human's answer to one open need: mark it answered and route the text
    back to the asking lane as ln= steering (single destination, never broadcast)."""
    rec = _NEEDS.get(str(need_id or "").strip())
    if rec is None or rec["tid"] != tid:
        return {"ok": False, "error": f"unknown need_id {need_id!r}"}
    t = str(text or "").strip()
    if not t:
        return {"ok": False, "error": "answer needs text"}
    rec["status"] = "answered"
    rec["answer"] = t[:512]
    rec["answered_at"] = time.time()
    ln = queue_lane_steer(tid, rec["lane"], "answer: " + t[:480])
    publish(tid, {"kind": "lane_need_answered", "need_id": rec["need_id"],
                  "lane": rec["lane"], "answer": rec["answer"]})
    # NOTE: no call_lane.steer_lanes() mirror here on purpose. `ln=<lane>=answer:` (rail 1)
    # already reaches the lane's mind on the next /act turn; if that lane is a phone
    # call, IT decides what to say on the call via say_on_call. A second copy through
    # the call-steer rail would land the same user answer on the timeline twice.
    return {"ok": True, "need_id": rec["need_id"], "lane": ln, "routed": "ln-steer"}


def needs_for_lane(tid: str, lane: Optional[str], *, include_answered: bool = False,
                   limit: int = 5) -> list[dict[str, Any]]:
    """What is waiting for/answered to one lane — for R-lane prompt slicing."""
    out = []
    for r in _NEEDS.values():
        if r["tid"] != tid or normalize_lane(r["lane"]) != normalize_lane(lane):
            continue
        if r["status"] != "open" and not include_answered:
            continue
        out.append(r)
    out.sort(key=lambda r: r["asked_at"], reverse=True)
    return out[:limit]


# ── route_decision — the structured router rail (tool-validated) ─────────────

ROUTE_DECISIONS = ("chat", "steer", "new_task", "surface_need")


def route_decision(tid: str, decision: str, lane: Optional[str] = None,
                   instruction: str = "", need_id: str = "") -> dict[str, Any]:
    """Validate + apply one of L's router decisions as DATA, not prose.

    decision:
      chat          -> nothing to route; L answers in conversation.
      steer         -> EXACTLY ONE existing lane (validated against active
                       lanes). Unknown/missing lane is REFUSED with the live
                       list: this is what makes single-owner routing deterministic.
      new_task      -> L spawned a new R lane for a fresh task; nothing queued here.
      surface_need  -> narrate the open needs_user question for `lane` / `need_id`.
    """
    d = str(decision or "").strip().lower()
    t = str(instruction or "").strip()
    if d not in ROUTE_DECISIONS:
        return {"ok": False, "error": f"unknown decision {decision!r}; "
                                      "one of " + "|".join(ROUTE_DECISIONS)}
    if d == "chat":
        return {"ok": True, "decision": "chat", "queued": False}
    if d == "new_task":
        return {"ok": True, "decision": "new_task", "queued": False}
    if d == "surface_need":
        rows = open_needs(tid)
        hit = None
        if need_id and str(need_id).strip() in _NEEDS:
            hit = _NEEDS[str(need_id).strip()]
        else:
            ln = normalize_lane(lane)
            hit = next((r for r in rows if normalize_lane(r["lane"]) == ln), None) or \
                  (rows[0] if rows else None)
        if hit is None:
            return {"ok": False, "error": "no open needs_user question to surface"}
        return {"ok": True, "decision": "surface_need", "need": dict(hit), "queued": False}
    # d == "steer": one lane, and it must exist.
    ln = normalize_lane(lane)
    if not ln:
        return {"ok": False, "error": "steer needs lane=<lnID>; pick ONE owner "
                                      "(ambiguous -> ask the user, never broadcast)",
                "active_lanes": active_lanes(tid)}
    live = active_lanes(tid, limit=MAX_ACTIVE_LANES)
    if ln not in live:
        return {"ok": False, "error": f"lane {ln} is not an active lane on this thread",
                "active_lanes": live[:6],
                "hint": "steer to one lane above, or answer needs_user, or spawn a "
                        "new R lane (new_task). Never broadcast to all lanes."}
    if not t:
        return {"ok": False, "error": "steer needs instruction text"}
    queue_lane_steer(tid, ln, t)
    publish(tid, {"kind": "lane_route", "lane": ln, "instruction": t[:200]})
    return {"ok": True, "decision": "steer", "lane": ln, "queued": True}


# ── prompt rails consumed by persona_orchestrator._build_messages ────────────

def router_block() -> str:
    """L's per-turn routing contract — appended to the host system context."""
    return (
        "[lane routing] You are L, the only lobe the user speaks to directly. "
        "Execution lanes (R) share this timeline for awareness but MUST NOT act "
        "on a plain user message. Classify EVERY user message into exactly one "
        "of: respond-in-chat / steer-to-lane / spawn-new-R / surface-needs_user-"
        "question. Route as data, not vibes: call route_decision with "
        "{decision: chat|steer|new_task|surface_need, lane_id, instruction}, or "
        "emit steering as 'ln=<lane-id>=<instruction>'. A message that could "
        "apply to more than one lane gets ONE owner — the lane whose recent task "
        "context best matches — or you ask the user. NEVER broadcast the same "
        "instruction to several lanes. When a lane calls needs_user, its question "
        "appears below as [lane needs_user]: you MUST narrate it to the human in "
        "your next reply and never leave it unanswered; when the human answers, "
        "route the answer back to that lane only (answer_lane_need / "
        "ln=<lane>=answer: ...)."
    )


def lane_addressing_rules() -> str:
    """The static R-lane addressing contract (same text on the companion side)."""
    return (
        "[lane addressing] Execution lanes act ONLY on instructions addressed to "
        "them — a '[steering] ln=<your-lane-id>=...' line (or the x-sawii-steer "
        "header) — or on the task they were spawned for. A plain user message has "
        "no lane id: read it for awareness (shared mind), but do NOT start, "
        "redirect, or repeat work because of it. L owns routing. If you need "
        "something from the human, call the needs_user tool; the answer comes "
        "back to you as ln=<your-lane-id>=answer: ..."
    )


def lane_steering_block(tid: str) -> str:
    """R-lane contract + this lane's addressed instructions and own needs.

    Goes in every /act system prompt. Companion-side lanes honor the same
    `[steering] ln=<id>=...` rule through the shared timeline's meta.lobe notes
    (kernel/goal_agent.py _read_live_updates: adopt only instructions addressed
    to your own lane id; plain user turns belong to L).
    """
    rows = consume_lane_steers(tid)
    lines = [lane_addressing_rules()]
    for ln, txt in rows:
        lines.append("ln=" + (ln or "?") + "=" + txt[:480])
    return "\n".join(lines) if lines else ""


def maybe_expire_needs(tid: str) -> None:
    """Timeouts are advisory only: an expired need stays in `open_needs` until
    L answers the human's silence from context. Publishes lane_need_timeout once."""
    now = time.time()
    for r in _NEEDS.values():
        if r["tid"] != tid or r["status"] != "open" or not r.get("timeout_s"):
            continue
        if now - r["asked_at"] >= r["timeout_s"] and not r.get("_timeout_notified"):
            r["_timeout_notified"] = True
            publish(tid, {"kind": "lane_need_timeout", "need_id": r["need_id"],
                          "lane": r["lane"], "question": r["question"]})


def reset_bus() -> None:   # tests
    _SUBS.clear()
    _bus_seq.clear()
    _NEEDS.clear()
    _PENDING_STEERS.clear()
    _ACTIVE_LANES.clear()


__all__ = [
    "subscribe", "unsubscribe", "publish", "drain",
    "note_lane_activity", "active_lanes", "normalize_lane", "lane_addressed_to",
    "queue_lane_steer", "consume_lane_steers",
    "ask_user", "open_needs", "needs_block_for_prompt", "answer_need", "needs_for_lane",
    "route_decision", "ROUTE_DECISIONS",
    "router_block", "lane_steering_block", "lane_addressing_rules",
    "maybe_expire_needs", "reset_bus",
]
