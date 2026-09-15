"""Stateless look-ahead and commit endpoints for Tasker's dual-lobe mode.

The existing NeuralAgent /next_step endpoint remains the authoritative single
lobe path.  These endpoints add an opt-in lane:

* /dual_lobe/predict calls the computer-use model without writing task state.
* /dual_lobe/commit records a B batch only after the desktop agent executed it.

That separation prevents a speculative B answer from advancing the task by
itself.
"""

from base64 import b64decode
import io
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from sqlmodel import Session, and_, select
from pydantic import BaseModel, Field

from db.database import get_session
from db.models import (
    PlanSubtask,
    SubtaskStatus,
    SubtaskType,
    Thread,
    ThreadChatFromChoices,
    ThreadChatType,
    ThreadMessage,
    ThreadStatus,
    ThreadTask,
    ThreadTaskMemoryEntry,
    ThreadTaskPlan,
    ThreadTaskPlanStatus,
    ThreadTaskStatus,
    User,
)
from dependencies.auth_dependencies import get_current_user_dependency
from schemas.aiagent import NextStepRequest
from utils import ai_prompts, llm_provider, upload_helper
from utils.procedures import CustomError, extract_json
from utils.agentic_tools import run_tool_server_side


router = APIRouter(
    prefix="/aiagent",
    tags=["dual-lobe"],
    dependencies=[Depends(get_current_user_dependency)],
)


class DualLobePredictRequest(BaseModel):
    batch_id: str
    current_os: str
    current_interactive_elements: List[dict] = Field(default_factory=list)
    current_running_apps: List[dict] = Field(default_factory=list)
    screenshot_b64: Optional[str] = None
    executing_batch: Dict[str, Any] = Field(default_factory=dict)
    predicted_end: Dict[str, Any] = Field(default_factory=dict)


class DualLobeCommitRequest(BaseModel):
    batch_id: str
    response: Dict[str, Any]
    observed_boundary: Dict[str, Any] = Field(default_factory=dict)
    predicted_end: Dict[str, Any] = Field(default_factory=dict)


def _context(tid: str, db: Session, user: User):
    instance = db.exec(
        select(Thread).where(
            and_(
                Thread.id == tid,
                Thread.user_id == user.id,
                Thread.status == ThreadStatus.WORKING,
            )
        )
    ).first()
    if not instance:
        raise CustomError(status.HTTP_404_NOT_FOUND, "Thread not found")

    task = db.exec(
        select(ThreadTask).where(
            and_(
                ThreadTask.thread_id == tid,
                ThreadTask.status == ThreadTaskStatus.WORKING,
            )
        )
    ).first()
    if not task:
        raise CustomError(status.HTTP_404_NOT_FOUND, "Thread has no running task")

    plan = db.exec(
        select(ThreadTaskPlan).where(
            and_(
                ThreadTaskPlan.thread_task_id == task.id,
                ThreadTaskPlan.status == ThreadTaskPlanStatus.ACTIVE,
            )
        )
    ).first()
    if not plan:
        raise CustomError(status.HTTP_404_NOT_FOUND, "Thread has no active plan")

    subtask = db.exec(
        select(PlanSubtask).where(
            and_(
                PlanSubtask.status == SubtaskStatus.ACTIVE,
                PlanSubtask.thread_task_plan_id == plan.id,
            )
        ).order_by(PlanSubtask.ordering.asc())
    ).first()
    if not subtask or subtask.subtask_type != SubtaskType.DESKTOP:
        raise CustomError(status.HTTP_404_NOT_FOUND, "No current desktop task")
    return instance, task, plan, subtask


def _response_data(model_response: Any) -> Dict[str, Any]:
    content = model_response.content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"text", "output_text"}:
                value = item.get("text")
                if value:
                    text_parts.append(value)
        content = "\n".join(text_parts)
    data = extract_json(str(content))
    if not isinstance(data, dict):
        raise CustomError(status.HTTP_502_BAD_GATEWAY, "Model did not return an action object")
    actions = data.get("actions")
    if not isinstance(actions, list) or not actions:
        raise CustomError(status.HTTP_502_BAD_GATEWAY, "Model did not return a non-empty action batch")
    if any(not isinstance(action, dict) for action in actions):
        raise CustomError(status.HTTP_502_BAD_GATEWAY, "Model returned a malformed action batch")
    for action in actions:
        if not action.get("action"):
            raise CustomError(status.HTTP_502_BAD_GATEWAY, "Model returned an action without a kind")
    if any(
        action.get("action") in {"subtask_completed", "subtask_failed"}
        for action in actions
    ) and len(actions) != 1:
        raise CustomError(
            status.HTTP_502_BAD_GATEWAY,
            "Completion actions must be the only action in a batch",
        )
    return data


