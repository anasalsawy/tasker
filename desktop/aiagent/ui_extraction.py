import platform
import pyautogui
import psutil
import os

if platform.system() == "Windows":
    import win32gui
    import win32process

# Windows: UIA
try:
    import uiautomation as auto
except ImportError:
    auto = None

# macOS: Accessibility
try:
    from Quartz import (
        AXUIElementCreateSystemWide,
        AXUIElementCopyAttributeValue,
        kAXRoleAttribute,
        kAXTitleAttribute,
        kAXValueAttribute,
        kAXChildrenAttribute,
    )
except ImportError:
    AXUIElementCreateSystemWide = None

# Linux: AT-SPI
try:
    import pyatspi
except ImportError:
    pyatspi = None


def get_bounding_rect(x, y, width, height):
    screen_w, screen_h = pyautogui.size()
    scale_x = 1280 / screen_w
    scale_y = 720 / screen_h

    scaled_x = int(x * scale_x)
    scaled_y = int(y * scale_y)
    scaled_width = int(width * scale_x)
    scaled_height = int(height * scale_y)

    return {
        'x': int(scaled_x + scaled_width / 2),
        'y': int(scaled_y + scaled_height / 2),
        'width': scaled_width,
        'height': scaled_height,
    }


def get_running_apps():
    system = platform.system()
    result = []

    if system == "Windows":
        def callback(hwnd, app_list):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid)
                name = process.name()

                # Filter out common system noise
                ignored = {
                    "System Idle Process", "System", "Registry", "MemCompression",
                    "svchost.exe", "explorer.exe", "fontdrvhost.exe", "dwm.exe",
                    "winlogon.exe", "csrss.exe", "wininit.exe", "services.exe",
                    "dllhost.exe", "conhost.exe", "RuntimeBroker.exe", "taskhostw.exe"
                }

                if name in ignored or not name.lower().endswith((".exe",)):
                    return True

                entry = {
                    "pid": pid,
                    "name": name,
                    "focused": hwnd == win32gui.GetForegroundWindow()
                }

                # Avoid duplicates
                if not any(app["pid"] == pid for app in app_list):
                    app_list.append(entry)
            except Exception:
                pass
            return True

        app_list = []
        win32gui.EnumWindows(callback, app_list)
        result = app_list

    elif system == "Darwin":
        import subprocess, json
        try:
            output = subprocess.check_output(
                ["osascript", "-e", 'tell application "System Events" to get name of (processes where background only is false)']
            )
            active = subprocess.check_output(
                ["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true']
            ).decode().strip()

            apps = [name.strip() for name in output.decode().split(",")]
            result = [{"pid": None, "name": app, "focused": app == active} for app in apps]
        except Exception:
            pass

    elif system == "Linux":
        try:
            import subprocess
            output = subprocess.check_output(["wmctrl", "-lp"]).decode()
            lines = output.splitlines()
            active_output = subprocess.check_output(["xdotool", "getactivewindow", "getwindowpid"]).decode().strip()
            active_pid = int(active_output) if active_output.isdigit() else None

            seen = set()
            for line in lines:
                parts = line.split()
                if len(parts) >= 5:
                    pid = int(parts[2])
                    if pid in seen:
                        continue
                    seen.add(pid)
                    name = psutil.Process(pid).name()
                    result.append({
                        "pid": pid,
                        "name": name,
                        "focused": pid == active_pid
                    })
        except Exception:
            pass

    return result


def extract_desktop_icons_windows():
    """
    Enumerate desktop icons via the Explorer ListView (SysListView32).
    """

    if os.getenv('NEURALAGENT_BACKGROUND_MODE') == 'true':
        return []

    if not auto:
        return []

    try:
        # Locate the SysListView32 control hosting desktop icons
        listview = auto.Control(ClassName='SysListView32')
    except Exception:
        return []

    icons = []
    for idx, item in enumerate(listview.GetChildren(), start=1):
        try:
            name = item.Name or ''
            rect = item.BoundingRectangle
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w > 0 and h > 0:
                icons.append({
                    'id': idx,
                    'type': 'DesktopIcon',
                    'label': name,
                    'bounding_box': get_bounding_rect(rect.left, rect.top, w, h),
                })
        except Exception:
            continue
    return icons


def extract_ui_elements_windows():
    """
    Extract UI Automation interactive elements from the active foreground window.
    """
    if not auto:
        return []
    
    try:
        foreground = auto.GetForegroundControl()
        elements = []

        def recurse(control, depth=0):
            try:
                control_type = control.ControlTypeName
                name = control.Name or ""
                rect = control.BoundingRectangle
            except Exception:
                return
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w > 0 and h > 0:
                interactive = {
                    "ButtonControl", "EditControl", "CheckBoxControl", "ComboBoxControl",
                    "HyperlinkControl", "TabItemControl", "MenuItemControl"
                }
                if control_type in interactive:
                    elements.append({
                        "type": control_type.replace('Control', ''),
                        "label": name,
                        "bounding_box": get_bounding_rect(rect.left, rect.top, w, h),
                        "depth": depth
                    })
            for child in control.GetChildren():
                recurse(child, depth + 1)

        recurse(foreground)
        return elements
    except:
        return []


def extract_ui_elements_macos():
    """
    Extract macOS Accessibility interactive elements globally.
    """
    if not AXUIElementCreateSystemWide:
        return []

    system = AXUIElementCreateSystemWide()
    elements = []

    def recurse(element, depth=0):
        try:
            role = AXUIElementCopyAttributeValue(element, kAXRoleAttribute)
            title = AXUIElementCopyAttributeValue(element, kAXTitleAttribute) or ""
            value = AXUIElementCopyAttributeValue(element, kAXValueAttribute) or ""
            children = AXUIElementCopyAttributeValue(element, kAXChildrenAttribute) or []
        except Exception:
            return

        interactive = {"AXButton", "AXTextField", "AXCheckBox", "AXComboBox", "AXMenuItem", "AXTabGroup"}
        if role in interactive:
            try:
                f = AXUIElementCopyAttributeValue(element, 'AXFrame')
                x, y, w, h = f.x, f.y, f.width, f.height
                if w > 0 and h > 0:
                    elements.append({
                        "type": role.replace('AX', ''),
                        "label": title or value,
                        "bounding_box": scaled_bounding_rect(x, y, w, h),
                        "depth": depth
                    })
            except Exception:
                pass

        for child in children:
            recurse(child, depth + 1)

    recurse(system)
    return elements


def extract_ui_elements_linux():
    """
    Extract AT-SPI interactive elements on Linux desktop.
    """
    if not pyatspi:
        return []

    desktop = pyatspi.Registry.getDesktop(0)
    elements = []

    def recurse(obj, depth=0):
        try:
            role = obj.getRoleName()
            name = obj.name or ""
        except Exception:
            return

        interactive = {"push button", "check box", "combo box", "text", "hyperlink", "menu item"}
        if role.lower() in interactive:
            elements.append({
                "type": role.title().replace(' ', ''),
                "label": name,
                "bounding_box": None,
                "depth": depth
            })

        for i in range(obj.childCount):
            recurse(obj.getChildAtIndex(i), depth + 1)

    recurse(desktop)
    return elements


def detect_possible_webview(bounding_boxes, screen_w, screen_h, threshold=0.5):
    """
    Detect if a large portion of the screen is uncovered, suggesting a WebView.
    Returns a placeholder element if so.
    """
    total_area = screen_w * screen_h
    covered = 0

    for box in bounding_boxes:
        bb = box.get("bounding_box")
        if bb and bb["width"] and bb["height"]:
            covered += bb["width"] * bb["height"]

    uncovered_ratio = 1 - (covered / total_area)

    if uncovered_ratio >= threshold:
        return {
            "id": -1,
            "type": "PossibleWebView",
            "label": "Potential WebView region not detected via native UI",
            "bounding_box": {
                "x": int(screen_w * 0.05),
                "y": int(screen_h * 0.05),
                "width": int(screen_w * 0.9),
                "height": int(screen_h * 0.9),
            },
        }

    return None


def extract_interactive_elements():
    """
    Combine native elements on Windows (and only include desktop icons when no window is active),
    or fallback native on macOS/Linux.
    Returns a list of dicts: {id, type, label, bounding_box}.
    """
    system = platform.system()
    raw = []

    if system == "Windows":
        ui = extract_ui_elements_windows()
        icons = []
        # only show icons when no UI controls found (i.e., desktop is active)
        if not ui:
            icons = extract_desktop_icons_windows()
        raw = ui + icons

    elif system == "Darwin":
        raw = extract_ui_elements_macos()

    elif system == "Linux":
        raw = extract_ui_elements_linux()

    else:
        raise NotImplementedError(f"Unsupported platform: {system}")

    interactive = []
    for idx, e in enumerate(raw, start=1):
        interactive.append({
            "id": idx,
            "type": e["type"],
            "label": e.get("label", ""),
            "bounding_box": e.get("bounding_box"),
        })
    
    screen_w, screen_h = pyautogui.size()
    webview_hint = detect_possible_webview(interactive, screen_w, screen_h)
    if webview_hint:
        interactive.append(webview_hint)

    return interactive
