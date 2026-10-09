"""Shared model configuration and observational LangChain logging callbacks."""

import time
from threading import Lock
from typing import Any, TypeVar
from uuid import UUID

from langchain.chat_models import init_chat_model
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from pydantic import BaseModel

from config.settings import settings
from observability.logging import get_logger, trace_payload

logger = get_logger(__name__)
ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


def parse_structured_response(response: dict, schema: type[ResponseModel]) -> ResponseModel:
    """Propagate LangChain parsing errors and require the expected response model."""
    if response["parsing_error"] is not None:
        raise response["parsing_error"]
    parsed = response["parsed"]
    if not isinstance(parsed, schema):
        raise ValueError(f"Model did not return structured {schema.__name__}")
    return parsed


class ModelLoggingCallback(BaseCallbackHandler):
    """Observe model requests without changing responses or handling their errors."""

    run_inline = True

    def __init__(self, model_name: str, stage: str, tool_name: str | None = None) -> None:
        self.model_name = model_name
        self.stage = stage
        self.tool_name = tool_name
        self._starts: dict[UUID, float] = {}
        self._lock = Lock()

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        with self._lock:
            # Bound storage if a cancelled caller never delivers an end/error event.
            if len(self._starts) >= 1024:
                self._starts.pop(next(iter(self._starts)))
            self._starts[run_id] = time.monotonic()

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        with self._lock:
            started_at = self._starts.pop(run_id, None)
        message = next(
            (
                generation.message
                for group in response.generations
                for generation in group
                if isinstance(generation, ChatGeneration)
                and isinstance(generation.message, AIMessage)
            ),
            None,
        )
        if message is None:
            return
        usage = message.usage_metadata or {}
        fields = {
            "model": self.model_name,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "latency_ms": int((time.monotonic() - started_at) * 1000)
            if started_at is not None
            else None,
        }
        if self.tool_name is not None:
            logger.info("llm_complete_json", tool=self.tool_name, **fields)
            trace_payload(f"{self.stage} <- tool output (verbatim)", message.tool_calls)
        else:
            logger.info("llm_complete", **fields)
            if self.stage == "search":
                if message.text:
                    trace_payload("search <- model text (verbatim)", message.text)
            else:
                trace_payload(f"{self.stage} <- text output (verbatim)", message.text)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        with self._lock:
            self._starts.pop(run_id, None)
        logger.error(
            "llm_error",
            model=self.model_name,
            stage=self.stage,
            error_type=type(error).__name__,
        )


def create_chat_model(
    model_name: str,
    max_tokens: int,
    *,
    stage: str,
    tool_name: str | None = None,
) -> BaseChatModel:
    # Bare names retain the existing Anthropic default. A provider prefix enables
    # another installed integration without changing any component's model code.
    provider, name = model_name.split(":", 1) if ":" in model_name else ("anthropic", model_name)
    credentials = {}
    if provider == "anthropic":
        if not settings.anthropic_api_key.strip():
            raise ValueError("ANTHROPIC_API_KEY is required when using an Anthropic model")
        credentials["api_key"] = settings.anthropic_api_key
    return init_chat_model(
        model=name,
        model_provider=provider,
        max_tokens=max_tokens,
        callbacks=[ModelLoggingCallback(model_name, stage, tool_name)],
        **credentials,
    )
