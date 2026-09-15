import base64
import time
import requests
import pyautogui
import mss
import os
import subprocess
import platform
from io import BytesIO
from PIL import Image
import webbrowser
import sys
import io
import pyperclip
import unicodedata
import json
import asyncio
import logging
import ui_extraction


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

def type_unicode_smart(text: str, delay: float = 0.05) -> None:
    try:
        text.encode("ascii")

        for idx, line in enumerate(text.split("\n")):
            pyautogui.write(line, interval=delay)
            if idx < len(text.split("\n")) - 1:
                pyautogui.hotkey("shift", "enter")
        return
    except UnicodeEncodeError:
        pass

    old_clip = pyperclip.paste()

    pyperclip.copy(text)
    for _ in range(20):
        if pyperclip.paste() == text:
            break
        time.sleep(0.05)

    hotkey = ("command", "v") if sys.platform == "darwin" else ("ctrl", "v")
    pyautogui.hotkey(*hotkey)
    time.sleep(0.05)

    pyperclip.copy(old_clip)

def windows_direct_app_launch(app_name):
    try:
        subprocess.Popen(f'start "" "{app_name}"', shell=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[❌] Failed to launch with 'start': {e}")
        return False
    except Exception as e:
        print(f"[❌] Unexpected error with 'start': {e}")
        return False

def launch_application(app_name):
    os_name = platform.system().lower()
    try:
        if os_name == 'windows':
            if windows_direct_app_launch(app_name):
                return

            ps_command = f"powershell -Command \"Get-StartApps | Where-Object {{$_.Name -like '*{app_name}*'}} | Select-Object -First 1 -ExpandProperty AppId\""
            result = subprocess.run(ps_command, capture_output=True, text=True, shell=True)
            app_id = result.stdout.strip()
            if app_id:
                subprocess.Popen(f'explorer.exe shell:AppsFolder\\{app_id}', shell=True)
                return
            print("❌ App not found via UWP or direct command.")

        elif os_name == 'darwin':
            subprocess.Popen(["open", "-a", app_name])

        elif os_name == 'linux':
            subprocess.Popen([app_name])

    except Exception as e:
        print(f"❌ Could not launch {app_name}: {e}")

def focus_app(app_name):
    os_name = platform.system().lower()

    if os_name == "windows":
        try:
            import win32gui
            import win32con
            import win32api

            def enum_handler(hwnd, match_hwnds):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if app_name.lower() in title.lower():
                        match_hwnds.append(hwnd)

            match_hwnds = []
            win32gui.EnumWindows(lambda hwnd, _: enum_handler(hwnd, match_hwnds), None)

            for hwnd in match_hwnds:
                try:
                    # Check if already in foreground
                    if hwnd == win32gui.GetForegroundWindow():
                        return True  # Already focused, don't touch

                    # Only restore if minimized
                    if win32gui.IsIconic(hwnd):
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

                    # Simulate ALT key to bypass foreground lock
                    win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)  # Alt down
                    win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)  # Alt up
                    time.sleep(0.05)

                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.1)

                    if hwnd == win32gui.GetForegroundWindow():
                        return True
                except Exception as e:
                    print(f"[❌] Failed to focus window: {e}")
            print(f"[⚠️] No visible window matched: {app_name}")
        except ImportError:
            print("[❌] pywin32 is not installed. Install it via `pip install pywin32`.")

    elif os_name == "darwin":
        try:
            subprocess.run(["osascript", "-e", f'tell application "{app_name}" to activate'], check=True)
            return True
        except subprocess.CalledProcessError:
            print(f"[❌] Could not focus macOS app: {app_name}")

    elif os_name == "linux":
        try:
            # Try wmctrl first
            result = subprocess.run(["wmctrl", "-a", app_name], check=True)
            return result.returncode == 0
        except FileNotFoundError:
            print("❌ wmctrl is not installed. Try `sudo apt install wmctrl`.")
        except subprocess.CalledProcessError:
            print(f"[⚠️] wmctrl failed, trying xdotool for app: {app_name}")
            try:
                subprocess.run(["xdotool", "search", "--name", app_name, "windowactivate"], check=True)
                return True
            except Exception:
                print(f"[❌] Could not focus Linux app: {app_name}")

    return False

def take_screenshot_b64():
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        img = img.resize((1280, 720))
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

def safe_coords(x, y, screen_width, screen_height):
    return max(1, min(screen_width - 1, x)), max(1, min(screen_height - 1, y))

