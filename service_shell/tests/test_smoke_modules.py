"""Smoke: every shell module compiles AND imports with the real symbols main
expects. No mic, no network, no tray — pure imports + symbol presence."""
from __future__ import annotations

import importlib
import py_compile
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent          # service_shell/
sys.path.insert(0, str(ROOT))

MODULES = ["shell", "shell.audio", "shell.chain", "shell.config",
           "shell.context", "shell.httpd", "shell.notify", "shell.persona",
           "shell.tray", "shell.wake"]

NEEDED = {  # exact symbols main.py wires (typo guard against drift)
    "shell.audio": ["MicSource", "silence_frames", "synthetic_speech_frames"],
    "shell.chain": ["Chain"],
    "shell.config": ["ACK_DEADLINE_S", "ShellConfig"],
    "shell.context": ["ContextSampler"],
    "shell.httpd": ["ShellAPI"],
    "shell.notify": ["acknowledge", "configure_tts", "notify"],
    "shell.tray": ["TrayPresence"],
    "shell.wake": ["PsEngine", "SimulatedEngine", "WakePipeline", "build_engine"],
}


@pytest.mark.parametrize("mod", MODULES)
def test_module_compiles(mod: str):
    f = ROOT.joinpath(*mod.split("."))
    f = f / "__init__.py" if f.is_dir() else f.with_suffix(".py")
    py_compile.compile(str(f), doraise=True)           # SyntaxError -> test fail


@pytest.mark.parametrize("mod", MODULES)
def test_module_imports(mod: str):
    importlib.import_module(mod)


@pytest.mark.parametrize("mod, names", list(NEEDED.items()))
def test_symbols_present(mod: str, names: list):
    m = importlib.import_module(mod)
    for n in names:
        assert hasattr(m, n), f"{mod}.{n} missing (main.py wires this)"


def test_main_imports_as_module():
    """main.py must import cleanly (its __main__ guard must not fire)."""
    m = importlib.import_module("main")
    for fn in ("ShellApp", "sim_say", "context_once", "main"):
        assert hasattr(m, fn)
