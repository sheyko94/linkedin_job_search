from typing import Callable

import anthropic
from anthropic.types import MessageParam
from config.settings import settings

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def complete(system: str, user: str, max_tokens: int = 1024) -> str:
    response = _client.messages.create(
        model=settings.model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text  # type: ignore[union-attr]


def run_agent(
    system: str,
    user: str,
    tools: list,
    on_tool_call: Callable[[str, dict], str],
    max_tokens: int = 1024,
    max_iterations: int = 10,
) -> str:  # type: ignore[return]
    messages: list[MessageParam] = [{"role": "user", "content": user}]
    for _ in range(max_iterations):
        response = _client.messages.create(
            model=settings.model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})  # type: ignore[list-item]

        if response.stop_reason == "end_turn":
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
