from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel


@dataclass
class ToolResult:
    """Result of a tool execution, returned to the LLM."""
    success: bool
    content: str                              # Text given back to the LLM
    display: Optional[str] = None             # Optional user-facing summary
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class ToolParameter(BaseModel):
    """Describes a single parameter for OpenAI-format tool schema."""
    name: str
    type: str           # "string", "integer", etc.
    description: str
    required: bool = True
    enum: Optional[list[str]] = None


class ToolDefinition:
    """Holds the OpenAI-compatible tool schema + metadata."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: list[ToolParameter],
    ):
        self.name = name
        self.description = description
        self.parameters = parameters

    def to_openai_schema(self) -> dict:
        """Convert to the dict format LiteLLM/OpenAI expects for `tools`."""
        properties = {}
        required = []
        for p in self.parameters:
            prop: dict = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            properties[p.name] = prop
            if p.required:
                required.append(p.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


class BaseTool(ABC):
    """Abstract base class for all tools."""

    @abstractmethod
    def get_definition(self) -> ToolDefinition:
        """Return the tool's schema definition."""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with validated arguments. Must be async."""
        ...

    @property
    def timeout_seconds(self) -> int:
        """Override to set a custom timeout (default 15)."""
        return 15
