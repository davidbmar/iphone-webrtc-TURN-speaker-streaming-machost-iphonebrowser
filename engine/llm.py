"""LLM wrapper — Claude, OpenAI, or Ollama, switchable via env var."""

import asyncio
import logging
import os

log = logging.getLogger("llm")

# Provider config from env
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Lazy-loaded clients
_anthropic_client = None
_openai_client = None
_httpx_client = None


def _resolve_provider() -> str:
    """Determine which LLM provider to use."""
    if LLM_PROVIDER in ("claude", "openai", "ollama"):
        return LLM_PROVIDER
    # Auto-detect: Claude > OpenAI > Ollama
    if ANTHROPIC_API_KEY:
        return "claude"
    if OPENAI_API_KEY:
        return "openai"
    return "ollama"


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        log.info("Anthropic client initialized")
    return _anthropic_client


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
        log.info("OpenAI client initialized")
    return _openai_client


def _get_httpx():
    global _httpx_client
    if _httpx_client is None:
        import httpx
        _httpx_client = httpx.Client(timeout=30.0)
        log.info("httpx client initialized for Ollama at %s", OLLAMA_URL)
    return _httpx_client


def _generate_claude(system: str, messages: list[dict]) -> str:
    """Call Claude Haiku via the Anthropic SDK (synchronous)."""
    client = _get_anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=system,
        messages=messages,
    )
    text = resp.content[0].text
    log.info("Claude response: %d chars, stop=%s", len(text), resp.stop_reason)
    return text


def _generate_openai(system: str, messages: list[dict]) -> str:
    """Call OpenAI via the OpenAI SDK (synchronous)."""
    client = _get_openai()
    openai_messages = [{"role": "system", "content": system}] + messages
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=300,
        messages=openai_messages,
    )
    text = resp.choices[0].message.content
    log.info("OpenAI response (%s): %d chars, finish=%s", OPENAI_MODEL, len(text), resp.choices[0].finish_reason)
    return text


def _generate_ollama(system: str, messages: list[dict]) -> str:
    """Call Ollama local model via HTTP (synchronous)."""
    client = _get_httpx()
    # Ollama chat API expects system message in the messages list
    ollama_messages = [{"role": "system", "content": system}] + messages
    resp = client.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": OLLAMA_MODEL, "messages": ollama_messages, "stream": False},
    )
    resp.raise_for_status()
    text = resp.json()["message"]["content"]
    log.info("Ollama response (%s): %d chars", OLLAMA_MODEL, len(text))
    return text


def _generate_sync(system: str, messages: list[dict], provider: str = "") -> str:
    """Synchronous generate — dispatches to the given or default provider."""
    provider = provider or _resolve_provider()
    log.info("LLM generate: provider=%s, %d messages", provider, len(messages))
    if provider == "claude":
        return _generate_claude(system, messages)
    elif provider == "openai":
        return _generate_openai(system, messages)
    else:
        return _generate_ollama(system, messages)


async def generate(system: str, messages: list[dict], provider: str = "") -> str:
    """Generate an LLM response (runs in thread pool).

    Args:
        system: System prompt string.
        messages: Conversation messages [{"role": "user"/"assistant", "content": "..."}].
        provider: Override provider ("claude", "openai", "ollama"). Empty = use default.

    Returns:
        The assistant's reply text.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _generate_sync, system, messages, provider)


def available_providers() -> list[dict]:
    """Return list of available providers with their config status."""
    providers = []
    if ANTHROPIC_API_KEY:
        providers.append({"id": "claude", "name": "Claude Haiku"})
    if OPENAI_API_KEY:
        providers.append({"id": "openai", "name": f"OpenAI ({OPENAI_MODEL})"})
    providers.append({"id": "ollama", "name": f"Ollama ({OLLAMA_MODEL})"})
    return providers


def is_configured() -> bool:
    """Check if any LLM provider is available."""
    provider = _resolve_provider()
    if provider == "claude":
        return bool(ANTHROPIC_API_KEY)
    if provider == "openai":
        return bool(OPENAI_API_KEY)
    # Ollama is assumed available if selected (no easy pre-check)
    return True


def get_provider_name() -> str:
    """Return the name of the active provider."""
    return _resolve_provider()
