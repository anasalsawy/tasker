from langchain_core.prompts import ChatPromptTemplate
from utils import ai_prompts
import json
from utils import llm_provider


def generate_thread_title(task):
    llm = llm_provider.get_llm(agent='title', temperature=0.3)

    prompt = ChatPromptTemplate.from_messages([
        ('system', ai_prompts.TITLE_GENERATION_PROMPT),
    ])

    chain = prompt | llm

    response = chain.invoke({'task': task})

    try:
        response_data = json.loads(response.content.split('```json')[1].split('```')[0])
    except:
        try:
            response_data = json.loads(response.content)
        except:
            response_data = {'title': ''}

    return response_data.get('title')
