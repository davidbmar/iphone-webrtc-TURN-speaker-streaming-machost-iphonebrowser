"""Base class for all tools in the voice assistant.

Each tool declares its name, description, and JSON Schema parameters,
then implements async execute(). The to_openai_schema() method generates
the function-calling format that Ollama's /api/chat expects.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Type

from pydantic import BaseModel


class BaseTool(ABC):
    """Abstract base for a callable tool."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used in function calls (e.g. 'web_search')."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description shown to the model."""

    @property
    @abstractmethod
    def parameters_schema(self) -> dict:
        """JSON Schema for the tool's parameters."""

    @property
    def input_model(self) -> Optional[Type[BaseModel]]:
        """Optional Pydantic model for input validation."""
        return None

    @property
    def output_model(self) -> Optional[Type[BaseModel]]:
        """Optional Pydantic model for output validation."""
        return None

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Run the tool. Always returns a string for the tool role message."""

    def to_openai_schema(self) -> dict:
        """Generate Ollama-compatible tool definition (OpenAI function format)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }
