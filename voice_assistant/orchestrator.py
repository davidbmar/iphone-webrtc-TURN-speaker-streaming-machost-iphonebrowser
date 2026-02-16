"""Conversation orchestrator — manages the chat loop with Ollama tool calling.

Core flow:
  1. User message appended, history trimmed
  2. POST /api/chat with tools list
  3. Model returns text (done) or tool_calls (execute, loop back to 2)
  4. Max 5 tool-call iterations, then force text response

The orchestrator owns the message history and handles all Ollama protocol
details including Qwen 3's thinking mode suppression.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from .config import settings
from .tool_router import dispatch_tool_call
from .tools import get_all_schemas

log = logging.getLogger("orchestrator")

# Load system prompt template
_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.txt"
_SYSTEM_TEMPLATE = _PROMPT_PATH.read_text()

# Regex to strip <think>...</think> blocks from Qwen 3 output
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# Regex to detect tool calls emitted as text (fallback for models without native support).
# Matches patterns like: tool_name {"key": "val"}  or  tool_name({"key": "val"})
_TEXT_TOOL_RE = re.compile(
    r"""(?:^|['"`\s])(\w+)\s*\(?\s*(\{[^}]*\})\s*\)?""",
    re.DOTALL,
)

# Map model-emitted tool names to our registry names.
# Models like qwen2.5 invent their own names (gc_search, etc.)
_TOOL_ALIASES: dict[str, str] = {
    "gc_search": "web_search",
    "search": "web_search",
    "web_search": "web_search",
    "check_calendar": "check_calendar",
    "calendar": "check_calendar",
    "get_calendar": "check_calendar",
    "search_notes": "search_notes",
    "notes": "search_notes",
    "get_notes": "search_notes",
}


class Orchestrator:
    """Manages conversation state and Ollama tool-calling loop."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self._active_model: str = ""
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def active_model(self) -> str:
        return self._active_model

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=settings.ollama_timeout)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Model management ──────────────────────────────────────

    async def ensure_model(self) -> str:
        """Check if preferred model is available, fall back if needed.
        Returns the active model name.
        """
        client = await self._get_client()
        try:
            resp = await client.get(f"{settings.ollama_url}/api/tags")
            resp.raise_for_status()
            installed = {m["name"] for m in resp.json().get("models", [])}
            # Normalize: "qwen3:8b" might be reported as "qwen3:8b" or with :latest
            installed_normalized = set()
            for name in installed:
                installed_normalized.add(name)
                if name.endswith(":latest"):
                    installed_normalized.add(name[:-7])
        except Exception as e:
            log.error("Cannot reach Ollama at %s: %s", settings.ollama_url, e)
            raise ConnectionError(
                f"Cannot reach Ollama at {settings.ollama_url}. "
                f"Is Ollama running? Start it with: ollama serve"
            ) from e

        # Check preferred model
        if settings.ollama_model in installed_normalized:
            self._active_model = settings.ollama_model
        elif settings.ollama_fallback_model in installed_normalized:
            log.warning(
                "Preferred model '%s' not found, using fallback '%s'",
                settings.ollama_model, settings.ollama_fallback_model,
            )
            self._active_model = settings.ollama_fallback_model
        else:
            self._active_model = ""

        return self._active_model

    async def pull_model(self, model_name: str):
        """Pull a model from Ollama. Yields progress dicts."""
        client = await self._get_client()
        async with httpx.AsyncClient(timeout=None) as pull_client:
            async with pull_client.stream(
                "POST",
                f"{settings.ollama_url}/api/pull",
                json={"name": model_name, "stream": True},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

    # ── System prompt ─────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        now = datetime.now()
        return _SYSTEM_TEMPLATE.format(
            date=now.strftime("%A, %B %d, %Y"),
            time=now.strftime("%I:%M %p"),
        )

    # ── Ollama API ────────────────────────────────────────────

    async def _call_ollama(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> dict:
        """POST /api/chat and return the response message dict."""
        client = await self._get_client()
        body: dict[str, Any] = {
            "model": self._active_model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            body["tools"] = tools
        if not settings.enable_thinking:
            body["think"] = False

        log.debug("Ollama request: model=%s, %d messages, %d tools",
                   self._active_model, len(messages), len(tools or []))

        resp = await client.post(f"{settings.ollama_url}/api/chat", json=body)
        resp.raise_for_status()
        return resp.json()["message"]

    # ── Content cleanup ───────────────────────────────────────

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Remove <think>...</think> blocks that Qwen 3 sometimes emits."""
        return _THINK_RE.sub("", text).strip()

    # ── Text-based tool call parsing (fallback) ────────────────

    @staticmethod
    def _parse_text_tool_calls(text: str) -> list[dict]:
        """Detect tool calls embedded in text output.

        Some models (qwen2.5) emit tool calls as text like:
          gc_search {"query": "weather in Austin"}
        instead of using structured tool_calls. This parser catches
        those and converts them into the standard format.
        """
        results = []
        for match in _TEXT_TOOL_RE.finditer(text):
            raw_name = match.group(1).lower()
            raw_args = match.group(2)

            # Resolve alias to registry name
            tool_name = _TOOL_ALIASES.get(raw_name)
            if not tool_name:
                continue

            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                continue

            results.append({
                "function": {"name": tool_name, "arguments": args}
            })
            log.debug("Parsed text tool call: %s -> %s(%s)", raw_name, tool_name, args)

        return results

    # ── History management ────────────────────────────────────

    def _trim_history(self) -> None:
        """Trim message history to max_history_messages, preserving tool groups.

        A "tool group" is an assistant message with tool_calls followed by
        one or more tool-role messages. These must stay together or the
        conversation becomes incoherent to the model.
        """
        limit = settings.max_history_messages
        if len(self.messages) <= limit:
            return

        # Walk backwards to find a safe cut point that doesn't split a tool group
        cut = len(self.messages) - limit
        # Don't cut in the middle of a tool group — advance cut past any tool messages
        while cut < len(self.messages) and self.messages[cut].get("role") == "tool":
            cut += 1
        # If the message right before cut is an assistant with tool_calls, include it
        if cut > 0 and self.messages[cut - 1].get("tool_calls"):
            cut -= 1
            # Also skip its tool results
            while cut > 0 and self.messages[cut - 1].get("role") == "tool":
                cut -= 1

        self.messages = self.messages[cut:]

    # ── Main chat method ──────────────────────────────────────

    async def chat(
        self,
        user_input: str,
        on_tool_call: Optional[Callable[[str, dict], None]] = None,
    ) -> str:
        """Process user input through the tool-calling loop.

        Args:
            user_input: The user's message text.
            on_tool_call: Optional callback(tool_name, args) for UI updates.

        Returns:
            The assistant's final text response.
        """
        self.messages.append({"role": "user", "content": user_input})
        self._trim_history()

        system_prompt = self._build_system_prompt()
        all_messages = [{"role": "system", "content": system_prompt}] + self.messages
        tool_schemas = get_all_schemas()

        for iteration in range(settings.max_tool_calls_per_turn):
            # On last iteration, omit tools to force a text response
            is_last = iteration == settings.max_tool_calls_per_turn - 1
            tools_for_call = None if is_last else tool_schemas

            response = await self._call_ollama(all_messages, tools=tools_for_call)

            text = self._strip_thinking(response.get("content", ""))
            tool_calls = response.get("tool_calls", [])

            # Fallback: detect tool calls emitted as text by models
            # that don't use Ollama's native tool protocol
            if not tool_calls and text:
                text_tool_calls = self._parse_text_tool_calls(text)
                if text_tool_calls:
                    log.info("Detected %d tool call(s) in text output (fallback parser)",
                             len(text_tool_calls))
                    tool_calls = text_tool_calls
                    text = ""  # The text was a tool call, not a real response

            if not tool_calls:
                # Model gave a text response — we're done
                if text:
                    self.messages.append({"role": "assistant", "content": text})
                return text

            # Model wants to call tools — execute each one
            # Append the assistant message with tool_calls to history
            assistant_msg = {"role": "assistant", "content": text}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            self.messages.append(assistant_msg)
            all_messages.append(assistant_msg)

            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "unknown")
                tool_args = fn.get("arguments", {})

                if on_tool_call:
                    on_tool_call(tool_name, tool_args)

                result = await dispatch_tool_call(tool_name, tool_args)

                tool_msg = {"role": "tool", "content": result}
                self.messages.append(tool_msg)
                all_messages.append(tool_msg)

        # Shouldn't reach here, but safety net
        return text if text else "I wasn't able to complete that request."

    def clear_history(self) -> None:
        """Reset conversation history."""
        self.messages.clear()
