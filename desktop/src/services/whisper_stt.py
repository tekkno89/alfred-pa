"""Whisper MLX speech-to-text service wrapper."""
import asyncio
from typing import Optional
from pipecat.services.whisper.stt import WhisperSTTServiceMLX, MLXModel
from pipecat.frames.frames import TranscriptionFrame, ErrorFrame

from src.config import Settings, get_device


class WhisperSTTService:
    """Wrapper for Whisper MLX with simpler interface."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.device = get_device(settings.stt.device)
        self._service: Optional[WhisperSTTServiceMLX] = None
        self._model_map = {
            "large-v3-turbo": MLXModel.LARGE_V3_TURBO,
            "large-v3-turbo-q4": MLXModel.LARGE_V3_TURBO_Q4,
            "large-v3": MLXModel.LARGE_V3,
        }
        
    def _ensure_service_loaded(self):
        """Lazy-load service on first use."""
        if self._service is None:
            model_enum = self._model_map.get(
                self.settings.stt.model, 
                MLXModel.LARGE_V3_TURBO
            )
            model_path = model_enum.value
            print(f"Loading Whisper model '{self.settings.stt.model}' ({model_path}) on {self.device}...")
            self._service = WhisperSTTServiceMLX(
                settings=WhisperSTTServiceMLX.Settings(
                    model=model_path,
                    language=self.settings.stt.language
                )
            )
            print("✓ Whisper model loaded")
    
    async def warmup(self):
        """Pre-load model weights."""
        self._ensure_service_loaded()
        print("Warming up model (downloading weights if needed)...")
        await self.transcribe(b'\x00' * 1024)  # Silent audio to trigger model load
        print("✓ Model ready")
    
    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """
        Transcribe audio data to text.
        
        Args:
            audio_data: Raw audio bytes (int16 PCM, mono)
            sample_rate: Audio sample rate (default 16000)
        
        Returns:
            Transcribed text
        """
        self._ensure_service_loaded()
        
        # Use run_stt which is an async generator
        text_parts = []
        async for frame in self._service.run_stt(audio_data):
            if isinstance(frame, ErrorFrame):
                print(f"  ❌ Error: {frame.error}")
            elif isinstance(frame, TranscriptionFrame):
                text_parts.append(frame.text)
        
        return " ".join(text_parts).strip()


async def create_stt_service(settings: Settings) -> WhisperSTTService:
    """Create and initialize STT service."""
    service = WhisperSTTService(settings)
    return service
