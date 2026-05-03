"""Remote LLM client for Alfred backend connection."""
from typing import AsyncIterator, Optional
import httpx
from openai import AsyncOpenAI

from src.config import Settings


class RemoteLLMService:
    """OpenAI-compatible streaming LLM client for Alfred backend."""
    
    def __init__(self, settings: Settings):
        if not settings.llm.enabled:
            raise ValueError("LLM is not enabled in config. Set llm.enabled: true")
        
        self.settings = settings
        self.base_url = settings.get_backend_url()
        self.model = settings.llm.model
        
        # Initialize OpenAI client with custom base URL
        self.client = AsyncOpenAI(
            api_key="dummy-key",  # Some servers don't require real key
            base_url=f"{self.base_url}/v1"
        )
        
        print(f"LLM client initialized: {self.base_url}")
    
    async def generate_stream(
        self,
        messages: list[dict],
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream tokens from the LLM.
        
        Args:
            messages: OpenAI-format message list
            **kwargs: Additional parameters (temperature, etc.)
        
        Yields:
            Text tokens as they arrive
        """
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                **kwargs
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        
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