def _lookahead_prompt(
    task_text: str,
    subtask_text: str,
    request: DualLobePredictRequest,
    previous_messages: List[ThreadMessage],
):
    history = []
    for message in previous_messages:
        try:
            history.append(json.loads(message.text))
        except (TypeError, ValueError):
            continue

    blocks = [
        {
            "type": "text",
            "text": (
                "This is a Tasker dual-lobe look-ahead call. "
                "Lobe A is executing the batch below. Prepare exactly one next "
                "action batch that starts after A's predicted boundary. "
                "This call is stateless: do not claim that any action already "
                "succeeded and do not alter task state."
            ),
        },
        {"type": "text", "text": "Full task: {}".format(task_text)},
        {"type": "text", "text": "Current subtask: {}".format(subtask_text)},
        {"type": "text", "text": "Current OS: {}".format(request.current_os)},
        {
            "type": "text",
            "text": "Current visible native elements: {}".format(
                json.dumps(request.current_interactive_elements)
            ),
        },
        {
            "type": "text",
            "text": "Current running apps: {}".format(
                json.dumps(request.current_running_apps)
            ),
        },
        {
            "type": "text",
            "text": "Lobe A executing batch: {}".format(
                json.dumps(request.executing_batch)
            ),
        },
        {
            "type": "text",
            "text": "A predicted boundary: {}".format(
                json.dumps(request.predicted_end)
            ),
        },
    ]
    if history:
        blocks.append(
            {
                "type": "text",
                "text": "Recent committed action history: {}".format(
                    json.dumps(history[-5:])
                ),
            }
        )
    if request.screenshot_b64:
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": request.screenshot_b64,
                },
            }
        )
    return blocks


@router.post("/{tid}/dual_lobe/predict")
def predict_next_batch(
    tid: str,
    request: DualLobePredictRequest,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user_dependency),
):
    instance, task, plan, subtask = _context(tid, db, user)
    previous_messages = db.exec(
        select(ThreadMessage)
        .where(
            and_(
                ThreadMessage.thread_task_id == task.id,
                ThreadMessage.thread_chat_type == ThreadChatType.DESKTOP_USE,
            )
        )
        .order_by(ThreadMessage.created_at.desc())
        .limit(5)
    ).all()

    llm = llm_provider.get_llm(agent="computer_use", temperature=0.0)
    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=ai_prompts.COMPUTER_USE_SYSTEM_PROMPT),
            HumanMessage(
                content=_lookahead_prompt(
                    task.task_text,
                    subtask.subtask_text,
                    request,
                    previous_messages,
                )
            ),
        ]
    )
    response = (prompt | llm).invoke({})
    prediction = _response_data(response)

    return {
        "batch_id": request.batch_id,
        "source_lobe": "B",
        "prediction": prediction,
        "actions": prediction["actions"],
        "current_state": prediction.get("current_state", {}),
    }


@router.post("/{tid}/dual_lobe/commit")
def commit_next_batch(
    tid: str,
    request: DualLobeCommitRequest,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user_dependency),
):
    instance, task, plan, subtask = _context(tid, db, user)
    response = request.response.get("prediction", request.response)
    if not isinstance(response, dict):
        raise CustomError(status.HTTP_400_BAD_REQUEST, "Invalid predicted response")

    actions = response.get("actions")
    if not isinstance(actions, list) or not actions:
        raise CustomError(status.HTTP_400_BAD_REQUEST, "Cannot commit an empty action batch")
    if any(
        not isinstance(action, dict) or not action.get("action")
        for action in actions
    ):
        raise CustomError(status.HTTP_400_BAD_REQUEST, "Cannot commit malformed actions")
    if any(
        action.get("action") in {"subtask_completed", "subtask_failed"}
        for action in actions
    ) and len(actions) != 1:
        raise CustomError(
            status.HTTP_400_BAD_REQUEST,
            "Completion actions must be the only action in a batch",
        )

    message = ThreadMessage(
        thread_id=instance.id,
        thread_task_id=task.id,
        plan_subtask_id=subtask.id,
        thread_chat_type=ThreadChatType.DESKTOP_USE,
        thread_chat_from=ThreadChatFromChoices.FROM_AI,
        prompt=json.dumps(
            {
                "dual_lobe": True,
                "batch_id": request.batch_id,
                "predicted_end": request.predicted_end,
                "observed_boundary": request.observed_boundary,
            }
        ),
        text=json.dumps(response),
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    for action in actions:
        action_type = action.get("action")
        params = action.get("params") or {}
        if action_type == "subtask_completed":
            subtask.status = SubtaskStatus.COMPLETED
            db.add(subtask)
            db.commit()
            db.refresh(subtask)
        elif action_type == "subtask_failed":
            plan.status = ThreadTaskPlanStatus.FAILED
            task.status = ThreadTaskStatus.FAILED
            instance.status = ThreadStatus.STANDBY
            db.add(plan)
            db.add(task)
            db.add(instance)
            db.commit()
        elif action_type == "tool_use":
            tool = params.get("tool")
            args = params.get("args", {})
            if tool == "save_to_memory":
                db.add(
                    ThreadTaskMemoryEntry(
                        thread_task_id=task.id,
                        text=args.get("text", ""),
                    )
                )
                db.commit()
            elif tool in {"read_pdf", "fetch_url", "summarize_youtube_video"}:
                output = run_tool_server_side(tool, args)
                db.add(ThreadTaskMemoryEntry(thread_task_id=task.id, text=output))
                db.commit()

    return {
        "accepted": True,
        "batch_id": request.batch_id,
        "action_count": len(actions),
        "subtask_status": subtask.status,
    }
