# Tasker

Tasker is the Tasker-branded continuation of the NeuralAgent desktop automation codebase.

The initial implementation preserves NeuralAgent's existing architecture:

- FastAPI backend
- Electron desktop shell
- React desktop UI
- Python desktop agent using pyautogui, mss, and UI extraction
- planner and computer-use model paths

The next layer adds dual-lobe execution on top of that loop: one lobe plans the next safe action batch while the execution lobe performs the current batch, with explicit state, predicted boundaries, and screen-aware verification.

Upstream base: https://github.com/skyiron/neuralagentAI

This repository uses one branch: `main`.

## Status

The repository is being migrated from the upstream codebase before the dual-lobe layer is added. No deterministic demo is presented as proof of real model-backed execution. Live validation requires a configured provider, credentials, and a desktop session.

## Safety

Tasker can control the user's mouse and keyboard. Use a test account and review model/provider settings before enabling live execution.
