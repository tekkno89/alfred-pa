"""Remote LLM client for Alfred backend connection."""
from typing import AsyncIterator, Optional
import json

import httpx

from src.config import Settings


class RemoteLLMService:
    """HTTP client for Alfred backend voice chat endpoint."""
    
    def __init__(self, settings: Settings):
        if not settings.llm.enabled:
            raise ValueError("LLM is not enabled in config. Set llm.enabled: true")
        
        self.settings = settings
        self.base_url = settings.get_backend_url()
        
        print(f"LLM client initialized: {self.base_url}")
    
    async def generate_stream(
        self,
        messages: list[dict],
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream tokens from the backend.
        
        Args:
            messages: OpenAI-format message list (only last user message is used)
            **kwargs: Additional parameters (ignored)
        
        Yields:
            Text tokens as they arrive
        """
        # Get the last user message
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break
        
        if not user_message:
            yield "No message provided."
            return
        
        url = f"{self.base_url}/api/voice-chat"
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    url,
                    params={"message": user_message},
                ) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix
                            
                            if data == "[DONE]":
                                break
                            
                            if data.startswith("ERROR:"):
                                error_msg = data[6:].strip()
                                raise RuntimeError(error_msg)
                            
                            yield data
        
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Cannot connect to backend at {self.base_url}. "
                f"Check your connection settings in config/settings.yaml"
            ) from e
        
        except Exception as e:
            raise RuntimeError(f"LLM request failed: {e}") from e
    
    async def generate(
        self,
        messages: list[dict],
        **kwargs
    ) -> str:
        """Generate complete response (non-streaming)."""
        full_response = []
        async for token in self.generate_stream(messages, **kwargs):
            full_response.append(token)
        return "".join(full_response)


async def create_llm_service(settings: Settings) -> Optional[RemoteLLMService]:
    """Create LLM service if enabled."""
    if not settings.llm.enabled:
        print("LLM not enabled - skipping LLM service initialization")
        return None
    
    try:
        return RemoteLLMService(settings)
    except Exception as e:
        print(f"⚠ Warning: Failed to initialize LLM service: {e}")
        return None
