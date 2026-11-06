"""Command-line interface for the local Tasker desktop agent."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

import requests


ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
DESKTOP_DIR = ROOT / "desktop"
AGENT_SCRIPT = DESKTOP_DIR / "aiagent" / "main.py"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"


class TaskerCLIError(RuntimeError):
    pass


def _api_error(response: requests.Response) -> str:
    try:
        payload = response.json()
        return str(payload.get("message") or payload.get("detail") or payload)
    except ValueError:
        return response.text.strip() or f"HTTP {response.status_code}"


def _request(method: str, url: str, **kwargs) -> requests.Response:
    try:
        response = requests.request(method, url, timeout=kwargs.pop("timeout", 180), **kwargs)
    except requests.RequestException as exc:
        raise TaskerCLIError(f"Could not contact Tasker: {exc}") from exc
    if not response.ok:
        raise TaskerCLIError(f"Tasker returned HTTP {response.status_code}: {_api_error(response)}")
    return response


def _backend_ready(base_url: str) -> bool:
    try:
        return requests.get(base_url + "/", timeout=2).ok
    except requests.RequestException:
        return False


def _start_backend(base_url: str) -> subprocess.Popen:
    if base_url.rstrip("/") != DEFAULT_BACKEND_URL:
        raise TaskerCLIError("Automatic startup is available only for the default local backend URL.")

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    process = subprocess.Popen(
        command,
        cwd=BACKEND_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    print("Starting the Tasker backend", end="", flush=True)
    for _ in range(60):
        if _backend_ready(base_url):
            print(" ready.")
            return process
        if process.poll() is not None:
            raise TaskerCLIError("The Tasker backend exited during startup.")
        print(".", end="", flush=True)
        time.sleep(2)
    print()
    raise TaskerCLIError("Timed out waiting for the Tasker backend to start.")


def _local_login(base_url: str) -> str:
    response = _request("POST", base_url + "/apps/auth/dev_login", timeout=30)
    token = response.json().get("token")
    if not token:
        raise TaskerCLIError("The local login response did not contain an access token.")
    return token


def _run_agent(base_url: str, token: str, thread_id: str) -> int:
    env = os.environ.copy()
    env.update(
        {
            "NEURALAGENT_API_URL": base_url,
            "NEURALAGENT_THREAD_ID": thread_id,
            "NEURALAGENT_USER_ACCESS_TOKEN": token,
            "PYTHONUTF8": "1",
        }
    )
    print("Tasker is controlling the desktop. Press Ctrl+C to stop.")
    process = subprocess.Popen([sys.executable, str(AGENT_SCRIPT)], cwd=DESKTOP_DIR, env=env)
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        raise


def run_task(
    base_url: str,
    token: str,
    task: str,
    thinking: bool = False,
    thread_id: str | None = None,
) -> tuple[int, str | None]:
    headers = {"Authorization": "Bearer " + token}
    endpoint = (
        f"{base_url}/apps/threads/{thread_id}/send_message"
        if thread_id
        else base_url + "/apps/threads"
    )
    text_field = "text" if thread_id else "task"
    response = _request(
        "POST",
        endpoint,
        headers=headers,
        json={
            text_field: task,
            "background_mode": False,
            "extended_thinking_mode": thinking,
        },
    )
    result = response.json()
    reply = result.get("response")
    if reply:
        print(f"Tasker: {reply}")

    if result.get("type") != "desktop_task":
        return 0, thread_id or result.get("thread_id")

    thread_id = thread_id or result.get("thread_id")
    if not thread_id:
        raise TaskerCLIError("Tasker classified a desktop task without returning a thread ID.")

    try:
        exit_code = _run_agent(base_url, token, thread_id)
    except KeyboardInterrupt:
        try:
            _request(
                "POST",
                f"{base_url}/apps/threads/{thread_id}/cancel_task",
                headers=headers,
                timeout=15,
            )
        except TaskerCLIError:
            pass
        print("\nTask canceled.")
        return 130, thread_id

    if exit_code:
        raise TaskerCLIError(f"The desktop agent exited with code {exit_code}.")
    print("Task completed.")
    return 0, thread_id


def _interactive(base_url: str, token: str, thinking: bool) -> int:
    thread_id = None
    print("Tasker CLI")
    print("Interactive desktop agent session. Type /help for commands.\n")
    while True:
        try:
            prompt = f"tasker[{thread_id[:8]}]> " if thread_id else "tasker> "
            task = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not task:
            continue
        command = task.lower()
        if command in {"exit", "quit", ":q", "/exit", "/quit"}:
            return 0
        if command == "/help":
            print("/new             start a fresh conversation thread")
            print("/status          show backend, thread, and thinking status")
            print("/thinking on     enable extended thinking")
            print("/thinking off    disable extended thinking")
            print("/exit             quit Tasker CLI")
            print("Ctrl+C            stop the running desktop task")
            continue
        if command == "/new":
            thread_id = None
            print("Started a new Tasker conversation.")
            continue
        if command == "/status":
            print(f"backend:  {base_url}")
            print(f"thread:   {thread_id or '(new)'}")
            print(f"thinking: {'on' if thinking else 'off'}")
            continue
        if command in {"/thinking on", "/thinking off"}:
            thinking = command.endswith("on")
            print(f"Extended thinking {'enabled' if thinking else 'disabled'}.")
            continue
        if task.startswith("/"):
            print(f"Unknown command: {task}. Type /help.")
            continue
        try:
            _, thread_id = run_task(base_url, token, task, thinking, thread_id)
        except TaskerCLIError as exc:
            print(f"Error: {exc}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tasker",
        description="Run Tasker desktop automation tasks without Electron.",
    )
    parser.add_argument("task", nargs="*", help="Task to execute. Omit for interactive mode.")
    parser.add_argument(
        "--backend-url",
        default=os.getenv("TASKER_BACKEND_URL", DEFAULT_BACKEND_URL),
        help="Tasker backend URL (default: %(default)s).",
    )
    parser.add_argument("--thinking", action="store_true", help="Enable extended-thinking mode.")
    parser.add_argument(
        "--no-start-backend",
        action="store_true",
        help="Fail instead of automatically starting a missing local backend.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_url = args.backend_url.rstrip("/")
    try:
        if not _backend_ready(base_url):
            if args.no_start_backend:
                raise TaskerCLIError(f"No Tasker backend is responding at {base_url}.")
            _start_backend(base_url)
        token = _local_login(base_url)
        task = " ".join(args.task).strip()
        if task:
            return run_task(base_url, token, task, args.thinking)[0]
        return _interactive(base_url, token, args.thinking)
    except TaskerCLIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
