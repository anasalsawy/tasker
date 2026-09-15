import os
import platform
import requests
import ui_extraction
import mss
from io import BytesIO
from PIL import Image
import base64
import json


def take_screenshot_b64():
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        img = img.resize((1280, 720))
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


def get_suggestions():
    api_url = os.getenv("NEURALAGENT_API_URL") + '/aiagent/suggestor'
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + os.getenv("NEURALAGENT_USER_ACCESS_TOKEN"),
    }

    payload = {
        "current_os": "MacOS" if platform.system() == "darwin" else platform.system(),
        "current_interactive_elements": ui_extraction.extract_interactive_elements(),
        "current_running_apps": ui_extraction.get_running_apps(),
        "screenshot_b64": take_screenshot_b64(),
    }

    try:
        response = requests.post(api_url, json=payload, headers=headers)
        if response.status_code in (200, 201):
            return response.json()
        else:
            return {"suggestions": [], "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"suggestions": [], "error": str(e)}


if __name__ == "__main__":
    suggestions = get_suggestions()
    print(json.dumps(suggestions))