def perform_action(response):
    global screenshot_requested
    actions = response.get("actions", [])
    TARGET_W, TARGET_H = 1280, 720
    screen_w, screen_h = pyautogui.size()
    scale_x = screen_w / TARGET_W
    scale_y = screen_h / TARGET_H

    def scale_coords(coord):
        x = int(coord["x"] * scale_x)
        y = int(coord["y"] * scale_y)
        return safe_coords(x, y, screen_w, screen_h)

    for action in actions:
        try:
            act = action["action"]
            params = action.get("params", {})

            if act in ["left_click", "double_click", "triple_click", "right_click"]:
                x, y = scale_coords(params)
                pyautogui.moveTo(x, y)

                click_config = {
                    "left_click": ("left", 1),
                    "double_click": ("left", 2),
                    "triple_click": ("left", 3),
                    "right_click": ("right", 1),
                }

                button, clicks = click_config[act]
                pyautogui.click(button=button, clicks=clicks, interval=0.1)
            
            elif act == 'click':
                # Consider it as left click
                x, y = scale_coords(params)
                pyautogui.moveTo(x, y)
                pyautogui.click(button='left')

            elif act == "mouse_move":
                x, y = scale_coords(params)
                pyautogui.moveTo(x, y, duration=0.1)

            elif act == "left_click_drag":
                x1, y1 = scale_coords(params["from"])
                x2, y2 = scale_coords(params["to"])
                pyautogui.moveTo(x1, y1)
                pyautogui.mouseDown()
                pyautogui.moveTo(x2, y2, duration=0.3)
                pyautogui.mouseUp()

            elif act == "left_mouse_down":
                pyautogui.mouseDown()
            elif act == "left_mouse_up":
                pyautogui.mouseUp()

            elif act == "key":
                pyautogui.press(params["text"])
            
            elif act == "key_combo":
                keys = params.get("keys", [])
                if keys:
                    pyautogui.hotkey(*keys)

            elif act == "type":
                if params.get("replace", False):
                    pyautogui.hotkey("ctrl", "a" if sys.platform != "darwin" else "command")
                    pyautogui.press("backspace")
                
                type_unicode_smart(params["text"], delay=0.05)

            elif act == "hold_key":
                pyautogui.keyDown(params["text"])
                time.sleep(float(params.get("duration", 1.0)))
                pyautogui.keyUp(params["text"])

            elif act == "scroll":
                x, y = scale_coords({"x": params["x"], "y": params["y"]})
                pyautogui.moveTo(x, y, duration=0.1)
                direction = params.get("scroll_direction", "down")
                amount = params.get("scroll_amount", 3)
                if direction == "down":
                    pyautogui.scroll(-100 * amount)
                elif direction == "up":
                    pyautogui.scroll(100 * amount)
                elif direction == "left":
                    pyautogui.hscroll(-100 * amount)
                elif direction == "right":
                    pyautogui.hscroll(100 * amount)

            elif act == "wait":
                time.sleep(params.get("duration", 1))

            elif act == "launch_browser":
                webbrowser.open(params["url"])

            elif act == "launch_app":
                launch_application(params["app_name"])
            
            elif act == "focus_app":
                focus_app(params["app_name"])

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


def get_next_step():
    global screenshot_requested
    url = os.getenv('NEURALAGENT_API_URL') + '/aiagent/' + os.getenv('NEURALAGENT_THREAD_ID') + '/next_step'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + os.getenv('NEURALAGENT_USER_ACCESS_TOKEN'),
    }

    interactive_elements = ui_extraction.extract_interactive_elements()
    running_apps = ui_extraction.get_running_apps()

    # Automatically trigger screenshot if WebView is present
    has_webview = any(e.get("type") == "PossibleWebView" for e in interactive_elements)
    should_send_screenshot = screenshot_requested or has_webview

    payload = {
        'current_os': 'MacOS' if platform.system() == 'darwin' else platform.system(),
        'current_interactive_elements': interactive_elements,
        'current_running_apps': running_apps,
    }

    if should_send_screenshot:
        payload['screenshot_b64'] = take_screenshot_b64()
        screenshot_requested = False

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in (200, 201, 202):
            return response.json()
    except Exception as e:
        print(f"[❌] Error sending next step request: {e}")
    
    return None

def get_current_subtask():
    url = os.getenv('NEURALAGENT_API_URL') + '/aiagent/' + os.getenv('NEURALAGENT_THREAD_ID') + '/current_subtask'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + os.getenv('NEURALAGENT_USER_ACCESS_TOKEN'),
    }
    payload = {
        'current_os': 'MacOS' if platform.system() == 'darwin' else platform.system(),
        'current_interactive_elements': ui_extraction.extract_interactive_elements(),
        'current_running_apps': ui_extraction.get_running_apps(),
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in (200, 201, 202):
            return response.json()
    except:
        pass
    return None

async def main_loop():
    while True:
        current_subtask_response = get_current_subtask()
        if not current_subtask_response:
            continue

        if current_subtask_response.get('action') == 'task_completed':
            break

        action_response = get_next_step()
        print("NeuralAgent Next Step Response:", action_response)

        if not action_response:
            continue

        if any(a['action'] in ['task_completed', 'subtask_failed'] for a in action_response.get('actions', [])):
            break

        perform_action(action_response)

if __name__ == "__main__":
    asyncio.run(main_loop())
