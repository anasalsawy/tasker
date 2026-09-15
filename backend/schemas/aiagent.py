from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List


class NextStepRequest(BaseModel):
    screenshot_b64: Optional[str] = None
    current_interactive_elements: list[dict] = []
    current_os: str
    current_running_apps: list[dict] = []


class BackgroundNextStepRequest(BaseModel):
    screenshot_b64: Optional[str] = None
    current_open_tabs: list[dict] = []
    current_url: str


class CurrentSubtaskRequestObj(BaseModel):
    current_interactive_elements: list[dict] = []
    current_os: str
    current_running_apps: list[dict] = []


class SuggestorRequest(BaseModel):
    current_interactive_elements: list[dict] = []
    current_os: str
    current_running_apps: list[dict] = []
    screenshot_b64: Optional[str] = None
