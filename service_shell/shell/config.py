"""Configuration for the Hands Always-On Shell.

Loads service_shell/config.toml (stdlib tomllib on py3.11+), applies env overrides
(matches the DL-Companion env names used by backend/persona_client.py).
Every knob the founder asked to be configurable lives here.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

SHELL_ROOT = Path(__file__).resolve().parent.parent          # .../service_shell
VAR_DIR = SHELL_ROOT / "var"
STATE_DIR = VAR_DIR / "state"
LOG_DIR = VAR_DIR / "logs"

DEFAULT_CONFIG_PATH = SHELL_ROOT / "config.toml"

# Founder commitment: wake -> user-visible ack in under 1s. This constant is
# asserted by tests/test_wake_pipeline.py (measured mock audio + mock detector).
ACK_DEADLINE_S = 1.0

# == backend/persona_client.py HANDS_PERSONA_KEY (persona id 60). Env-overridable.
HANDS_PERSONA_DEFAULT_KEY = "sp_sltCBbGrfWzwyiQBUthGNQSE0NxbQNBy-PV673fH6U4"


def _default_tts_voice_cmd() -> list[str]:
    """One-shot SAPI speak via stdin. Launched detached fire-and-forget for the
    spoken ack during conversation streaming (opt-out: ack_tts = false)."""
    return ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
            "-Command",
            "Add-Type -AssemblyName System.Speech;"
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "$s.Rate=1;$s.Speak([Console]::In.ReadToEnd())"]


@dataclass
class WakeConfig:
    engine: str = "auto"               # auto|pvporcupine|openwakeword|pocketsphinx|energy_vad|simulated
    words: list[str] = field(default_factory=lambda: ["hey hands", "hey tasker", "hey operator"])
    # keyword-spotting fuzzy accept list (pocketsphinx/energy paths): a provisional ASR
    # hypothesis counts as a wake if it contains/ends with any of these phrases.
    fuzzy_words: list[str] = field(default_factory=lambda: [
        "hey hands", "hey hand", "hey tasks", "hey tasker", "hey operator",
        "hands", "hand it", "on hands", "in hands"])
    sim_prebuilt_keyword: str = ""     # pre-built Porcupine .ppn for "hey hands" (picovoice console)
    sim_access_key: str = ""           # Picovoice access key (porcupine engine only)
    buffer_ms: int = 600               # sliding window fed to the detector per decision
    threshold: float = 0.55            # engine score cut (ps posterior / oww sigmoid / energy)
    energy_floor: float = 90.0         # RMS gate (int16 counts) below which detector is skipped
    oww_model_paths: list[str] = field(default_factory=list)  # extra custom "hey hands" models
    vad_aggressiveness: int = 2        # webrtcvad 0..3


@dataclass
class ContextConfig:
    poll_interval_s: float = 20.0      # steady-state ambient sampling period
    on_change: bool = True             # fast-poll (2s) while the foreground app/title is unstable
    history_len: int = 40              # ring size of activity samples -> "user task signature"
    max_summary_chars: int = 1200      # cap on the in-memory summary handed to /intent
    opt_in_screenshots: bool = False   # NEVER default-on; capture is a stub in this build
    opt_in_persist_jsonl: bool = False  # rolling JSONL written only when the user flips this
    persist_path: str = "var/state/context.jsonl"
    persist_max_bytes: int = 512_000   # rotate at 512 KB
    persist_keep: int = 3              # keep context.jsonl.1..N


@dataclass
class PersonaBackendConfig:
    base_url: str = "http://127.0.0.1:8000"
    health_path: str = "/"             # Tasker backend GET / -> {'message': <now>} (200 when alive)
    act_path_template: str = "/aiagent/persona/{tid}/act"
    thread_id: str = ""                # empty => always take the persona-direct path
    token: str = ""                    # Bearer JWT; the act route is auth-guarded
    timeout_s: float = 12.0


@dataclass
class PersonaDirectConfig:
    base_url: str = "https://dl-companion-production.up.railway.app"
    api_key: str = HANDS_PERSONA_DEFAULT_KEY
    model: str = "sawii-persona"
    timeout_s: float = 90.0


@dataclass
class HttpConfig:
    host: str = "127.0.0.1"
    port: int = 5117                   # ref-impl used by /api/v1/presence doctor probe test
    listen_voice_port: int = 5118      # optional --listen-voice lane (stub, see README)
    context_prefix_max_chars: int = 1200  # cap on injected ambient block


@dataclass
class ShellConfig:
    wake: WakeConfig = field(default_factory=WakeConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    backend: PersonaBackendConfig = field(default_factory=PersonaBackendConfig)
    persona: PersonaDirectConfig = field(default_factory=PersonaDirectConfig)
    http: HttpConfig = field(default_factory=HttpConfig)
    ack_sound: bool = True             # winsound beep at wake (instant)
    ack_tts: bool = True               # spoken "Yes?" one-shot (still <1s to first sound)
    tts_voice_cmd: list[str] = field(default_factory=_default_tts_voice_cmd)
    exec_tools: bool = True            # report tool_calls to task-executor if reachable (else parked)
    task_executor_url: str = ""        # POST {tool_call} here when an executor exists
    log_level: str = "INFO"
    config_path: Path = DEFAULT_CONFIG_PATH

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "ShellConfig":
        cfg = cls()
        p = Path(path) if path else DEFAULT_CONFIG_PATH
        cfg.config_path = p
        if p.exists():
            with open(p, "rb") as f:
                raw = tomllib.load(f)
            _apply(cfg, raw)
        # env overrides: same names backend/persona_client.py reads (ctx-verified)
        cfg.persona.base_url = os.getenv("SAWII_PERSONA_URL", cfg.persona.base_url).rstrip("/") or cfg.persona.base_url
        cfg.persona.api_key = os.getenv("SAWII_PERSONA_KEY", cfg.persona.api_key) or HANDS_PERSONA_DEFAULT_KEY
        cfg.backend.base_url = os.getenv("HANDS_SHELL_BACKEND_URL", cfg.backend.base_url).rstrip("/")
        cfg.backend.thread_id = os.getenv("HANDS_SHELL_THREAD_ID", cfg.backend.thread_id)
        cfg.backend.token = os.getenv("HANDS_SHELL_BACKEND_TOKEN", cfg.backend.token)
        cfg.http.port = int(os.getenv("HANDS_SHELL_PORT", cfg.http.port))
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        return cfg


_SECTIONS = ("wake", "context", "backend", "persona", "http")


def _apply(cfg: ShellConfig, raw: dict) -> None:
    for name in _SECTIONS:
        sec = raw.get(name)
        if isinstance(sec, dict):
            target = getattr(cfg, name)
            for k, v in sec.items():
                if hasattr(target, k):
                    setattr(target, k, v)
    for k in ("ack_sound", "ack_tts", "exec_tools", "log_level", "task_executor_url"):
        if k in raw:
            setattr(cfg, k, raw[k])
    if isinstance(raw.get("tts_voice_cmd"), list):
        cfg.tts_voice_cmd = [str(x) for x in raw["tts_voice_cmd"]]
    cfg.wake.words = [w.strip().lower() for w in cfg.wake.words if str(w).strip()]
    if not cfg.wake.words:
        cfg.wake.words = ["hey hands"]


__all__ = ["ShellConfig", "ACK_DEADLINE_S", "SHELL_ROOT", "VAR_DIR", "STATE_DIR", "LOG_DIR",
           "HANDS_PERSONA_DEFAULT_KEY"]
