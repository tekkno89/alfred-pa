# Research: Whisper MLX (via Pipecat)

**Package:** `mlx-whisper` (wrapped by Pipecat's `WhisperSTTServiceMLX`)  
**Pipecat Docs:** https://docs.pipecat.ai/server/services/stt/whisper  
**Source:** https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/services/whisper/stt.py

## Overview

MLX Whisper is Apple's MLX framework implementation of OpenAI's Whisper model, optimized for Apple Silicon. Pipecat provides `WhisperSTTServiceMLX` which wraps mlx-whisper.

## Installation

```bash
# Install Pipecat with Whisper support (includes both faster-whisper and mlx-whisper)
pip install "pipecat-ai[whisper]"

# On Apple Silicon, mlx-whisper is what you need
```

## API Usage

### Service Class

```python
from pipecat.services.whisper.stt import WhisperSTTServiceMLX
from pipecat.services.whisper.stt import MLXModel

# Create service with recommended model
stt = WhisperSTTServiceMLX(
    model=MLXModel.LARGE_V3_TURBO,  # Best speed/quality balance
    language="en"
)

# Or for machines with less unified memory
stt = WhisperSTTServiceMLX(
    model=MLXModel.LARGE_V3_TURBO_Q4,  # Quantized, ~4GB less memory
    language="en"
)
```

### Available Models

| Model | Memory | Speed | Quality |
|-------|--------|-------|---------|
| `MLXModel.LARGE_V3_TURBO` | ~4GB | Fast | Best |
| `MLXModel.LARGE_V3_TURBO_Q4` | ~2GB | Fast | Good (quantized) |
| `MLXModel.LARGE_V3` | ~4GB | Slower | Best |

### Transcription

```python
# Process audio through the service
# The service integrates with Pipecat's frame-based pipeline
async for frame in stt.process_audio(audio_frame):
    if isinstance(frame, TranscriptionFrame):
        print(frame.text)
```

## Audio Format Requirements

- **Sample Rate:** 16kHz (standard for Whisper)
- **Format:** int16 PCM, mono
- **Channels:** 1 (mono)

## Performance on Apple Silicon

- **M4/M5 Macs:** Excellent performance with MPS GPU acceleration
- **M1-M3:** Good performance, consider Q4 model for memory efficiency
- **Intel Macs:** Not supported (use faster-whisper instead)

## Integration with Custom Pipeline

For our desktop POC, we can use the service directly or wrap it:

```python
from pipecat.services.whisper.stt import WhisperSTTServiceMLX, MLXModel

class WhisperSTTWrapper:
    def __init__(self, model: str = "large-v3-turbo"):
        self.service = WhisperSTTServiceMLX(
            model=MLXModel.LARGE_V3_TURBO,
            language="en"
        )
    
    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        # Create audio frame and process
        from pipecat.frames.frames import AudioRawFrame
        
        frame = AudioRawFrame(
            audio=audio_data,
            sample_rate=sample_rate,
            num_channels=1
        )
        
        text_parts = []
        async for output_frame in self.service.process_frame(frame):
            if hasattr(output_frame, 'text'):
                text_parts.append(output_frame.text)
        
        return " ".join(text_parts)
```

## Key Points for Implementation

1. **Use `WhisperSTTServiceMLX`** (not `WhisperSTTService` which uses faster-whisper)
2. **Model choice:** `LARGE_V3_TURBO` for best balance, `LARGE_V3_TURBO_Q4` for memory-constrained systems
3. **Audio format:** 16kHz int16 mono PCM
4. **Apple Silicon only:** This service is specifically optimized for M-series chips

## Gotchas

- Requires Apple Silicon (M1/M2/M3/M4/M5)
- Model downloads on first use (~1-4GB depending on model)
- Async API - all methods are async
- For Intel Macs, use `WhisperSTTService` (faster-whisper) instead
