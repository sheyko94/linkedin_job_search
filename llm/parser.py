import json
from agents.models import ExecutionResult


def parse_execution_result(raw: str) -> ExecutionResult:
    """Extract JSON from the LLM response and validate against ExecutionResult."""
    text = raw.strip()

    # Strip markdown code fences if present
    if "```" in text:
        parts = text.split("```")
        # parts[1] is the fenced block; strip a leading language tag (e.g. "json\n")
        text = parts[1].split("\n", 1)[-1] if "\n" in parts[1] else parts[1]

    return ExecutionResult.model_validate(json.loads(text.strip()))
