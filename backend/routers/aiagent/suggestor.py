from fastapi import APIRouter, Depends
from sqlmodel import Session, select, and_
from db.database import get_session
import os
from typing import Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
import json
from utils import ai_prompts
from utils.procedures import CustomError, extract_json, extract_json_array
from dependencies.auth_dependencies import get_current_user_dependency
from db.models import (User, Thread, ThreadStatus, ThreadTask)
from schemas.aiagent import SuggestorRequest
from utils import llm_provider


router = APIRouter(
    prefix='/aiagent/suggestor',
    tags=['aiagent', 'suggestor'],
    dependencies=[Depends(get_current_user_dependency)]
)


@router.post('')
def get_suggestions(request: SuggestorRequest, db: Session = Depends(get_session),
                    user: User = Depends(get_current_user_dependency)):
    prompt_blocks = [
        {"type": "text", "text": f"Current OS: {request.current_os}"},
        {"type": "text", "text": f"Current Visible UI Elements: {json.dumps(request.current_interactive_elements)}"},
        {"type": "text", "text": f"Current Running Apps: {json.dumps(request.current_running_apps)}"},
    ]

    most_recent_tasks = db.exec(select(ThreadTask).where(and_(
        ThreadTask.thread.has(Thread.user_id == user.id),
        ThreadTask.thread.has(Thread.status != ThreadStatus.DELETED),
    )).order_by(ThreadTask.created_at.desc()).limit(20)).all()
    most_recent_tasks_arr = []
    for recent_task in most_recent_tasks:
        most_recent_tasks_arr.append({
            'task': recent_task.task_text,
            'status': recent_task.status,
        })

    if len(most_recent_tasks_arr) > 0:
        prompt_blocks.append({
            "type": "text",
            "text": f"Most Recent User Tasks (Limited to 20): {json.dumps(most_recent_tasks_arr)}"
        })

    if request.screenshot_b64:
        prompt_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": request.screenshot_b64
            }
        })

    llm = llm_provider.get_llm(agent='suggestor', temperature=0.6)

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=ai_prompts.SUGGESTOR_AGENT_PROMPT),
        HumanMessage(content=prompt_blocks)
    ])

    chain = prompt | llm
    response = chain.invoke({})

    response_data = extract_json(response.content)

    return response_data
