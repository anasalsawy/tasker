import base64
import time
import requests
import os
import subprocess
from io import BytesIO
from PIL import Image
import sys
import io
import asyncio
import logging
import urllib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
    encoding="utf-8",
)

screenshot_requested = False

def take_screenshot_b64():
    """Capture, resize, and return screenshot as base64 string without saving to disk."""
    proc = subprocess.Popen(["scrot", "-q", "60", "-"], stdout=subprocess.PIPE)
    image = Image.open(proc.stdout).convert("RGB")
    # image = image.resize((800, 500))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=60)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def safe_coords(x, y, screen_width, screen_height):
    return max(1, min(screen_width - 1, x)), max(1, min(screen_height - 1, y))

def run_xdotool(*args):
    try:
        subprocess.run(['xdotool', *args], check=True)
    except Exception as e:
        print(f"❌ xdotool error: {e}")

def open_new_tab(url):
    try:
        encoded_url = urllib.parse.quote(url, safe='')
        response = requests.put(f"{os.getenv('BROWSER_CDP_URL', 'http://127.0.0.1:13783')}/json/new?{encoded_url}")
        response.raise_for_status()
        print(f"✅ Opened new tab: {url}")
    except Exception as e:
        print(f"❌ Failed to open new tab: {e}")

def perform_action(response):
    global screenshot_requested
    actions = response.get("actions", [])
    TARGET_W, TARGET_H = 800, 500
    screen_w, screen_h = 1280, 720

    scale_x = screen_w / TARGET_W
    scale_y = screen_h / TARGET_H

    def scale_coords(coord):
        # x = int(coord["x"] * scale_x)
        # y = int(coord["y"] * scale_y)
        return safe_coords(coord["x"], coord["y"], screen_w, screen_h)

    for action in actions:
        try:
            act = action["action"]
            params = action.get("params", {})

            if act in ["left_click", "double_click", "triple_click", "right_click"]:
                x, y = scale_coords(params)
                run_xdotool("mousemove", str(x), str(y))
                click_map = {
                    "left_click": ["click", "1"],
                    "double_click": ["click", "--repeat", "2", "1"],
                    "triple_click": ["click", "--repeat", "3", "1"],
                    "right_click": ["click", "3"],
                }
                run_xdotool(*click_map[act])

            elif act == 'click':
                x, y = scale_coords(params)
                run_xdotool("mousemove", str(x), str(y))
                run_xdotool("click", "1")

            elif act == "mouse_move":
                x, y = scale_coords(params)
                run_xdotool("mousemove", str(x), str(y))

            elif act == "left_click_drag":
                x1, y1 = scale_coords(params["from"])
                x2, y2 = scale_coords(params["to"])
                run_xdotool("mousemove", str(x1), str(y1))
                run_xdotool("mousedown", "1")
                run_xdotool("mousemove", str(x2), str(y2))
                run_xdotool("mouseup", "1")

            elif act == "left_mouse_down":
                run_xdotool("mousedown", "1")

            elif act == "left_mouse_up":
                run_xdotool("mouseup", "1")

            elif act == "key":
                run_xdotool("key", params["text"])

            elif act == "key_combo":
                keys = params.get("keys", [])
                if keys:
                    run_xdotool("key", "+".join(keys))

            elif act == "type":
                if params.get("replace", False):
                    run_xdotool("key", "ctrl+a", "BackSpace")
                run_xdotool("type", params["text"])

            elif act == "hold_key":
                run_xdotool("keydown", params["text"])
                time.sleep(float(params.get("duration", 1.0)))
                run_xdotool("keyup", params["text"])

            elif act == "scroll":
                x, y = scale_coords({"x": params["x"], "y": params["y"]})
                run_xdotool("mousemove", str(x), str(y))
                direction = params.get("scroll_direction", "down")
                amount = int(params.get("scroll_amount", 3))
                button = {
                    "up": "4", "down": "5", "left": "6", "right": "7"
                }.get(direction, "5")
                for _ in range(amount):
                    run_xdotool("click", button)

            elif act == "wait":
                time.sleep(params.get("duration", 1))

            elif act == "launch_browser":
                open_new_tab(params["url"])

            elif act == "tool_use":
                print(f"🛠️ Tool requested: {params}")

            elif act == "request_screenshot":
                screenshot_requested = True

            elif act == "subtask_completed":
                print("✅ Subtask completed.")

            elif act == "subtask_failed":
                print("❌ Subtask failed.")

            else:
                print(f"⚠️ Unknown action: {act}")
        except Exception as e:
            print("❌ Exception in perform_action:", e)


def get_chrome_tabs():
    try:
        response = requests.get(f'{os.getenv('BROWSER_CDP_URL')}/json')
        response.raise_for_status()
        tabs = response.json()

        open_tabs = []
        for tab in tabs:
            if tab.get("type") == "page" and tab.get("url") and tab.get("url") != "about:blank":
                open_tabs.append({
                    "title": tab.get("title"),
                    "url": tab.get("url"),
                    "id": tab.get("id"),
                    "webSocketDebuggerUrl": tab.get("webSocketDebuggerUrl")
                })

        return open_tabs
    
    except Exception as e:
        print("❌ Failed to get Chrome tabs:", e)
        return []


def get_next_step():
    global screenshot_requested
    url = os.getenv('NEURALAGENT_API_URL') + '/aiagent/background/' + os.getenv('NEURALAGENT_THREAD_ID') + '/next_step'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + os.getenv('NEURALAGENT_USER_ACCESS_TOKEN'),
    }

    tabs = get_chrome_tabs()
    if tabs:
        print("Open Tabs:")
        for i, tab in enumerate(tabs):
            print(f"Tab {i+1}: {tab['title']} → {tab['url']}")
        
        current_url = tabs[0]['url']
        print("\n✅ Current tab URL:", current_url)
    else:
        print("No tabs found or Chrome not running.")

    payload = {
        'current_open_tabs': tabs,
        'current_url': current_url,
        'screenshot_b64': take_screenshot_b64(),
    }

    screenshot_requested = False

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in (200, 201, 202):
            return response.json()
    except Exception as e:
        print(f"[❌] Error sending next step request: {e}")
    
    return None

async def main_loop():
    while True:
        action_response = get_next_step()
        print("NeuralAgent Next Step Response:", action_response)

        if not action_response:
            continue

        if any(a['action'] in ['task_completed', 'task_failed'] for a in action_response.get('actions', [])) and len(action_response.get('actions', [])) == 1:
            break

        perform_action(action_response)

if __name__ == "__main__":
    asyncio.run(main_loop())
