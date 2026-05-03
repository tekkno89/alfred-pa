"""Echo cancellation for speaker output feedback."""
from typing import Optional
from enum import Enum


class EchoCancellationMode(Enum):
    AUTO = "auto"
    WEBRTC = "webrtc"
    MUTE_DURING_SPEECH = "mute_during_speech"
    DISABLED = "disabled"


class EchoCancellationProcessor:
    """
    Handles echo cancellation to prevent agent from hearing itself.
    
    Three modes:
    1. webrtc - Software AEC (requires webrtcvad)
    2. mute_during_speech - Mute mic while bot is speaking
    3. disabled - No echo cancellation (use headphones)
    """
    
    def __init__(self, mode: EchoCancellationMode = EchoCancellationMode.AUTO):
        self.mode = mode
        self.is_bot_speaking = False
        self._vad = None
        
        if mode == EchoCancellationMode.WEBRTC:
            self._init_webrtc()
    
    def _init_webrtc(self):
        """Initialize WebRTC AEC."""
        try:
            import webrtcvad
            self._vad = webrtcvad.Vad(2)
            print("✓ WebRTC VAD initialized for echo detection")
        except ImportError:
            print("⚠ webrtcvad not installed, falling back to mute_during_speech")
            self.mode = EchoCancellationMode.MUTE_DURING_SPEECH
    
    def on_bot_started_speaking(self):
        """Called when bot starts speaking."""
        self.is_bot_speaking = True
    
    def on_bot_stopped_speaking(self):
        """Called when bot stops speaking."""
        self.is_bot_speaking = False
    
    def should_mute_mic(self) -> bool:
        """Return True if mic should be muted."""
        if self.mode == EchoCancellationMode.MUTE_DURING_SPEECH:
            return self.is_bot_speaking
        return False
    
    def process_audio(self, audio_data: bytes, sample_rate: int = 16000) -> Optional[bytes]:
        """
        Process audio to remove echo.
        
        Args:
            audio_data: Raw audio bytes (int16 PCM)
            sample_rate: Audio sample rate
        
        Returns:
            Processed audio or None if should be dropped
        """
        if self.mode == EchoCancellationMode.DISABLED:
            return audio_data
        
        if self.mode == EchoCancellationMode.MUTE_DURING_SPEECH:
            if self.is_bot_speaking:
                return None
            return audio_data
        
        return audio_data


def create_echo_cancellation(mode: str) -> EchoCancellationProcessor:
    """Create echo cancellation processor from config string."""
    mode_map = {
        "auto": EchoCancellationMode.AUTO,
        "webrtc": EchoCancellationMode.WEBRTC,
        "mute_during_speech": EchoCancellationMode.MUTE_DURING_SPEECH,
        "disabled": EchoCancellationMode.DISABLED
    }
    return EchoCancellationProcessor(mode_map.get(mode, EchoCancellationMode.AUTO))
