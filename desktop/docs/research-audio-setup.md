# Research: Apple Silicon Audio Setup

## PyAudio on macOS

### Installation

```bash
# Install PortAudio first
brew install portaudio

# Then install PyAudio
pip install pyaudio
```

### Audio Device Enumeration

```python
import pyaudio

p = pyaudio.PyAudio()

# List all devices
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    print(f"{i}: {info['name']}")
    print(f"   Input channels: {info['maxInputChannels']}")
    print(f"   Output channels: {info['maxOutputChannels']}")
    print(f"   Sample rate: {info['defaultSampleRate']}")

p.terminate()
```

### Input Stream (Microphone)

```python
import pyaudio

p = pyaudio.PyAudio()

# Standard Whisper input format
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000  # 16kHz for Whisper
CHUNK = 1024

stream = p.open(
    format=FORMAT,
    channels=CHANNELS,
    rate=RATE,
    input=True,
    frames_per_buffer=CHUNK
)

# Read audio
data = stream.read(CHUNK, exception_on_overflow=False)

# Cleanup
stream.stop_stream()
stream.close()
p.terminate()
```

### Output Stream (Speaker)

```python
import pyaudio

p = pyaudio.PyAudio()

# Chatterbox output format
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000  # 24kHz from Chatterbox

stream = p.open(
    format=FORMAT,
    channels=CHANNELS,
    rate=RATE,
    output=True
)

# Play audio
stream.write(audio_bytes)

# Cleanup
stream.stop_stream()
stream.close()
p.terminate()
```

## MPS (Metal Performance Shaders)

### Check MPS Availability

```python
import torch

if torch.backends.mps.is_available():
    device = "mps"
    print("MPS available - using GPU acceleration")
else:
    device = "cpu"
    print("MPS not available - using CPU")
```

### Common MPS Errors

#### Placeholder Storage Error

```python
try:
    model = SomeModel.to("mps")
    output = model(input)
except RuntimeError as e:
    if "placeholder" in str(e).lower():
        # MPS failed, fall back to CPU
        model = model.to("cpu")
        output = model(input.cpu())
```

#### Memory Pressure

```python
# Clear MPS cache
torch.mps.empty_cache()

# Monitor memory
import subprocess
result = subprocess.run(['sysctl', 'vm.page_pageable_internal_count'], 
                       capture_output=True, text=True)
```

### Graceful MPS Fallback Pattern

```python
def get_device_with_fallback():
    """Get the best available device with MPS error handling."""
    import torch
    
    if not torch.backends.mps.is_available():
        return "cpu"
    
    try:
        # Test MPS with a simple operation
        device = torch.device("mps")
        x = torch.randn(3, 3, device=device)
        y = x @ x.T
        return "mps"
    except RuntimeError as e:
        print(f"MPS test failed: {e}")
        return "cpu"
```

## Audio Format Conversions

### Bytes ↔ NumPy

```python
import numpy as np

# bytes to numpy (int16)
audio_np = np.frombuffer(audio_bytes, dtype=np.int16)

# numpy to bytes
audio_bytes = audio_np.astype(np.int16).tobytes()
```

### Sample Rate Conversion

```python
import scipy.signal

def resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample audio to target sample rate."""
    number_of_samples = round(len(audio) * float(target_sr) / orig_sr)
    return scipy.signal.resample(audio, number_of_samples)
```

### Torch Tensor ↔ NumPy/Bytes

```python
import torch
import numpy as np

# Tensor to numpy
audio_np = tensor.squeeze().cpu().numpy()

# Tensor to int16 bytes
audio_int16 = (tensor.squeeze().cpu().numpy() * 32767).astype(np.int16)
audio_bytes = audio_int16.tobytes()

# Bytes to tensor
audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
audio_float = audio_np.astype(np.float32) / 32767.0
tensor = torch.from_numpy(audio_float)
```

## Volume Detection (Simple VAD)

```python
import audioop

def calculate_rms(audio_bytes: bytes, sample_width: int = 2) -> float:
    """Calculate RMS volume level."""
    return audioop.rms(audio_bytes, sample_width)

# Usage in audio loop
VOLUME_THRESHOLD = 500  # Adjust based on your mic

while True:
    data = stream.read(CHUNK)
    rms = calculate_rms(data)
    
    if rms > VOLUME_THRESHOLD:
        print("Speaking...")
    else:
        print("Silent...")
```

## Common Issues

### 1. Microphone Permission

macOS requires microphone permission. First run will prompt. If denied:

```bash
# Check permissions
# System Preferences > Privacy & Security > Microphone
```

### 2. Device Selection

```python
# Find default input device
default_input = p.get_default_input_device_info()
print(f"Default input: {default_input['name']}")

# Or specify device by index
stream = p.open(..., input_device_index=2)
```

### 3. Buffer Overflow

```python
# Use exception_on_overflow=False to prevent crashes
data = stream.read(CHUNK, exception_on_overflow=False)
```

### 4. Sample Rate Mismatch

- Whisper expects 16kHz input
- Chatterbox outputs 24kHz
- PyAudio can handle different rates for input/output streams

## Full Audio Pipeline Example

```python
import asyncio
import pyaudio
import audioop
import numpy as np

class AudioPipeline:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.input_rate = 16000
        self.output_rate = 24000
        
    async def run(self):
        # Input stream (mic)
        input_stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.input_rate,
            input=True,
            frames_per_buffer=1024
        )
        
        # Output stream (speaker)
        output_stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.output_rate,
            output=True
        )
        
        frames = []
        silence_count = 0
        SILENCE_THRESHOLD = 30
        VOLUME_THRESHOLD = 500
        
        try:
            while True:
                data = input_stream.read(1024, exception_on_overflow=False)
                rms = audioop.rms(data, 2)
                
                if rms > VOLUME_THRESHOLD:
                    frames.append(data)
                    silence_count = 0
                elif frames:
                    silence_count += 1
                    if silence_count >= SILENCE_THRESHOLD:
                        # Process utterance
                        audio = b"".join(frames)
                        # ... STT -> LLM -> TTS ...
                        frames = []
                        silence_count = 0
                
                await asyncio.sleep(0.01)
        
        finally:
            input_stream.stop_stream()
            input_stream.close()
            output_stream.stop_stream()
            output_stream.close()
            self.p.terminate()
```
