"""Settings for the voice assistant orchestrator.

Uses pydantic-settings to load from parent project's .env file,
with type validation and sensible defaults for local Ollama usage.
"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Ollama connection
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_fallback_model: str = "qwen2.5:14b"

    # Search API keys
    brave_api_key: str = ""
    tavily_api_key: str = ""

    # Orchestrator limits
    max_tool_calls_per_turn: int = 5
    max_history_messages: int = 20
    enable_thinking: bool = False

    # Timeouts (seconds)
    ollama_timeout: float = 60.0
    search_timeout: float = 10.0

    model_config = {
        "env_file": str(Path(__file__).resolve().parent.parent / ".env"),
        "extra": "ignore",
    }


settings = Settings()
