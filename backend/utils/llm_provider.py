import os
from dotenv import load_dotenv
from botocore.config import Config

from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_aws import ChatBedrockConverse
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel

load_dotenv()  # Load env variables from .env

def get_llm(agent: str, temperature: float = 0.0, max_tokens: int = None, thinking_enabled: bool = False) -> BaseChatModel:
    """
    Get an LLM instance based on agent name and environment variables.

    Args:
        agent (str): Logical name of the agent, e.g., "planner", "suggestor", "computer_use", "classifier", "title"
        temperature (float): Sampling temperature
        max_tokens (int): Optional token limit

    Returns:
        langchain-compatible LLM object
    """
    model_type = os.getenv(f"{agent.upper()}_AGENT_MODEL_TYPE")
    model_id = os.getenv(f"{agent.upper()}_AGENT_MODEL_ID")

    if not model_type or not model_id:
        raise ValueError(f"Missing model config for agent: {agent}")

    if model_type == "azure_openai":
        return AzureChatOpenAI(
            azure_deployment=model_id,
            api_version=os.getenv("OPENAI_API_VERSION", "2024-12-01-preview"),
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=None,
            max_retries=2
        )
    
    elif model_type == "openai":
        return ChatOpenAI(
            model=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=None,
            max_retries=2
        )

    elif model_type == "anthropic":
        if not thinking_enabled:
            return ChatAnthropic(
                model=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=None,
                max_retries=2,
            )
        else:
            return ChatAnthropic(
                model=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=None,
                max_retries=2,
                thinking={"type": "enabled", "budget_tokens": 2000},
            )

    elif model_type == "bedrock":
        thinking_params = {
            "thinking": {
                "type": "enabled",
                "budget_tokens": 2000
            }
        }
        boto3_config = Config(
            connect_timeout=300,
            read_timeout=300,
            retries={'max_attempts': 5},
            region_name=os.getenv("BEDROCK_REGION", "us-east-1")
        )
        if thinking_enabled and 'claude' in model_id:
            return ChatBedrockConverse(
                model=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                config=boto3_config,
                region_name=os.getenv("BEDROCK_REGION", "us-east-1"),
                additional_model_request_fields=thinking_params
            )
        else:
            return ChatBedrockConverse(
                model=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                config=boto3_config,
                region_name=os.getenv("BEDROCK_REGION", "us-east-1")
            )

    else:
        raise ValueError(f"Unsupported model type '{model_type}' for agent '{agent}'")
