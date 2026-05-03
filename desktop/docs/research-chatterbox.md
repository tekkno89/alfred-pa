# Research: Chatterbox TTS

**Source:** https://github.com/resemble-ai/chatterbox  
**Apple Silicon Guide:** https://huggingface.co/Jimmi42/chatterbox-tts-apple-silicon-code

## Overview

Chatterbox is a state-of-the-art open-source TTS model by Resemble AI with zero-shot voice cloning. It supports Apple Silicon via MPS.

## Models

| Model | Size | Languages | Best For |
|-------|------|-----------|----------|
| **Chatterbox-Turbo** | 350M | English | Voice agents, low latency |
| Chatterbox-Multilingual | 500M | 23+ languages | Global applications |
| Chatterbox | 500M | English | Creative controls |

**We use Chatterbox-Turbo** for the desktop voice agent.

## Installation

**CRITICAL: Install order matters for Apple Silicon!**

```bash
# 1. Install PyTorch first
pip install torch torchvision torchaudio

# 2. Install Chatterbox with --no-deps to prevent torch downgrade
pip install chatterbox-tts --no-deps

# 3. Install remaining dependencies
pip install numpy scipy librosa soundfile
```

## API Usage

### Basic Usage

```python
import torch
from chatterbox.tts import ChatterboxTurboTTS

# Detect device
device = "mps" if torch.backends.mps.is_available() else "cpu"

# Load model
model = ChatterboxTurboTTS.from_pretrained(device=device)

# Generate speech
text = "Hello, this is a test of the voice agent."
wav = model.generate(text)

# wav is a tensor at 24kHz
# Convert to numpy/int16 for playback
audio = (wav.cpu().numpy() * 32767).astype(np.int16)
```

### Voice Cloning

```python
# With reference voice (10-15 second WAV file)
wav = model.generate(
    text="Hello, this is a test.",
    audio_prompt_path="reference_voices/my_voice.wav"
)
```

### Generation Parameters

```python
wav = model.generate(
    text="Hello!",
    audio_prompt_path="voice.wav",  # Optional
    exaggeration=0.5,  # 0.0-1.0, expressiveness
    cfg_weight=0.5,    # 0.0-1.0, classifier-free guidance
)
```

- **exaggeration:** Higher = more expressive/dramatic (default 0.5)
- **cfg_weight:** Higher = more consistent pacing (default 0.5)
  - Lower (~0.3) for fast-speaking reference voices
  - Higher for slower, more deliberate speech

### Paralinguistic Tags

Chatterbox-Turbo supports tags for natural speech:

```python
text = "Hi there [chuckle], have you got a minute?"
# Supported: [cough], [laugh], [chuckle], etc.
```

## Reference Voice Requirements

- **Format:** WAV (uncompressed)
- **Duration:** 10-15 seconds recommended
- **Sample Rate:** 24kHz or higher
- **Channels:** Mono, single speaker
- **Quality:** Clear, conversational style, minimal background noise

## Apple Silicon Specifics

### MPS Issues

MPS may have "placeholder storage" errors on some configurations:

```python
try:
    model = ChatterboxTurboTTS.from_pretrained(device="mps")
except RuntimeError as e:
    if "placeholder" in str(e).lower():
        print("MPS error, falling back to CPU")
        model = ChatterboxTurboTTS.from_pretrained(device="cpu")
```

### Memory Management

```python
# Clear MPS cache periodically
if torch.backends.mps.is_available():
    torch.mps.empty_cache()
```

## Output Format

- **Sample Rate:** 24000 Hz
- **Format:** torch.Tensor (float32, -1 to 1)
- **Conversion to int16 PCM:**

```python
import numpy as np

# Convert tensor to int16 bytes
audio_np = wav.squeeze().cpu().numpy()
audio_int16 = (audio_np * 32767).astype(np.int16)
audio_bytes = audio_int16.tobytes()
```

## Key Points for Implementation

1. **Install order critical:** torch first, chatterbox with --no-deps
2. **Device selection:** Check MPS availability, fallback to CPU
3. **Sample rate:** 24kHz output (not 16kHz like Whisper)
4. **Voice cloning:** Pre-load reference voice path
5. **Error handling:** Catch MPS placeholder errors

## Custom Pipecat TTSService Pattern

```python
from pipecat.services.tts import TTSService
from pipecat.frames.frames import TTSStartedFrame, TTSAudioRawFrame, TTSStoppedFrame
from chatterbox.tts import ChatterboxTurboTTS
import torch
import numpy as np

class ChatterboxTTSService(TTSService):
    def __init__(self, reference_voice: str = None, **kwargs):
        super().__init__(sample_rate=24000, **kwargs)
        
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._model = ChatterboxTurboTTS.from_pretrained(device=device)
        self._reference_voice = reference_voice
    
    async def run_tts(self, text: str):
        yield TTSStartedFrame()
        
        # Generate audio
        wav = self._model.generate(
            text,
            audio_prompt_path=self._reference_voice
        )
        
        # Convert to int16 bytes
        audio_np = wav.squeeze().cpu().numpy()
        audio_int16 = (audio_np * 32767).astype(np.int16)
        
        yield TTSAudioRawFrame(
            audio=audio_int16.tobytes(),
            sample_rate=24000,
            num_channels=1
        )
        
        yield TTSStoppedFrame()
```
