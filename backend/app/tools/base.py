from abc import ABC, abstractmethod
from typing import Any, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import ToolDefinition


class ToolContext(TypedDict, total=False):
    """Context injected into tools at runtime by the agent framework.

    Fields are set by tool_node from the authenticated session state —
    never from LLM output — so tools can trust them for authorization.
    """

    db: AsyncSession
    user_id: str


class BaseTool(ABC):
    """Abstract base class for tools that the LLM can call."""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    last_execution_metadata: dict[str, Any] | None = None

    def to_definition(self) -> ToolDefinition:
        """Convert to a ToolDefinition for passing to the LLM."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters_schema,
        )

    @abstractmethod
    async def execute(self, *, context: ToolContext | None = None, **kwargs: Any) -> str:
        """Execute the tool with the given arguments and return a text result."""
        ...
