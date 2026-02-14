import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_vertexai import (
    ChatVertexAI,
    HarmBlockThreshold,
    HarmCategory,
)
from langchain_google_vertexai.model_garden import ChatAnthropicVertex

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


def _to_openai_messages(messages: list[LLMMessage]) -> list[dict[str, str]]:
    """Convert LLMMessages to OpenAI API message format."""
    return [{"role": msg.role, "content": msg.content} for msg in messages]


class OpenRouterProvider(LLMProvider):
    """
    OpenRouter provider - access to multiple models via one API.

    Supports Claude, GPT-4, Llama, Mistral, and many more.
    See https://openrouter.ai/docs for available models.
    """

    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "anthropic/claude-3.5-sonnet",
    ):
        settings = get_settings()
        self.api_key = api_key or settings.openrouter_api_key
        self.model_name = model_name

        if not self.api_key:
            raise ValueError(
                "OpenRouter API key is required. "
                "Set OPENROUTER_API_KEY environment variable."
            )

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/alfred-ai",  # Optional, for rankings
            "X-Title": "Alfred AI Assistant",  # Optional, for rankings
        }

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        payload = {
            "model": self.model_name,
            "messages": _to_openai_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.OPENROUTER_API_URL,
                headers=self._get_headers(),
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model_name,
            "messages": _to_openai_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                self.OPENROUTER_API_URL,
                headers=self._get_headers(),
                json=payload,
                timeout=60.0,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue


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
    ) -> ChatAnthropicVertex:
        return ChatAnthropicVertex(
            model_name=self.model_name,
            project=self.project_id,
            location=self.location,
            temperature=temperature,
            max_tokens=max_tokens,
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
        model = self._create_model(temperature, max_tokens)
        lc_messages = _to_langchain_messages(messages)
        async for chunk in model.astream(lc_messages):
            if chunk.content:
                yield str(chunk.content)


def get_llm_provider(model_name: str | None = None) -> LLMProvider:
    """
    Get an LLM provider based on model name.

    Model name format determines the provider:
    - "openrouter/..." -> OpenRouter (e.g., "openrouter/anthropic/claude-3.5-sonnet")
    - "gemini-..." -> Vertex AI Gemini
    - "claude-..." -> Vertex AI Claude
    - Default: Uses DEFAULT_LLM from settings

    Args:
        model_name: The model to use. If None, uses the default from settings.

    Returns:
        An LLM provider instance.
    """
    settings = get_settings()
    model = model_name or settings.default_llm

    # OpenRouter models are prefixed with "openrouter/"
    if model.startswith("openrouter/"):
        # Remove the prefix to get the actual model name
        openrouter_model = model[len("openrouter/") :]
        return OpenRouterProvider(model_name=openrouter_model)

    # Vertex AI providers
    if model.startswith("gemini"):
        return VertexGeminiProvider(model_name=model)
    elif model.startswith("claude"):
        return VertexClaudeProvider(model_name=model)

    # Default to Gemini
    return VertexGeminiProvider(model_name=model)
