from langchain_core.prompts import ChatPromptTemplate
from utils import ai_prompts
import json
from utils import llm_provider
from utils.procedures import extract_json


def generate_thread_title(task):
    llm = llm_provider.get_llm(agent='title', temperature=0.3)

    prompt = ChatPromptTemplate.from_messages([
        ('system', ai_prompts.TITLE_GENERATION_PROMPT),
        ('user', 'Generate a title for this task: {task}'),
    ])

    chain = prompt | llm

    response = chain.invoke({'task': task})

    try:
        response_data = extract_json(response.content)
    except (TypeError, ValueError, json.JSONDecodeError):
        response_data = {'title': ''}

    return response_data.get('title')
