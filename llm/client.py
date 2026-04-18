import time
from typing import Callable

import anthropic
from anthropic.types import MessageParam

from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def complete(system: str, user: str, model: str, max_tokens: int = 1024) -> str:
    start = time.monotonic()
    response = _client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    logger.info(
        "llm_complete",
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_ms=int((time.monotonic() - start) * 1000),
    )
    return response.content[0].text  # type: ignore[union-attr]


def complete_with_tools(
    system: str,
    user: str,
    model: str,
    tools: list,
    on_tool_call: Callable[[str, dict], str],
    max_tokens: int = 1024,
    max_iterations: int = 10,
) -> str:  # type: ignore[return]
    messages: list[MessageParam] = [{"role": "user", "content": user}]
    total_input_tokens = 0
    total_output_tokens = 0
    start = time.monotonic()

    for _ in range(max_iterations):
        response = _client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )
        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens
        messages.append({"role": "assistant", "content": response.content})  # type: ignore[list-item]

        if response.stop_reason == "end_turn":
            logger.info(
                "llm_complete_with_tools",
                model=model,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
                latency_ms=int((time.monotonic() - start) * 1000),
            )
            return next(
                b.text for b in response.content
                if isinstance(b, anthropic.types.TextBlock)
            )

        tool_results = [
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": on_tool_call(block.name, block.input),
            }
            for block in response.content
            if isinstance(block, anthropic.types.ToolUseBlock)
        ]
        messages.append({"role": "user", "content": tool_results})  # type: ignore[list-item]

    raise RuntimeError(f"Agent exceeded max_iterations ({max_iterations}) without reaching end_turn")
