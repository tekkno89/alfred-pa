"""Configuration management with YAML support."""
from pathlib import Path
from typing import Optional, Literal
import yaml
from pydantic import BaseModel, Field


class STTConfig(BaseModel):
    """Speech-to-text configuration."""
    model: str = "large-v3-turbo"
    device: str = "auto"
    language: str = "en"


class TTSConfig(BaseModel):
    """Text-to-speech configuration."""
    model: str = "chatterbox-turbo"
    device: str = "auto"
    reference_voice: Optional[str] = None
    exaggeration: float = 0.5
    cfg_weight: float = 0.5
    sample_rate: int = 24000


class LLMConfig(BaseModel):
    """LLM configuration."""
    enabled: bool = False
    model: str = "gpt-4o"


class BackendConfig(BaseModel):
    """Backend configuration - just a URL like the frontend uses."""
    url: str = "http://localhost:8000"


class FillerConfig(BaseModel):
    """Filler response configuration."""
    enabled: bool = True
    use_defaults: bool = True
    custom_file: Optional[str] = None
    timeout_ms: int = 300


class PipelineConfig(BaseModel):
    """Pipeline configuration."""
    allow_interruptions: bool = True
    min_words_interruption: int = 2
    echo_cancellation: Literal["auto", "webrtc", "mute_during_speech", "disabled"] = "auto"


class DebugConfig(BaseModel):
    """Debug/development configuration."""
    log_level: str = "INFO"
    save_audio: bool = False
    audio_output_dir: str = "debug/audio"


class Settings(BaseModel):
    """Root configuration model."""
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    backend: BackendConfig = Field(default_factory=BackendConfig)
    fillers: FillerConfig = Field(default_factory=FillerConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    debug: DebugConfig = Field(default_factory=DebugConfig)
    
    @classmethod
    def load(cls, config_path: str = "config/settings.yaml") -> "Settings":
        """Load settings from YAML file."""
        path = Path(config_path)
        if not path.exists():
            print(f"Warning: Config file not found at {config_path}, using defaults")
            return cls()
        
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        
        return cls(**data)
    
    def get_backend_url(self) -> str:
        """Get the backend URL."""
        return self.backend.url.rstrip("/")


def get_device(config_device: str) -> str:
    """Determine the actual device to use (auto -> mps or cpu)."""
    import torch
    
    if config_device == "auto":
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    
    return config_device
