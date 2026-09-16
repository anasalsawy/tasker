# Tasker

Tasker is a Tasker-branded continuation of the public NeuralAgent desktop automation codebase.

The initial application structure is inherited from https://github.com/skyiron/neuralagentAI:

- FastAPI backend
- Electron desktop shell
- React desktop UI
- Python desktop agent using pyautogui, mss, and native UI extraction
- planner and computer-use model paths
- foreground and background desktop execution

Tasker adds an opt-in dual-lobe execution layer on top of that loop:

- Lobe A executes the accepted action batch.
- Lobe B prepares the next batch through a stateless look-ahead request.
- A continuous screen observer records the transition while A runs.
- B is handed off only after the observed boundary passes the selected policy.
- B is committed to task state only after its actions execute.
- A rejected prediction falls back to the inherited NeuralAgent request path.

See docs/tasker-dual-lobe.md for the protocol, profiles, and control condition.

## Repository

- GitHub: https://github.com/anasalsawy/tasker
- Branch policy: main only
- Upstream base: https://github.com/skyiron/neuralagentAI

## Install on Windows without a virtual environment

Tasker uses your normal persistent Python installation. Do not create or activate a virtual environment.

Prerequisites: Git, Python 3.11+ with the Windows launcher (py), and Node.js/npm.

Open PowerShell and run:

    cd C:\Projects
    git clone https://github.com/anasalsawy/tasker.git
    cd tasker
    py -m pip install -r backend\requirements.txt
    py -m pip install -r desktop\aiagent\requirements.txt

Install the Electron and React dependencies:

    cd desktop
    npm install
    cd neuralagent-app
    npm install
    cd ..\..

Create both environment files. Fill in the backend database and model/provider values; the frontend file points the desktop UI at the local backend:

    Copy-Item backend\.env.example backend\.env
    Copy-Item desktop\neuralagent-app\.env.example desktop\neuralagent-app\.env
    notepad backend\.env
    notepad desktop\neuralagent-app\.env

The frontend .env should contain:

    REACT_APP_PROTOCOL=http
    REACT_APP_WEBSOCKET_PROTOCOL=ws
    REACT_APP_DNS=127.0.0.1:8000
    REACT_APP_API_KEY=
    REACT_APP_DEV_AUTH_BYPASS=false

For local agent testing without an account, set both of these flags to true:

    TASKER_DEV_AUTH_BYPASS=true
    REACT_APP_DEV_AUTH_BYPASS=true

This creates a local development user and opens Tasker directly. Do not enable this on a shared or production backend.

After the PostgreSQL values are configured in backend\.env, create/update the database schema:

    cd backend
    py -m alembic upgrade head

Start the backend in this PowerShell window:

    py -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

Open a second PowerShell window and start the Tasker desktop app:

    cd C:\Projects\tasker\desktop
    npm start

The Electron development launcher invokes the persistent system Python interpreter. Set TASKER_PYTHON only if Windows has more than one Python installation, for example:

    $env:TASKER_PYTHON = "C:\Path\To\python.exe"

## Dual-lobe settings

Screen-aware is the default:

    $env:TASKER_DUAL_LOBE_PROFILE = "screen-aware"

Use the single-loop control condition:

    $env:TASKER_DUAL_LOBE_PROFILE = "off"

Additional settings are documented in docs/tasker-dual-lobe.md.

## Status and validation

The dual-lobe coordinator has unit tests for concurrent look-ahead, post-execution commit ordering, and boundary rejection:

    cd desktop\\aiagent
    py -m unittest test_dual_lobe.py

Those tests validate the coordinator mechanics only. They are not a provider benchmark and do not claim a real model call. Live validation requires a configured backend provider, credentials, and a desktop session.

## Safety

Tasker can control the user's mouse and keyboard. Use a test account and review model/provider settings before enabling live execution.
