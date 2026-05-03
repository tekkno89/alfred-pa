"""Chatterbox TTS service with voice cloning support."""
from pathlib import Path
from typing import Optional
import torch
import numpy as np
from chatterbox.tts import ChatterboxTTS

from src.config import Settings, get_device
from src.utils.device import get_device_with_fallback


class ChatterboxTTSService:
    """Chatterbox-Turbo TTS service with voice cloning."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.device = get_device_with_fallback() if settings.tts.device == "auto" else get_device(settings.tts.device)
        self.sample_rate = settings.tts.sample_rate
        self.exaggeration = settings.tts.exaggeration
        self.cfg_weight = settings.tts.cfg_weight
        
        # Reference voice for cloning
        self.reference_path = None
        if settings.tts.reference_voice:
            ref_path = Path(settings.tts.reference_voice)
            if not ref_path.exists():
                print(f"⚠ Warning: Reference voice not found: {ref_path}")
                print("  Using default voice instead.")
            else:
                self.reference_path = ref_path
                print(f"✓ Reference voice loaded: {ref_path.name}")
        
        # Lazy-load model
        self._model = None
    
    def _ensure_model_loaded(self):
        """Load model on first use."""
        if self._model is None:
            print(f"Loading Chatterbox model on {self.device}...")
            try:
                self._model = ChatterboxTTS.from_pretrained(device=self.device)
                print("✓ Chatterbox model loaded")
            except Exception as e:
                print(f"⚠ Chatterbox load error: {e}")
                if "placeholder" in str(e).lower() and self.device == "mps":
                    print("  MPS placeholder error detected, falling back to CPU...")
                    self.device = "cpu"
                    self._model = ChatterboxTTS.from_pretrained(device=self.device)
                    print("✓ Chatterbox loaded on CPU (fallback)")
                else:
                    raise
    
    def generate_audio(self, text: str) -> bytes:
        """
        Generate audio for text.
        
        Args:
            text: Text to synthesize
        
        Returns:
            Audio data as int16 PCM bytes
        """
        self._ensure_model_loaded()
        
        # Generate
        wav = self._model.generate(
            text,
            audio_prompt_path=str(self.reference_path) if self.reference_path else None,
            exaggeration=self.exaggeration,
            cfg_weight=self.cfg_weight
        )
        
        # Convert to int16 PCM
        if isinstance(wav, torch.Tensor):
            audio = (wav.squeeze().cpu().numpy() * 32767).astype(np.int16)
        else:
            audio = (np.array(wav) * 32767).astype(np.int16)
        
        return audio.tobytes()
    
    def save_audio(self, text: str, output_path: str):
        """Generate and save audio to file."""
        audio = self.generate_audio(text)
        
        import wave
        with wave.open(output_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio)
        
        print(f"✓ Audio saved to {output_path}")


async def create_tts_service(settings: Settings) -> ChatterboxTTSService:
    """Create TTS service."""
    return ChatterboxTTSService(settings)
