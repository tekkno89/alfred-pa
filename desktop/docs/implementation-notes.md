# Implementation Notes

Quick reference for common operations and patterns.

## Pipecat

### Key Imports

```python
# Pipeline
from pipecat.pipeline import Pipeline, PipelineTask, PipelineRunner
from pipecat.processors import FrameProcessor

# Frames
from pipecat.frames.frames import (
    Frame, AudioRawFrame, TextFrame, TranscriptionFrame,
    TTSStartedFrame, TTSAudioRawFrame, TTSStoppedFrame,
)

# Whisper MLX
from pipecat.services.whisper.stt import WhisperSTTServiceMLX, MLXModel

# Services base
from pipecat.services.tts import TTSService

# VAD
from pipecat.vad.silero import SileroVADAnalyzer
```

### WhisperSTTServiceMLX

```python
from pipecat.services.whisper.stt import WhisperSTTServiceMLX, MLXModel

stt = WhisperSTTServiceMLX(
    model=MLXModel.LARGE_V3_TURBO,
    language="en"
)
```

### Custom TTS Service Pattern

```python
from pipecat.services.tts import TTSService
from pipecat.frames.frames import TTSStartedFrame, TTSAudioRawFrame, TTSStoppedFrame

class CustomTTS(TTSService):
    def __init__(self, **kwargs):
        super().__init__(sample_rate=24000, **kwargs)
        # Load model
    
    async def run_tts(self, text: str):
        yield TTSStartedFrame()
        # Generate audio...
        yield TTSAudioRawFrame(audio=bytes, sample_rate=24000, num_channels=1)
        yield TTSStoppedFrame()
```

---

## Chatterbox TTS

### Install Order (CRITICAL)

```bash
pip install torch torchvision torchaudio
pip install chatterbox-tts --no-deps
pip install numpy scipy librosa soundfile
```

### Model Loading

```python
import torch
from chatterbox.tts import ChatterboxTurboTTS

# Device selection with fallback
device = "mps" if torch.backends.mps.is_available() else "cpu"

try:
    tts = ChatterboxTurboTTS.from_pretrained(device=device)
except RuntimeError as e:
    if "placeholder" in str(e).lower():
        tts = ChatterboxTurboTTS.from_pretrained(device="cpu")
```

### Generate Audio

```python
# Basic
wav = tts.generate("Hello world")

# With voice cloning
wav = tts.generate(
    text="Hello world",
    audio_prompt_path="voice.wav",
    exaggeration=0.5,
    cfg_weight=0.5
)

# Convert to int16 bytes for playback
import numpy as np
audio_np = wav.squeeze().cpu().numpy()
audio_int16 = (audio_np * 32767).astype(np.int16)
audio_bytes = audio_int16.tobytes()
```

---

## Audio (PyAudio)

### Input Stream (Mic, 16kHz for Whisper)

```python
import pyaudio

p = pyaudio.PyAudio()
stream = p.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=16000,
    input=True,
    frames_per_buffer=1024
)
data = stream.read(1024, exception_on_overflow=False)
```

### Output Stream (Speaker, 24kHz from Chatterbox)

```python
stream = p.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=24000,
    output=True
)
stream.write(audio_bytes)
```

### Volume Detection

```python
import audioop
rms = audioop.rms(data, 2)  # sample_width=2 for int16
```

---

## Device Detection

```python
import torch

def get_device():
    if torch.backends.mps.is_available():
        try:
            device = torch.device("mps")
            x = torch.randn(3, 3, device=device)
            _ = x @ x.T
            return "mps"
        except RuntimeError:
            return "cpu"
    return "cpu"
```

---

## Key Audio Formats

| Component | Sample Rate | Format |
|-----------|-------------|--------|
| Whisper (input) | 16kHz | int16 PCM mono |
| Chatterbox (output) | 24kHz | int16 PCM mono |
| PyAudio | configurable | int16 |

---

## Open Questions / Notes

1. **Pipecat integration level**: Can we use Pipecat's full pipeline or build custom with just the services?
   - For CLI-only POC, custom PyAudio loop may be simpler
   - Can integrate Pipecat's `WhisperSTTServiceMLX` as a component

2. **MPS stability**: Watch for placeholder storage errors, have CPU fallback ready

3. **Reference voice**: Need user to provide 10-15s WAV for voice cloning

4. **Latency**: Chatterbox-Turbo is optimized for low latency (~200ms on M4)
