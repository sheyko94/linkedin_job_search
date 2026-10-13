"""Load a named chat prompt from Langfuse, with an explicit local fallback."""

import json
from hashlib import sha256
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langfuse import Langfuse
from langfuse.api import Prompt_Chat
from langfuse.model import ChatPromptClient

from config.settings import settings
from observability.logging import get_logger

logger = get_logger(__name__)
PROMPT_DIR = Path(__file__).parent


def load_prompt(
    name: str,
    client: Langfuse | None = None,
    *,
    label: str | None = None,
    version: int | None = None,
    allow_fallback: bool = True,
    required_variables: set[str] | None = None,
    history_placeholder: str | None = None,
) -> ChatPromptTemplate:
    local = json.loads((PROMPT_DIR / f"{name}.json").read_text())
    try:
        if client is None:
            if not settings.langfuse_public_key or not settings.langfuse_secret_key:
                raise ValueError("Both Langfuse project keys are required to fetch prompts")
            client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                base_url=settings.langfuse_base_url,
            )
        selected = client.get_prompt(
            local["name"],
            type="chat",
            version=version,
            label=None if version is not None else (label or settings.prompt_label),
            cache_ttl_seconds=0,
            max_retries=0,
            fetch_timeout_seconds=3,
        )
    except Exception as exc:
        if not allow_fallback:
            raise
        logger.warning("prompt_fallback", prompt_name=local["name"], error_type=type(exc).__name__)
        selected = ChatPromptClient(
            Prompt_Chat(**local, version=0, config={}, labels=[], tags=[]), is_fallback=True
        )

    messages = selected.get_langchain_prompt()
    metadata = {
        "prompt_name": selected.name,
        "prompt_source": "local" if selected.is_fallback else "langfuse",
        "prompt_version": selected.version,
        "prompt_hash": sha256(json.dumps(selected.prompt, sort_keys=True).encode()).hexdigest(),
    }
    template = ChatPromptTemplate.from_messages(messages)
    if required_variables is not None and set(template.input_variables) != required_variables:
        raise ValueError(
            f"{name} prompt must use exactly {sorted(required_variables)}; "
            f"got {sorted(template.input_variables)}"
        )
    if history_placeholder is not None and not any(
        isinstance(message, MessagesPlaceholder)
        and message.variable_name == history_placeholder
        and not message.optional
        for message in template.messages
    ):
        raise ValueError(
            f"{name} prompt must include a required {history_placeholder} history placeholder"
        )
    logger.info("prompt_selected", **metadata)
    template.metadata = metadata
    if not selected.is_fallback:
        template.metadata["langfuse_prompt"] = selected
    return template
