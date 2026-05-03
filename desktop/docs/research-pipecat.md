# Research: Pipecat Framework

**Source:** https://github.com/pipecat-ai/pipecat  
**Docs:** https://docs.pipecat.ai

## Overview

Pipecat is an open-source Python framework for building real-time voice and multimodal conversational AI agents.

## Key Concepts

### Frame-Based Architecture

Data flows through pipelines as "frames" - objects containing audio, text, or other data types.

**Frame Categories:**
- **System Frames**: Pipeline lifecycle, interruptions, speaking state (`StartFrame`, `EndFrame`, `CancelFrame`)
- **Control Frames**: Response boundaries, service settings
- **Data Frames**: Audio, image, text, transcription (`AudioRawFrame`, `TextFrame`, `TranscriptionFrame`)
- **LLM Frames**: Context frames, function calling helpers

### Processors

Processors are the building blocks. Each processor transforms frames as they pass through.

**Common Processors:**
- `SileroVADAnalyzer` - Voice Activity Detection
- `LLMContextAggregatorPair` - Manages conversation context
- Frame filters (pass, block, transform)

### Services

Services wrap AI APIs and emit/consume frames:

- **STT Services**: Speech-to-text (Deepgram, OpenAI, Whisper, etc.)
- **TTS Services**: Text-to-speech (Cartesia, ElevenLabs, OpenAI, etc.)
- **LLM Services**: Language models (OpenAI, Anthropic, etc.)
- **S2S Services**: Speech-to-speech (OpenAI Realtime, Gemini Live)

### Transports

Transports handle audio I/O:

- **DailyTransport** - WebRTC via Daily.co
- **LiveKitTransport** - WebRTC via LiveKit
- **SmallWebRTCTransport** - Peer-to-peer WebRTC
- **FastAPIWebsocketTransport** - WebSocket for web apps
- **Local** - Local audio (for testing)

## Pipeline Pattern

```python
from pipecat.pipeline import Pipeline
from pipecat.services import DeepgramSTT, OpenAI, CartesiaTTS

# Create services
stt = DeepgramSTTService(api_key="...")
llm = OpenAIService(api_key="...")
tts = CartesiaTTSService(api_key="...")

# Build pipeline
pipeline = Pipeline([
    transport.input(),   # Receive audio
    stt,                 # Transcribe
    llm,                 # Generate response
    tts,                 # Synthesize speech
    transport.output(),  # Send audio
])

# Run pipeline
runner = PipelineRunner()
task = PipelineTask(pipeline)
await runner.run(task)
```

## Custom TTS Service

To create a custom TTS service (like for Chatterbox):

```python
from pipecat.services.tts import TTSService
from pipecat.frames.frames import TTSStartedFrame, TTSAudioRawFrame, TTSStoppedFrame

class CustomTTSService(TTSService):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Initialize your TTS model here
    
    async def run_tts(self, text: str):
        # 1. Yield start frame
        yield TTSStartedFrame()
        
        # 2. Generate audio chunks
        audio_chunks = self._generate_audio(text)
        for chunk in audio_chunks:
            yield TTSAudioRawFrame(
                audio=chunk,
                sample_rate=self.sample_rate,
                num_channels=1
            )
        
        # 3. Yield stop frame
        yield TTSStoppedFrame()
```

## VAD (Voice Activity Detection)

Pipecat includes Silero VAD for detecting speech:

```python
from pipecat.vad.silero import SileroVADAnalyzer

vad = SileroVADAnalyzer()
# VAD is typically configured in transport params
```

## Interruption Handling

Pipecat has built-in interruption support:

- `CancelFrame` stops current generation
- `InterruptionFrame` signals user is speaking over bot
- Configure via `PipelineParams(allow_interruptions=True)`

## Key Imports for Our Project

```python
# Core
from pipecat.pipeline import Pipeline, PipelineTask, PipelineRunner
from pipecat.processors import FrameProcessor

# Frames
from pipecat.frames.frames import (
    Frame,
    AudioRawFrame,
    TextFrame,
    TranscriptionFrame,
    TTSStartedFrame,
    TTSAudioRawFrame,
    TTSStoppedFrame,
    StartFrame,
    EndFrame,
)

# Services (base classes)
from pipecat.services.tts import TTSService
from pipecat.services.stt import STTService

# VAD
from pipecat.vad.silero import SileroVADAnalyzer

# Context
from pipecat.context import LLMContext
from pipecat.processors.aggregators import LLMContextAggregatorPair
```

## Gotchas

1. **Async everywhere** - All processing is async; sync operations need `run_in_executor`
2. **Frame ordering matters** - Audio must be transcribed before LLM, text synthesized before playback
3. **Generator segments** - STT returns a generator; iterate to trigger actual transcription
4. **Transport selection** - For local CLI app, use local transport or custom PyAudio implementation

## For Desktop POC

Since we're building a local CLI app (not webRTC), we may not need the full Pipecat transport layer. We can:

1. Use Pipecat's service base classes (TTSService, STTService) 
2. Build custom audio I/O with PyAudio
3. Or use Pipecat's local transport if available

**Decision:** We'll start with custom PyAudio I/O and potentially integrate Pipecat services later for their VAD and frame processing utilities.
