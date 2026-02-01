from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_vertexai import ChatVertexAI, HarmBlockThreshold, HarmCategory

from app.core.config import get_settings


@dataclass
class LLMMessage:
    """Standardized message format for LLM interactions."""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a response from the LLM."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream response tokens from the LLM."""
        ...


def _to_langchain_messages(messages: list[LLMMessage]) -> list[BaseMessage]:
    """Convert LLMMessages to LangChain message format."""
    lc_messages: list[BaseMessage] = []
    for msg in messages:
        if msg.role == "system":
            lc_messages.append(SystemMessage(content=msg.content))
        elif msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            lc_messages.append(AIMessage(content=msg.content))
    return lc_messages


class VertexGeminiProvider(LLMProvider):
    """Vertex AI Gemini provider."""

    def __init__(
        self,
        project_id: str | None = None,
        location: str | None = None,
        model_name: str = "gemini-1.5-pro",
    ):
        settings = get_settings()
        self.project_id = project_id or settings.vertex_project_id
        self.location = location or settings.vertex_location
        self.model_name = model_name

    def _create_model(
        self,
        temperature: float,
        max_tokens: int,
        streaming: bool = False,
    ) -> ChatVertexAI:
        return ChatVertexAI(
            model_name=self.model_name,
            project=self.project_id,
            location=self.location,
            temperature=temperature,
            max_output_tokens=max_tokens,
            streaming=streaming,
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            },
        )

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        model = self._create_model(temperature, max_tokens)
        lc_messages = _to_langchain_messages(messages)
        response = await model.ainvoke(lc_messages)
        return str(response.content)

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        model = self._create_model(temperature, max_tokens, streaming=True)
        lc_messages = _to_langchain_messages(messages)
        async for chunk in model.astream(lc_messages):
            if chunk.content:
                yield str(chunk.content)


class VertexClaudeProvider(LLMProvider):
    """Vertex AI Claude provider (via Anthropic partner model)."""

    def __init__(
        self,
        project_id: str | None = None,
        location: str | None = None,
        model_name: str = "claude-3-5-sonnet@20240620",
    ):
        settings = get_settings()
        self.project_id = project_id or settings.vertex_project_id
        self.location = location or settings.vertex_location
        self.model_name = model_name

    def _create_model(
        self,
        temperature: float,
        max_tokens: int,
        streaming: bool = False,
    ) -> ChatVertexAI:
        return ChatVertexAI(
            model_name=self.model_name,
            project=self.project_id,
            location=self.location,
            temperature=temperature,
            max_output_tokens=max_tokens,
            streaming=streaming,
        )

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        model = self._create_model(temperature, max_tokens)
        lc_messages = _to_langchain_messages(messages)
        response = await model.ainvoke(lc_messages)
        return str(response.content)

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        model = self._create_model(temperature, max_tokens, streaming=True)
        lc_messages = _to_langchain_messages(messages)
        async for chunk in model.astream(lc_messages):
            if chunk.content:
                yield str(chunk.content)


def get_llm_provider(model_name: str | None = None) -> LLMProvider:
    """
    Get an LLM provider based on model name.

    Args:
        model_name: The model to use. If None, uses the default from settings.
                   Supported: gemini-1.5-pro, gemini-1.5-flash, claude-3-5-sonnet, etc.

    Returns:
        An LLM provider instance.
    """
    settings = get_settings()
    model = model_name or settings.default_llm

    if model.startswith("gemini"):
        return VertexGeminiProvider(model_name=model)
    elif model.startswith("claude"):
        return VertexClaudeProvider(model_name=model)
    else:
        return VertexGeminiProvider(model_name=model)
