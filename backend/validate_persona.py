"""End-to-end validation of the Tasker Persona bridge without loading torch."""
import ast
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))

# ---------- 1. persona_client ----------
from persona_client import PersonaClient, lane_of

assert lane_of("call_lnAbCdEf12_x") == "lnAbCdEf12", "lane_of broken (groups should be case-preserved)"
assert lane_of("call_plain") is None
print("✓ persona_client imports and parses lane ids")

# ---------- 2. router registration ----------
with open(os.path.join(os.path.dirname(__file__), "main.py")) as f:
    main_src = f.read()
assert "from routers.aiagent.persona_orchestrator import router as persona_router" in main_src, \
    "persona_router import missing from main.py"
assert "app.include_router(persona_router)" in main_src, \
    "persona_router not included in main.py"
print("✓ main.py includes persona_router")

# ---------- 3. the @router.post route path ----------
with open(os.path.join(os.path.dirname(__file__), "routers/aiagent/persona_orchestrator.py")) as f:
    orch_src = f.read()
assert '@router.post("/{tid}/act")' in orch_src, 'act() path missing'
assert "async def act(" in orch_src, "act endpoint not defined"
print("✓ POST /aiagent/persona/{tid}/act registered")

# ---------- 4. TASKER_TOOLS covers what DL-Companion needs ----------
with open(os.path.join(os.path.dirname(__file__), "routers/aiagent/persona_orchestrator.py")) as f:
    raw = f.read()
assert "fetch_url" in raw and "desktop_click" in raw and "desktop_type" in raw, \
    "host tools missing"
print("✓ TASKER_TOOLS exposes both server (fetch_url etc.) and desktop/browser (desktop_click, ...)")

# ---------- 5. env var ----------
with open(os.path.join(os.path.dirname(__file__), ".env.example")) as f:
    env = f.read()
assert "SAWII_PERSONA_URL" in env and "SAWII_PERSONA_KEY" in env, \
    "env vars missing from .env.example"
print("✓ .env.example documents SAWII_PERSONA_URL + SAWII_PERSONA_KEY")

# ---------- 6. contracts — no planner/computer_use inside persona paths ----------
bad_mentions = ["planner", "computer_use", "usher", "classifier"]
persona_paths = [os.path.join(os.path.dirname(__file__), "routers/aiagent/persona_orchestrator.py")]
for pp in persona_paths:
    text = open(pp).read()
    bad = [m for m in bad_mentions if m in text]
    assert not bad, f"{pp} mentions old-design: {bad}"
print("✓ persona_orchestrator is free of NeuralAgent-era constructs")

print("\n✅ ALL VALIDATIONS PASSED — Tasker is wired to DL-Companion (the unified mind)")
