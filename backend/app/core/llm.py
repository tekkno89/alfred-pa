import json
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_google_vertexai import (
    ChatVertexAI,
    HarmBlockThreshold,
    HarmCategory,
)
from langchain_google_vertexai.model_garden import ChatAnthropicVertex

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """Definition of a tool that the LLM can call."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class ToolCall:
    """A tool call requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Response from the LLM, may contain text and/or tool calls."""

    content: str | None = None
    tool_calls: list[ToolCall] | None = None


@dataclass
class LLMMessage:
    """Standardized message format for LLM interactions."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] | None = None  # for assistant messages requesting tools
    tool_call_id: str | None = None  # for tool result messages


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

    async def generate_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a response, allowing the LLM to call tools."""
        # Default: fall back to plain generate (no tool support)
        text = await self.generate(messages, temperature=temperature, max_tokens=max_tokens)
        return LLMResponse(content=text)

    async def stream_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMResponse]:
        """Stream a response, yielding text chunks or tool calls."""
        # Default: fall back to plain stream (no tool support)
        async for token in self.stream(messages, temperature=temperature, max_tokens=max_tokens):
            yield LLMResponse(content=token)


def _to_langchain_messages(messages: list[LLMMessage]) -> list[BaseMessage]:
    """Convert LLMMessages to LangChain message format."""
    lc_messages: list[BaseMessage] = []
    for msg in messages:
        if msg.role == "system":
            lc_messages.append(SystemMessage(content=msg.content or ""))
        elif msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content or ""))
        elif msg.role == "assistant":
            if msg.tool_calls:
                # Assistant message requesting tool calls
                lc_tool_calls = [
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "args": tc.arguments,
                    }
                    for tc in msg.tool_calls
                ]
                lc_messages.append(
                    AIMessage(content=msg.content or "", tool_calls=lc_tool_calls)
                )
            else:
                lc_messages.append(AIMessage(content=msg.content or ""))
        elif msg.role == "tool":
            lc_messages.append(
                ToolMessage(
                    content=msg.content or "",
                    tool_call_id=msg.tool_call_id or "",
                )
            )
    return lc_messages


def _to_openai_messages(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    """Convert LLMMessages to OpenAI API message format."""
    result: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "assistant" and msg.tool_calls:
            result.append({
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })
        elif msg.role == "tool":
            result.append({
                "role": "tool",
                "content": msg.content or "",
                "tool_call_id": msg.tool_call_id or "",
            })
        else:
            result.append({"role": msg.role, "content": msg.content or ""})
    return result


def _tool_definitions_to_openai(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Convert ToolDefinitions to OpenAI-compatible tool format."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


def _extract_text_content(content: Any) -> str | None:
    """
    Extract plain text from LangChain message content.

    When tools are bound, Anthropic/Claude returns content as a list of
    content blocks like [{'type': 'text', 'text': '...'}] instead of a
    plain string. This normalizes both formats.
    """
    if content is None:
        return None
    if isinstance(content, str):
        return content if content else None
    if isinstance(content, list):
        # Extract text from content blocks
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    # Skip tool_use blocks — handled separately
                    pass
                else:
                    logger.debug(f"Unknown content block type: {block.get('type')}")
            elif isinstance(block, str):
                parts.append(block)
            else:
                logger.debug(f"Unknown content block format: {type(block)}")
        text = "".join(parts)
        return text if text else None
    logger.debug(f"Unexpected content type: {type(content)}")
    return str(content) if content else None


def _tool_definitions_to_langchain(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Convert ToolDefinitions to LangChain tool format for bind_tools."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
        for tool in tools
    ]


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

    async def generate_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": _to_openai_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "tools": _tool_definitions_to_openai(tools),
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
            choice = data["choices"][0]["message"]

            tool_calls = None
            if choice.get("tool_calls"):
                tool_calls = [
                    ToolCall(
                        id=tc["id"],
                        name=tc["function"]["name"],
                        arguments=json.loads(tc["function"]["arguments"]),
                    )
                    for tc in choice["tool_calls"]
                ]

            return LLMResponse(
                content=choice.get("content"),
                tool_calls=tool_calls,
            )

    async def stream_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMResponse]:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": _to_openai_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "tools": _tool_definitions_to_openai(tools),
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

                # Buffer tool call chunks
                tool_call_buffers: dict[int, dict[str, Any]] = {}

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    delta = data["choices"][0].get("delta", {})

                    # Handle text content
                    content = delta.get("content")
                    if content:
                        yield LLMResponse(content=content)

                    # Handle tool call chunks
                    if delta.get("tool_calls"):
                        for tc_chunk in delta["tool_calls"]:
                            idx = tc_chunk["index"]
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {
                                    "id": tc_chunk.get("id", ""),
                                    "name": tc_chunk.get("function", {}).get("name", ""),
                                    "arguments": "",
                                }
                            else:
                                if tc_chunk.get("id"):
                                    tool_call_buffers[idx]["id"] = tc_chunk["id"]
                                if tc_chunk.get("function", {}).get("name"):
                                    tool_call_buffers[idx]["name"] = tc_chunk["function"]["name"]
                            # Accumulate arguments string
                            args_chunk = tc_chunk.get("function", {}).get("arguments", "")
                            if args_chunk:
                                tool_call_buffers[idx]["arguments"] += args_chunk

                # After stream ends, yield any accumulated tool calls
                if tool_call_buffers:
                    tool_calls = [
                        ToolCall(
                            id=buf["id"],
                            name=buf["name"],
                            arguments=json.loads(buf["arguments"]) if buf["arguments"] else {},
                        )
                        for buf in tool_call_buffers.values()
                    ]
                    yield LLMResponse(tool_calls=tool_calls)


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

    async def generate_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        model = self._create_model(temperature, max_tokens)
        lc_tools = _tool_definitions_to_langchain(tools)
        model_with_tools = model.bind_tools(lc_tools)
        lc_messages = _to_langchain_messages(messages)
        response = await model_with_tools.ainvoke(lc_messages)

        tool_calls = None
        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.get("id", f"call_{i}"),
                    name=tc["name"],
                    arguments=tc.get("args", {}),
                )
                for i, tc in enumerate(response.tool_calls)
            ]

        return LLMResponse(
            content=_extract_text_content(response.content),
            tool_calls=tool_calls,
        )

    async def stream_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMResponse]:
        model = self._create_model(temperature, max_tokens, streaming=True)
        lc_tools = _tool_definitions_to_langchain(tools)
        model_with_tools = model.bind_tools(lc_tools)
        lc_messages = _to_langchain_messages(messages)

        collected_tool_calls: list[dict[str, Any]] = []

        async for chunk in model_with_tools.astream(lc_messages):
            text = _extract_text_content(chunk.content)
            if text:
                yield LLMResponse(content=text)
            if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                for tc_chunk in chunk.tool_call_chunks:
                    # Accumulate tool call info
                    idx = tc_chunk.get("index", len(collected_tool_calls))
                    while len(collected_tool_calls) <= idx:
                        collected_tool_calls.append({"id": "", "name": "", "args_str": ""})
                    if tc_chunk.get("id"):
                        collected_tool_calls[idx]["id"] = tc_chunk["id"]
                    if tc_chunk.get("name"):
                        collected_tool_calls[idx]["name"] = tc_chunk["name"]
                    if tc_chunk.get("args"):
                        collected_tool_calls[idx]["args_str"] += tc_chunk["args"]

        if collected_tool_calls:
            tool_calls = []
            for i, tc in enumerate(collected_tool_calls):
                if tc["name"]:
                    args = json.loads(tc["args_str"]) if tc["args_str"] else {}
                    tool_calls.append(ToolCall(
                        id=tc["id"] or f"call_{i}",
                        name=tc["name"],
                        arguments=args,
                    ))
            if tool_calls:
                yield LLMResponse(tool_calls=tool_calls)


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

    async def generate_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        model = self._create_model(temperature, max_tokens)
        lc_tools = _tool_definitions_to_langchain(tools)
        model_with_tools = model.bind_tools(lc_tools)
        lc_messages = _to_langchain_messages(messages)
        response = await model_with_tools.ainvoke(lc_messages)

        tool_calls = None
        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.get("id", f"call_{i}"),
                    name=tc["name"],
                    arguments=tc.get("args", {}),
                )
                for i, tc in enumerate(response.tool_calls)
            ]

        return LLMResponse(
            content=_extract_text_content(response.content),
            tool_calls=tool_calls,
        )

    async def stream_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMResponse]:
        model = self._create_model(temperature, max_tokens)
        lc_tools = _tool_definitions_to_langchain(tools)
        model_with_tools = model.bind_tools(lc_tools)
        lc_messages = _to_langchain_messages(messages)

        collected_tool_calls: list[dict[str, Any]] = []
        chunk_count = 0
        text_chunks = 0

        async for chunk in model_with_tools.astream(lc_messages):
            chunk_count += 1
            text = _extract_text_content(chunk.content)
            if text:
                text_chunks += 1
                yield LLMResponse(content=text)
            if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                for tc_chunk in chunk.tool_call_chunks:
                    idx = tc_chunk.get("index", len(collected_tool_calls))
                    while len(collected_tool_calls) <= idx:
                        collected_tool_calls.append({"id": "", "name": "", "args_str": ""})
                    if tc_chunk.get("id"):
                        collected_tool_calls[idx]["id"] = tc_chunk["id"]
                    if tc_chunk.get("name"):
                        collected_tool_calls[idx]["name"] = tc_chunk["name"]
                    if tc_chunk.get("args"):
                        collected_tool_calls[idx]["args_str"] += tc_chunk["args"]

        logger.info(
            f"VertexClaude stream_with_tools: {chunk_count} chunks, "
            f"{text_chunks} text, {len(collected_tool_calls)} tool calls"
        )

        if collected_tool_calls:
            tool_calls = []
            for i, tc in enumerate(collected_tool_calls):
                if tc["name"]:
                    args = json.loads(tc["args_str"]) if tc["args_str"] else {}
                    tool_calls.append(ToolCall(
                        id=tc["id"] or f"call_{i}",
                        name=tc["name"],
                        arguments=args,
                    ))
            if tool_calls:
                yield LLMResponse(tool_calls=tool_calls)


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
