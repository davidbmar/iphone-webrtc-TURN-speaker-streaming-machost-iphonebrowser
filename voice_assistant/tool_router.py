"""Tool dispatch — routes tool calls to registered tools, never raises.

The router validates inputs via Pydantic models (when defined) and
catches all exceptions, returning error strings to the model so it
can self-correct or inform the user gracefully.
"""

from __future__ import annotations

import json
import logging

from .tools import get_tool

log = logging.getLogger("tool_router")


async def dispatch_tool_call(name: str, args: dict | str) -> str:
    """Execute a tool call by name. Always returns a string, never raises.

    Args:
        name: The tool name from the model's function call.
        args: Arguments dict (or JSON string) from the model.

    Returns:
        Tool result string, or an error message for the model.
    """
    # Parse args if they arrive as a JSON string
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return f"Error: invalid JSON arguments for tool '{name}': {args[:200]}"

    if not isinstance(args, dict):
        args = {}

    tool = get_tool(name)
    if tool is None:
        available = ", ".join(t.name for t in __import__(
            "voice_assistant.tools", fromlist=["TOOL_REGISTRY"]
        ).TOOL_REGISTRY.values())
        return f"Error: unknown tool '{name}'. Available tools: {available}"

    # Validate input via Pydantic model if the tool defines one
    if tool.input_model is not None:
        try:
            validated = tool.input_model(**args)
            args = validated.model_dump()
        except Exception as e:
            return f"Error: invalid arguments for '{name}': {e}"

    try:
        result = await tool.execute(**args)
        log.info("Tool '%s' returned %d chars", name, len(result))
        return result
    except Exception as e:
        log.exception("Tool '%s' raised an exception", name)
        return f"Error executing '{name}': {type(e).__name__}: {e}"
