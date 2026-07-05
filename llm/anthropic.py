import time
from typing import Callable

import anthropic
from anthropic.types import MessageParam

from config.logging import get_logger, trace_payload
from config.settings import settings

logger = get_logger(__name__)

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def complete_json(
    system: str,
    user: str,
    model: str,
    tool_name: str,
    input_schema: dict,
    tool_description: str = "Return the result as structured data.",
    max_tokens: int = 1024,
) -> dict:
    """Force structured JSON output via a single forced tool call.

    The model must call the tool described by `input_schema`; its validated input
    (a dict, no markdown/prose to strip) is returned directly.
    """
    start = time.monotonic()
    response = _client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[
            {
                "name": tool_name,
                "description": tool_description,
                "input_schema": input_schema,
            }
        ],
        tool_choice={"type": "tool", "name": tool_name},
    )
    logger.info(
        "llm_complete_json",
        model=model,
        tool=tool_name,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_ms=int((time.monotonic() - start) * 1000),
    )
    for block in response.content:
        if isinstance(block, anthropic.types.ToolUseBlock):
            trace_payload(f"{tool_name} <- tool output (verbatim)", block.input)
            return block.input  # type: ignore[return-value]
    logger.warning("llm_complete_json_no_tool_use", model=model, tool=tool_name)
    return {}


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
    text = response.content[0].text  # type: ignore[union-attr]
    trace_payload("complete <- text output (verbatim)", text)
    return text


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
            final_text = next(
                block.text
                for block in response.content
                if isinstance(block, anthropic.types.TextBlock)
            )
            trace_payload("agent <- final text output (verbatim)", final_text)
            return final_text

        tool_results = []
        for block in response.content:
            if not isinstance(block, anthropic.types.ToolUseBlock):
                continue
            trace_payload(f"{block.name} -> LLM tool input (verbatim)", block.input)
            content = on_tool_call(block.name, block.input)
            trace_payload(f"{block.name} <- tool result (verbatim)", content)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": content}
            )
        if not tool_results:
            break
        messages.append({"role": "user", "content": tool_results})  # type: ignore[list-item]

    logger.warning("llm_max_iterations_reached", model=model, max_iterations=max_iterations)
    return ""
