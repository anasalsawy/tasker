import os
from dotenv import load_dotenv
from botocore.config import Config

from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_aws import ChatBedrockConverse

# Anthropic is optional — its newer langchain glue expects anthropic.OverloadedError,
# which missing from some anthropic packages in this env defeats. Anthropic agents
# (planner/computer_use legacy) are dormant now that persona is the live path.
try:
    from langchain_anthropic import ChatAnthropic
except AttributeError:
    ChatAnthropic = None
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models.chat_models import BaseChatModel

# Tasker is a local desktop app: its project-specific settings must take
# precedence over unrelated machine-wide provider variables.
load_dotenv(override=True)


def _request_limits():
    timeout = float(os.getenv("TASKER_LLM_TIMEOUT", "120"))
    retries = int(os.getenv("TASKER_LLM_MAX_RETRIES", "2"))
    return timeout, retries


def _agent_env(agent: str, suffix: str, fallback: str = "") -> str:
    name = "{}_AGENT_{}".format(agent.upper(), suffix)
    value = os.getenv(name, "").strip() or fallback.strip()

    # People commonly paste a complete KEY=value line into the value field.
    # Accept that harmless formatting mistake without logging the secret.
    possible_names = (name, "OPENAI_{}".format(suffix))
    for possible_name in possible_names:
        prefix = possible_name + "="
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
    return value


def get_llm(
    agent: str,
    temperature: float = 0.0,
    max_tokens: int = None,
    thinking_enabled: bool = False,
) -> BaseChatModel:
    """Build a configured model for one Tasker logical agent.

    In addition to the upstream providers, Tasker supports any
    OpenAI-compatible endpoint. This covers NVIDIA NIM, Gemini gateways,
    local servers, and other compatible providers without changing the
    agent loop.
    """
    model_type = os.getenv("{}_AGENT_MODEL_TYPE".format(agent.upper()))
    model_id = os.getenv("{}_AGENT_MODEL_ID".format(agent.upper()))
    timeout, retries = _request_limits()

    if not model_type or not model_id:
        raise ValueError("Missing model config for agent: {}".format(agent))

    if model_type == "azure_openai":
        return AzureChatOpenAI(
            azure_deployment=model_id,
            api_version=os.getenv("OPENAI_API_VERSION", "2024-12-01-preview"),
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=retries,
        )

    if model_type == "openai":
        return ChatOpenAI(
            model=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=retries,
        )

    if model_type in {"openai_compatible", "nvidia", "gemini_compatible"}:
        base_url = _agent_env(
            agent,
            "BASE_URL",
            os.getenv("OPENAI_BASE_URL", ""),
        )
        api_key = _agent_env(
            agent,
            "API_KEY",
            os.getenv("OPENAI_API_KEY", ""),
        )
        if not base_url or not api_key:
            raise ValueError(
                "OpenAI-compatible agent {} requires BASE_URL and API_KEY".format(agent)
            )

        # Google AI Studio now issues AQ-prefixed authorization keys by
        # default. Those keys are not reliably accepted by the OpenAI-
        # compatibility gateway, so use Google's native client for them.
        if "generativelanguage.googleapis.com" in base_url and api_key.startswith("AQ."):
            return ChatGoogleGenerativeAI(
                model=model_id,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                max_retries=retries,
            )

        return ChatOpenAI(
            model=model_id,
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=retries,
        )

    if model_type == "anthropic":
        kwargs = {
            "model": model_id,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
            "max_retries": retries,
        }
        if thinking_enabled:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 2000}
        return ChatAnthropic(**kwargs)

    if model_type == "bedrock":
        thinking_params = {
            "thinking": {
                "type": "enabled",
                "budget_tokens": 2000,
            }
        }
        boto3_config = Config(
            connect_timeout=int(os.getenv("TASKER_BEDROCK_CONNECT_TIMEOUT", "300")),
            read_timeout=int(os.getenv("TASKER_BEDROCK_READ_TIMEOUT", "300")),
            retries={"max_attempts": int(os.getenv("TASKER_BEDROCK_MAX_RETRIES", "5"))},
            region_name=os.getenv("BEDROCK_REGION", "us-east-1"),
        )
        kwargs = {
            "model": model_id,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "config": boto3_config,
            "region_name": os.getenv("BEDROCK_REGION", "us-east-1"),
        }
        if thinking_enabled and "claude" in model_id:
            kwargs["additional_model_request_fields"] = thinking_params
        return ChatBedrockConverse(**kwargs)

    raise ValueError(
        "Unsupported model type '{}' for agent '{}'".format(model_type, agent)
    )
