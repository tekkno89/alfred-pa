# Desktop Voice Agent POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working proof-of-concept voice AI agent with real-time conversational voice interaction on Apple Silicon Mac (M4/M5), using local STT/TTS and a remote LLM server, with context-aware filler responses to mitigate latency.

**Architecture:** Pipecat-orchestrated pipeline with Whisper MLX (STT), Chatterbox-Turbo (TTS with voice cloning), and OpenAI-compatible remote LLM. UV-managed isolated Python environment. Simple backend URL connection (matches frontend pattern).

**Tech Stack:** Pipecat, faster-whisper-mlx, chatterbox-tts, PyTorch (MPS), OpenAI client, UV package manager, YAML config, Apple Silicon (M4/M5, macOS 14+)

**Phased Approach:**
- **Phase 0:** Research & familiarization with Pipecat, Whisper MLX, and Chatterbox documentation
- **Phase 1:** STT only (speak → transcript)
- **Phase 2:** TTS only (text → speech in cloned voice)
- **Phase 3:** Voice echo loop (STT + TTS integration test - speak → hear it repeated)
- **Phase 4:** LLM connection (full conversation with Alfred backend)
- **Phase 5:** Filler system (context-aware fillers during LLM latency)
- **Phase 6:** Polish (echo cancellation, interruption handling, README)

---

## File Structure

```
desktop/
├── setup.sh                    # Automated setup with UV
├── pyproject.toml              # UV project config (replaces requirements.txt)
├── docs/                       # Research & implementation notes
│   ├── research-pipecat.md
│   ├── research-whisper-mlx.md
│   ├── research-chatterbox.md
│   ├── research-audio-setup.md
│   └── implementation-notes.md
├── config/
│   ├── settings.yaml          # All configuration (TTS, STT, LLM, backend URL)
│   ├── fillers.json           # Default filler phrases
│   └── custom_fillers.json    # User customizations (optional)
├── cache/
│   └── fillers/               # Pre-generated filler audio (PCM)
├── reference_voices/          # User-provided voice samples (WAV, 10-15s)
├── src/
│   ├── __init__.py
│   ├── main.py                # CLI entry point
│   ├── config.py              # Config loader with YAML support
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── voice_agent.py     # Main Pipecat pipeline
│   │   └── phases.py          # Phase 1-6 pipeline builders
│   ├── services/
│   │   ├── __init__.py
│   │   ├── chatterbox_tts.py  # Custom Pipecat TTSService
│   │   ├── whisper_stt.py     # Whisper MLX service wrapper
│   │   └── remote_llm.py      # OpenAI-compatible streaming client
│   ├── processors/
│   │   ├── __init__.py
│   │   ├── filler_processor.py     # Filler classification + injection
│   │   ├── sentence_aggregator.py  # Sentence chunking
│   │   └── echo_cancellation.py    # AEC or mute-during-playback
│   └── utils/
│       ├── __init__.py
│       ├── audio.py           # PCM conversion, audio utilities
│       ├── device.py          # MPS/CPU detection
│       └── backend.py         # Backend connection testing
├── tests/
│   ├── test_stt.py
│   ├── test_tts.py
│   ├── test_fillers.py
│   └── test_pipeline.py
└── README.md
```

---

## Phase 0: Research & Documentation Familiarization

**Goal:** Before writing any code, thoroughly understand the frameworks and libraries we're using. This prevents architectural mistakes and ensures we use APIs correctly.

**Duration:** 2-4 hours (one-time research before implementation)

### Task 0.1: Research Pipecat Framework

**Goal:** Understand Pipecat's frame-based architecture, services, and processors.

**Resources:**
- GitHub: https://github.com/pipecat-ai/pipecat
- Documentation: https://github.com/pipecat-ai/pipecat/tree/main/docs
- Examples: https://github.com/pipecat-ai/pipecat/tree/main/examples

**Key Questions to Answer:**
- [ ] What is the frame-based architecture? (Frame types, frame flow)
- [ ] How do services work? (TTSService, STTService, LLMService base classes)
- [ ] How do processors work? (FrameProcessor for custom logic)
- [ ] What built-in services are available? (Whisper, Silero VAD, etc.)
- [ ] How does interruption handling work? (InterruptionFrame, cancellation)
- [ ] What's the correct way to create a custom TTS service?
- [ ] How does audio I/O work? (DailyTransport, local audio, PyAudio)

**Document findings in:** `desktop/docs/research-pipecat.md`

---

### Task 0.2: Research Whisper MLX

**Goal:** Understand faster-whisper-mlx API for Apple Silicon.

**Resources:**
- GitHub: https://github.com/anthropics/faster-whisper-mlx
- Model options: large-v3-turbo, large-v3-turbo-q4, large-v3

**Key Questions to Answer:**
- [ ] What's the API for loading a model? (device, compute_type options)
- [ ] What's the transcription API? (transcribe method, parameters)
- [ ] What sample rates are supported? (16kHz default?)
- [ ] How do we handle audio input format? (bytes, numpy array, file?)
- [ ] What's the performance difference between model sizes?
- [ ] Does it integrate with Pipecat natively, or do we need a wrapper?

**Document findings in:** `desktop/docs/research-whisper-mlx.md`

---

### Task 0.3: Research Chatterbox TTS

**Goal:** Understand Chatterbox-Turbo API, voice cloning, and Apple Silicon setup.

**Resources:**
- GitHub: https://github.com/resemble-ai/chatterbox
- Apple Silicon fork: https://github.com/devnen/Chatterbox-TTS-Server
- Hugging Face: https://huggingface.co/Jimmi42/chatterbox-tts-apple-silicon-code

**Key Questions to Answer:**
- [ ] What's the API for loading the model? (from_pretrained, device options)
- [ ] How does voice cloning work? (audio_prompt_path parameter)
- [ ] What format does reference audio need? (WAV, sample rate, duration)
- [ ] What are the generation parameters? (exaggeration, cfg_weight)
- [ ] What output format does it produce? (tensor, sample rate)
- [ ] Are there known Apple Silicon issues? (MPS errors, dependency conflicts)
- [ ] What's the correct install order for MPS support?

**Document findings in:** `desktop/docs/research-chatterbox.md`

---

### Task 0.4: Research Apple Silicon Audio Setup

**Goal:** Understand common gotchas with audio on Apple Silicon Macs.

**Resources:**
- PyAudio documentation
- MPS troubleshooting guides
- Common audio device issues on macOS

**Key Questions to Answer:**
- [ ] How to enumerate and select audio devices with PyAudio?
- [ ] What are common MPS errors and how to handle them? (placeholder storage)
- [ ] How to fall back from MPS to CPU gracefully?
- [ ] What audio formats work best for STT? (16kHz int16 mono)
- [ ] What audio formats work best for TTS? (24kHz int16 mono)

**Document findings in:** `desktop/docs/research-audio-setup.md`

---

### Task 0.5: Create Research Summary Document

**Goal:** Consolidate findings into a quick-reference document for implementation.

**Files:**
- Create: `desktop/docs/implementation-notes.md`

**Content should include:**
- API patterns for each library
- Required imports and initialization code
- Common gotchas and workarounds
- Decision log for any architectural choices

**Example structure:**

```markdown
# Implementation Notes

## Pipecat

### Key Imports
```python
from pipecat.services.tts import TTSService
from pipecat.frames.frames import TTSStartedFrame, TTSAudioRawFrame, TTSStoppedFrame
```

### Custom TTS Service Pattern
1. Subclass TTSService
2. Implement `run_tts(self, text: str)` async method
3. Yield frames: TTSStartedFrame → TTSAudioRawFrame → TTSStoppedFrame

### Gotchas
- Interruption handling requires...
- Frame ordering is important because...

## Whisper MLX

### Key Imports
```python
from faster_whisper_mlx import WhisperModel
```

### Model Loading
```python
model = WhisperModel('large-v3-turbo', device='mps', compute_type='float16')
```

### Gotchas
- Audio must be...
- Async wrapper needed because...

## Chatterbox TTS

### Key Imports
```python
from chatterbox.tts import ChatterboxTurboTTS
```

### Model Loading
```python
tts = ChatterboxTurboTTS.from_pretrained(device='mps')
```

### Voice Cloning
```python
wav = tts.generate(text, audio_prompt_path='voice.wav', exaggeration=0.5, cfg_weight=0.5)
```

### Gotchas
- Install order matters: torch first, then chatterbox with --no-deps
- MPS placeholder error fallback: catch RuntimeError and switch to CPU

## Audio (PyAudio)

### Input Stream (Mic)
```python
stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True)
```

### Output Stream (Speaker)
```python
stream = p.open(format=pyaudio.paInt16, channels=1, rate=24000, output=True)
```
```

---

### Task 0.6: Verify Phase 0 Completion

**Before proceeding to Phase 1, ensure:**

- [ ] Can explain Pipecat's frame architecture in simple terms
- [ ] Know the correct base class for custom TTS service
- [ ] Understand how to load and use Whisper MLX
- [ ] Understand how to load and use Chatterbox
- [ ] Know the correct install order for Apple Silicon
- [ ] Have code snippets ready for common operations
- [ ] Documented any open questions or unknowns

**Note to implementer:** This research phase prevents costly rework. If you encounter something unclear during research, ask for clarification before proceeding.

---

## Phase 1: Project Setup & STT Only

**Goal:** Isolated Python environment with Whisper STT working. User speaks into mic, sees transcript printed to console.

**Duration:** 1-2 days

### Task 1.1: Create Project Structure with UV

**Files:**
- Create: `desktop/pyproject.toml`
- Create: `desktop/.python-version`
- Create: `desktop/config/settings.yaml`

**Steps:**

- [ ] **Step 1: Create desktop directory structure**

```bash
mkdir -p desktop/{config,cache/fillers,reference_voices,src/{pipeline,services,processors,utils},tests}
touch desktop/src/{__init__,config,main}.py
touch desktop/src/{pipeline,services,processors,utils}/__init__.py
```

- [ ] **Step 2: Create pyproject.toml for UV**

```toml
[project]
name = "alfred-desktop"
version = "0.1.0"
description = "Voice agent POC for Alfred AI assistant"
requires-python = ">=3.12"
dependencies = [
    "pipecat-ai>=0.0.1",
    "faster-whisper-mlx>=0.1.0",
    "httpx>=0.27.0",
    "openai>=1.0.0",
    "pyaudio>=0.2.14",
    "webrtcvad>=2.0.10",
    "pyyaml>=6.0",
    "pydantic>=2.0.0",
    "numpy>=1.26.0",
    "scipy>=1.12.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]
```

- [ ] **Step 3: Create .python-version for UV**

```
3.12
```

- [ ] **Step 4: Create config/settings.yaml**

```yaml
# Voice Agent Configuration
# All settings in one place - no environment variables needed

stt:
  model: large-v3-turbo  # Options: large-v3-turbo, large-v3-turbo-q4, large-v3
  device: auto           # auto, mps, cpu
  language: en

tts:
  model: chatterbox-turbo
  device: auto           # auto, mps, cpu
  reference_voice: null  # Path to WAV file, or null for default voice
  exaggeration: 0.5      # Voice expressiveness (0.0-1.0)
  cfg_weight: 0.5        # Classifier-free guidance weight (0.0-1.0)
  sample_rate: 24000

llm:
  enabled: false         # Set to true in Phase 4
  model: gpt-4o          # Model identifier

# Backend URL - configure based on your setup:
# - Local: http://localhost:8000
# - LAN: http://192.168.1.100:8000 or http://hostname.local:8000
# - Tailscale/VPN: http://your-tailscale-host:8000
# - Cloudflare Tunnel: https://your-subdomain.trycloudflare.com
backend:
  url: http://localhost:8000

fillers:
  enabled: true
  use_defaults: true
  custom_file: null      # Path to custom_fillers.json
  timeout_ms: 300        # Max time before filler starts

pipeline:
  allow_interruptions: true
  min_words_interruption: 2
  echo_cancellation: auto  # auto, webrtc, mute_during_speech, disabled

# Development/debugging
debug:
  log_level: INFO
  save_audio: false      # Save raw audio for debugging
  audio_output_dir: debug/audio
```

---

### Task 1.2: Write Automated Setup Script

**Files:**
- Create: `desktop/setup.sh`

**Steps:**

- [ ] **Step 1: Create setup.sh with platform verification**

```bash
#!/bin/bash
set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║       Alfred Desktop Voice Agent - Setup                   ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# ============================================
# Platform Verification
# ============================================

# Check macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "❌ ERROR: This application requires macOS."
    echo "   Detected OS: $(uname)"
    exit 1
fi

# Check Apple Silicon
ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    echo "❌ ERROR: Apple Silicon (arm64) required."
    echo "   Detected architecture: $ARCH"
    echo "   This POC is optimized for M4/M5 Macs with MPS GPU support."
    exit 1
fi

# Check macOS version (14+)
MACOS_VERSION=$(sw_vers -productVersion | cut -d. -f1)
if [[ "$MACOS_VERSION" -lt 14 ]]; then
    echo "❌ ERROR: macOS 14 (Sonoma) or later required."
    echo "   Detected version: $(sw_vers -productVersion)"
    exit 1
fi

echo "✓ Platform: macOS $(sw_vers -productVersion) on Apple Silicon ($ARCH)"
echo ""

# ============================================
# UV Installation
# ============================================

if ! command -v uv &> /dev/null; then
    echo "UV package manager not found. Installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

UV_VERSION=$(uv --version)
echo "✓ UV installed: $UV_VERSION"
echo ""

# ============================================
# Project Setup with UV
# ============================================

echo "Creating isolated Python environment with UV..."
uv venv
source .venv/bin/activate

echo "Installing dependencies with UV..."
uv pip install torch torchvision torchaudio
uv pip install -e .

echo "✓ Dependencies installed"
echo ""

# ============================================
# MPS Verification
# ============================================

echo "Verifying Metal Performance Shaders (MPS)..."
MPS_RESULT=$(python -c "import torch; print(torch.backends.mps.is_available())" 2>&1 || echo "False")

if [[ "$MPS_RESULT" == "True" ]]; then
    echo "✓ MPS available - GPU acceleration enabled"
    DEVICE="mps"
else
    echo "⚠ MPS not available - falling back to CPU mode"
    echo "  This will work but be slower."
    DEVICE="cpu"
fi
echo ""

# ============================================
# Pre-download Model Weights
# ============================================

echo "Pre-downloading model weights..."
echo "  This may take 5-15 minutes depending on your connection."
echo ""

# Download Whisper model
echo "  [1/2] Downloading Whisper LARGE_V3_TURBO..."
python -c "
from faster_whisper_mlx import WhisperModel
import sys
try:
    model = WhisperModel('large-v3-turbo', device='$DEVICE', compute_type='float16' if '$DEVICE' == 'mps' else 'int8')
    print('    ✓ Whisper model downloaded')
except Exception as e:
    print(f'    ⚠ Warning: {e}', file=sys.stderr)
" || echo "    ⚠ Whisper download failed - will download on first run"

echo ""
echo "  [2/2] Chatterbox TTS will download on first use (not pre-cached)"
echo ""

# ============================================
# Create Default Config
# ============================================

if [[ ! -f "config/settings.yaml" ]]; then
    echo "Creating default configuration..."
    # Config was created in Task 1.1
fi

# ============================================
# Smoke Test
# ============================================

echo "Running smoke test..."

python -c "
import sys
import torch
print(f'  Python: {sys.version.split()[0]}')
print(f'  PyTorch: {torch.__version__}')
print(f'  Device: $DEVICE')
try:
    from faster_whisper_mlx import WhisperModel
    print('  ✓ Whisper MLX imported')
except ImportError as e:
    print(f'  ⚠ Whisper MLX import failed: {e}')
print('')
print('  ✅ Smoke test passed!')
"

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete!                         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. (Phase 1) Test STT:"
echo "     source .venv/bin/activate"
echo "     python src/main.py --phase 1"
echo ""
echo "  2. (Phase 2) Add TTS with voice cloning:"
echo "     Add a reference WAV to reference_voices/"
echo "     Update config/settings.yaml: tts.reference_voice"
echo "     python src/main.py --phase 2"
echo ""
echo "  3. (Phase 4) Connect to Alfred backend:"
echo "     Update config/settings.yaml: backend.url"
echo "     python src/main.py --phase 4"
echo ""
```

- [ ] **Step 2: Make setup.sh executable**

```bash
chmod +x desktop/setup.sh
```

---

### Task 1.3: Create Config Loader

**Files:**
- Create: `desktop/src/config.py`

**Steps:**

- [ ] **Step 1: Write config loader with Pydantic models**

```python
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
```

---

### Task 1.4: Create Device Detection Utility

**Files:**
- Create: `desktop/src/utils/device.py`

**Steps:**

- [ ] **Step 1: Write device detection utility**

```python
"""Device detection utilities for Apple Silicon."""
import torch


def get_available_device() -> str:
    """Get the best available device (mps > cpu)."""
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def verify_mps() -> tuple[bool, str]:
    """
    Verify MPS is available and working.
    
    Returns:
        Tuple of (is_available, message)
    """
    if not torch.backends.mps.is_available():
        return False, "MPS not available - using CPU mode"
    
    try:
        # Test MPS with a simple operation
        device = torch.device("mps")
        x = torch.randn(3, 3, device=device)
        y = x @ x.T
        return True, "MPS available and working"
    except RuntimeError as e:
        error_msg = str(e)
        if "placeholder" in error_msg.lower():
            return False, f"MPS placeholder error - falling back to CPU: {error_msg}"
        return False, f"MPS error: {error_msg}"
```

---

### Task 1.5: Create Whisper STT Service Wrapper

**Files:**
- Create: `desktop/src/services/whisper_stt.py`

**Steps:**

- [ ] **Step 1: Write Whisper MLX service wrapper for Pipecat**

```python
"""Whisper MLX speech-to-text service wrapper for Pipecat."""
from typing import AsyncIterator
import asyncio
from faster_whisper_mlx import WhisperModel
from pipecat.frames.frames import Frame, TranscriptionFrame

from src.config import Settings, get_device


class WhisperSTTService:
    """Wrapper for faster-whisper-mlx with Pipecat integration."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.device = get_device(settings.stt.device)
        self.model = None
        
    def _ensure_model_loaded(self):
        """Lazy-load model on first use."""
        if self.model is None:
            print(f"Loading Whisper model '{self.settings.stt.model}' on {self.device}...")
            compute_type = "float16" if self.device == "mps" else "int8"
            self.model = WhisperModel(
                self.settings.stt.model,
                device=self.device,
                compute_type=compute_type
            )
            print("✓ Whisper model loaded")
    
    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """
        Transcribe audio data to text.
        
        Args:
            audio_data: Raw audio bytes (int16 PCM, mono)
            sample_rate: Audio sample rate (default 16000)
        
        Returns:
            Transcribed text
        """
        self._ensure_model_loaded()
        
        # Run transcription in thread pool (Whisper is sync)
        loop = asyncio.get_event_loop()
        segments, info = await loop.run_in_executor(
            None,
            lambda: self.model.transcribe(
                audio_data,
                language=self.settings.stt.language,
                beam_size=5
            )
        )
        
        # Combine all segments
        text = " ".join(segment.text for segment in segments)
        return text.strip()


async def create_stt_service(settings: Settings) -> WhisperSTTService:
    """Create and initialize STT service."""
    service = WhisperSTTService(settings)
    return service
```

---

### Task 1.6: Create Phase 1 Pipeline (STT Only)

**Files:**
- Create: `desktop/src/pipeline/phases.py`

**Steps:**

- [ ] **Step 1: Write phase 1 pipeline (mic → STT → print)**

```python
"""Pipeline builders for each development phase."""
import asyncio
import signal
import pyaudio
from src.config import Settings
from src.services.whisper_stt import WhisperSTTService


async def run_phase_1(settings: Settings):
    """
    Phase 1: STT only.
    
    Listen to microphone, transcribe with Whisper, print transcript.
    No TTS, no LLM.
    """
    print("=== Phase 1: Speech-to-Text Test ===")
    print("Speak into your microphone. Press Ctrl+C to exit.\n")
    
    # Initialize STT
    stt_service = WhisperSTTService(settings)
    
    # Audio configuration
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    
    # Initialize PyAudio
    p = pyaudio.PyAudio()
    
    # Open microphone stream
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )
    
    print("🎤 Listening... (speak now)")
    
    # Audio buffer
    frames = []
    silence_count = 0
    SILENCE_THRESHOLD = 30  # Number of silent chunks before processing
    VOLUME_THRESHOLD = 500  # RMS threshold for silence detection
    
    try:
        while True:
            # Read audio chunk
            data = stream.read(CHUNK, exception_on_overflow=False)
            
            # Calculate volume (simple RMS)
            import audioop
            rms = audioop.rms(data, 2)
            
            if rms > VOLUME_THRESHOLD:
                # User is speaking
                frames.append(data)
                silence_count = 0
            elif len(frames) > 0:
                # User stopped speaking
                silence_count += 1
                
                if silence_count >= SILENCE_THRESHOLD:
                    # Process the utterance
                    audio_data = b"".join(frames)
                    
                    print("\n🔊 Processing speech...")
                    text = await stt_service.transcribe(audio_data, RATE)
                    
                    if text:
                        print(f"📝 Transcript: \"{text}\"")
                    else:
                        print("⚠ No speech detected")
                    
                    print("\n🎤 Listening...")
                    frames = []
                    silence_count = 0
            
            # Small sleep to prevent CPU spinning
            await asyncio.sleep(0.01)
    
    except KeyboardInterrupt:
        print("\n\nStopping...")
    
    finally:
        # Cleanup
        stream.stop_stream()
        stream.close()
        p.terminate()
        print("✓ Audio stream closed")
```

---

### Task 1.7: Create CLI Entry Point

**Files:**
- Create: `desktop/src/main.py`

**Steps:**

- [ ] **Step 1: Write CLI entry point with phase selection**

```python
#!/usr/bin/env python3
"""Alfred Desktop Voice Agent - CLI Entry Point"""
import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Settings
from src.pipeline.phases import run_phase_1


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Alfred Desktop Voice Agent POC"
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[0, 1, 2, 3, 4, 5, 6],
        default=0,
        help="Development phase to run (default: 0 for research/notes)"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/settings.yaml",
        help="Path to config file (default: config/settings.yaml)"
    )
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()
    
    # Load configuration
    print(f"Loading config from {args.config}...")
    settings = Settings.load(args.config)
    
    # Run the appropriate phase
    if args.phase == 0:
        print("Phase 0: Research & Documentation")
        print("Review docs/ directory for implementation notes before coding.")
        print("See Phase 0 tasks in the plan for research checklist.")
    elif args.phase == 1:
        from src.pipeline.phases import run_phase_1
        await run_phase_1(settings)
    elif args.phase == 2:
        from src.pipeline.phases import run_phase_2
        await run_phase_2(settings)
    elif args.phase == 3:
        from src.pipeline.phases import run_phase_3
        await run_phase_3(settings)
    elif args.phase == 4:
        from src.pipeline.phases import run_phase_4
        await run_phase_4(settings)
    elif args.phase == 5:
        from src.pipeline.phases import run_phase_5
        await run_phase_5(settings)
    elif args.phase == 6:
        from src.pipeline.phases import run_phase_6
        await run_phase_6(settings)
    else:
        print(f"Phase {args.phase} not implemented yet")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
```

---

### Task 1.8: Test Phase 1 End-to-End

**Steps:**

- [ ] **Step 1: Run setup.sh**

```bash
cd desktop
./setup.sh
```

Expected output:
```
✓ Platform: macOS 14.x on Apple Silicon (arm64)
✓ UV installed: uv 0.x.x
✓ Dependencies installed
✓ MPS available - GPU acceleration enabled
✓ Whisper model downloaded
✅ Smoke test passed!
```

- [ ] **Step 2: Run Phase 1**

```bash
source .venv/bin/activate
python src/main.py --phase 1
```

Expected output:
```
=== Phase 1: Speech-to-Text Test ===
Speak into your microphone. Press Ctrl+C to exit.

🎤 Listening... (speak now)
```

- [ ] **Step 3: Speak test phrase**

Say: "Hello, this is a test of the voice agent."

Expected output:
```
🔊 Processing speech...
📝 Transcript: "Hello, this is a test of the voice agent."
```

- [ ] **Step 4: Commit Phase 1**

```bash
git add desktop/
git commit -m "feat(desktop): add phase 1 STT pipeline with Whisper MLX

- UV-managed isolated Python environment
- Settings in YAML config (no .env)
- Whisper STT with MPS support
- Phase 1 pipeline: mic → STT → transcript output
- Setup script with platform verification and model pre-download"
```

---

## Phase 2: TTS Integration

**Goal:** Chatterbox TTS working with voice cloning. User provides text input, hears speech in cloned voice.

**Duration:** 1-2 days

### Task 2.1: Install Chatterbox with Correct Dependency Order

**Files:**
- Modify: `desktop/setup.sh`

**Steps:**

- [ ] **Step 1: Update setup.sh with Chatterbox installation**

Add after PyTorch installation:

```bash
# ============================================
# Chatterbox TTS Installation (Apple Silicon)
# ============================================

echo "Installing Chatterbox-TTS for Apple Silicon..."
echo "  This requires special install order to prevent torch downgrade."
echo ""

# Install Chatterbox dependencies manually
uv pip install numpy scipy librosa soundfile

# Install Chatterbox with --no-deps
uv pip install chatterbox-tts --no-deps

echo "✓ Chatterbox-TTS installed"
echo ""

# Verify Chatterbox
python -c "
try:
    from chatterbox.tts import ChatterboxTurboTTS
    print('  ✓ Chatterbox imported successfully')
except ImportError as e:
    print(f'  ⚠ Chatterbox import failed: {e}')
"
```

---

### Task 2.2: Create Chatterbox TTS Service

**Files:**
- Create: `desktop/src/services/chatterbox_tts.py`

**Steps:**

- [ ] **Step 1: Write custom Pipecat TTSService subclass**

```python
"""Chatterbox TTS service with voice cloning support."""
from pathlib import Path
from typing import Optional
import torch
import numpy as np
from pipecat.services.tts import TTSService
from pipecat.frames.frames import (
    TTSStartedFrame,
    TTSAudioRawFrame,
    TTSStoppedFrame,
)
from chatterbox.tts import ChatterboxTurboTTS

from src.config import Settings, get_device


class ChatterboxTTSService:
    """Chatterbox-Turbo TTS service with voice cloning."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.device = get_device(settings.tts.device)
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
                self._model = ChatterboxTurboTTS.from_pretrained(device=self.device)
                print("✓ Chatterbox model loaded")
            except Exception as e:
                print(f"⚠ Chatterbox load error: {e}")
                if "placeholder" in str(e).lower() and self.device == "mps":
                    print("  MPS placeholder error detected, falling back to CPU...")
                    self.device = "cpu"
                    self._model = ChatterboxTurboTTS.from_pretrained(device=self.device)
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
            audio = (wav.cpu().numpy() * 32767).astype(np.int16)
        else:
            audio = (np.array(wav) * 32767).astype(np.int16)
        
        # Ensure mono
        if len(audio.shape) > 1:
            audio = audio[:, 0]
        
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
```

---

### Task 2.3: Create Phase 2 Pipeline (TTS Test)

**Files:**
- Modify: `desktop/src/pipeline/phases.py`

**Steps:**

- [ ] **Step 1: Add Phase 2 function**

```python
async def run_phase_2(settings: Settings):
    """
    Phase 2: TTS only.
    
    Text input from user, synthesize with Chatterbox, play audio.
    Tests voice cloning.
    """
    print("=== Phase 2: Text-to-Speech Test ===")
    print("Type text and press Enter to hear it synthesized.")
    print("Press Ctrl+C to exit.\n")
    
    from src.services.chatterbox_tts import ChatterboxTTSService
    import pyaudio
    
    # Initialize TTS
    tts_service = ChatterboxTTSService(settings)
    
    # Audio output
    p = pyaudio.PyAudio()
    
    try:
        while True:
            # Get text input
            text = input("Text > ").strip()
            
            if not text:
                continue
            
            if text.lower() in ["exit", "quit"]:
                break
            
            # Generate audio
            print("🔊 Synthesizing...")
            audio_data = tts_service.generate_audio(text)
            
            # Play audio
            print("🔊 Playing...")
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=settings.tts.sample_rate,
                output=True
            )
            stream.write(audio_data)
            stream.stop_stream()
            stream.close()
            
            print("✓ Done\n")
    
    except KeyboardInterrupt:
        print("\n\nStopping...")
    
    finally:
        p.terminate()
        print("✓ Audio output closed")
```

---

### Task 2.4: Add Sample Reference Voice

**Files:**
- Create: `desktop/reference_voices/.gitkeep`

**Steps:**

- [ ] **Step 1: Create placeholder for reference voices**

```bash
mkdir -p desktop/reference_voices
touch desktop/reference_voices/.gitkeep
```

- [ ] **Step 2: Add README for reference voices**

Create `desktop/reference_voices/README.md`:

```markdown
# Reference Voices

Place voice reference WAV files here for voice cloning.

## Requirements

- Format: WAV (uncompressed)
- Duration: 10-15 seconds
- Sample rate: 24kHz or higher
- Channels: Mono (single speaker)
- Quality: Clear, conversational style, minimal background noise

## Usage

1. Add your WAV file to this directory
2. Update `config/settings.yaml`:
   ```yaml
   tts:
     reference_voice: reference_voices/your_voice.wav
   ```
3. Run Phase 2 to test: `python src/main.py --phase 2`

## Tips

- Record yourself speaking naturally (not reading)
- Use a good microphone in a quiet room
- 10-15 seconds of continuous speech works best
- Avoid long pauses or dramatic inflections
```

---

### Task 2.5: Test Phase 2 End-to-End

**Steps:**

- [ ] **Step 1: Update settings.yaml with reference voice**

Edit `config/settings.yaml`:
```yaml
tts:
  reference_voice: reference_voices/my_voice.wav  # Update this path
```

- [ ] **Step 2: Run Phase 2**

```bash
python src/main.py --phase 2
```

Expected output:
```
=== Phase 2: Text-to-Speech Test ===
Type text and press Enter to hear it synthesized.
Press Ctrl+C to exit.

✓ Reference voice loaded: my_voice.wav
Text > Hello, this is a test.
🔊 Synthesizing...
Loading Chatterbox model on mps...
✓ Chatterbox model loaded
🔊 Playing...
✓ Done
```

- [ ] **Step 3: Commit Phase 2**

```bash
git add desktop/
git commit -m "feat(desktop): add phase 2 TTS with Chatterbox voice cloning

- Chatterbox TTS service with MPS support
- Voice cloning with reference WAV
- Phase 2 pipeline: text input → TTS → audio output
- Reference voice directory with guidelines"
```

---

## Phase 3: Basic Voice Loop

**Goal:** STT → TTS echo loop. User speaks, hears it repeated back in cloned voice.

**Purpose:** This is an integration test phase that validates STT and TTS work together before adding LLM complexity. If Phase 1 (STT) and Phase 2 (TTS) both work, but Phase 3 fails, we know the issue is in how they integrate (audio format conversion, timing, buffering). This phased approach isolates problems early.

**Duration:** 1 day

### Task 3.1: Create Phase 3 Pipeline

**Files:**
- Modify: `desktop/src/pipeline/phases.py`

**Steps:**

- [ ] **Step 1: Add Phase 3 function**

```python
async def run_phase_3(settings: Settings):
    """
    Phase 3: STT → TTS echo loop.
    
    User speaks, hears it repeated in cloned voice.
    Tests end-to-end audio flow.
    """
    print("=== Phase 3: Voice Echo Loop ===")
    print("Speak into your microphone. You'll hear it repeated back.")
    print("Press Ctrl+C to exit.\n")
    
    from src.services.whisper_stt import WhisperSTTService
    from src.services.chatterbox_tts import ChatterboxTTSService
    import pyaudio
    import audioop
    
    # Initialize services
    stt_service = WhisperSTTService(settings)
    tts_service = ChatterboxTTSService(settings)
    
    # Audio configuration
    INPUT_RATE = 16000
    OUTPUT_RATE = settings.tts.sample_rate
    CHUNK = 1024
    
    p = pyaudio.PyAudio()
    
    # Input stream (mic)
    input_stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=INPUT_RATE,
        input=True,
        frames_per_buffer=CHUNK
    )
    
    # Output stream (speaker)
    output_stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=OUTPUT_RATE,
        output=True
    )
    
    print("🎤 Listening...")
    
    frames = []
    silence_count = 0
    SILENCE_THRESHOLD = 30
    VOLUME_THRESHOLD = 500
    
    try:
        while True:
            data = input_stream.read(CHUNK, exception_on_overflow=False)
            rms = audioop.rms(data, 2)
            
            if rms > VOLUME_THRESHOLD:
                frames.append(data)
                silence_count = 0
            elif len(frames) > 0:
                silence_count += 1
                
                if silence_count >= SILENCE_THRESHOLD:
                    # Process utterance
                    audio_data = b"".join(frames)
                    
                    print("\n🔊 Transcribing...")
                    text = await stt_service.transcribe(audio_data, INPUT_RATE)
                    
                    if text:
                        print(f"📝 You said: \"{text}\"")
                        
                        # Synthesize and play
                        print("🔊 Synthesizing response...")
                        response_audio = tts_service.generate_audio(text)
                        
                        print("🔊 Playing response...")
                        output_stream.write(response_audio)
                        
                        print("✓ Done")
                    else:
                        print("⚠ No speech detected")
                    
                    print("\n🎤 Listening...")
                    frames = []
                    silence_count = 0
            
            await asyncio.sleep(0.01)
    
    except KeyboardInterrupt:
        print("\n\nStopping...")
    
    finally:
        input_stream.stop_stream()
        input_stream.close()
        output_stream.stop_stream()
        output_stream.close()
        p.terminate()
        print("✓ Audio streams closed")
```

---

### Task 3.2: Test Phase 3 End-to-End

**Steps:**

- [ ] **Step 1: Run Phase 3**

```bash
python src/main.py --phase 3
```

Expected output:
```
=== Phase 3: Voice Echo Loop ===
Speak into your microphone. You'll hear it repeated back.
Press Ctrl+C to exit.

🎤 Listening...
🔊 Transcribing...
📝 You said: "Hello, this is a test of the voice agent."
🔊 Synthesizing response...
🔊 Playing response...
✓ Done

🎤 Listening...
```

- [ ] **Step 2: Commit Phase 3**

```bash
git add desktop/
git commit -m "feat(desktop): add phase 3 voice echo loop

- STT → TTS end-to-end pipeline
- User speaks, hears it repeated in cloned voice
- Tests full audio flow before LLM integration"
```

---

## Phase 4: LLM Connection

**Goal:** Connect to Alfred backend for LLM responses. Support multiple connection modes (local/Tailscale/FRP/Cloudflare).

**Duration:** 2 days

### Task 4.1: Create Remote LLM Client

**Files:**
- Create: `desktop/src/services/remote_llm.py`

**Steps:**

- [ ] **Step 1: Write OpenAI-compatible LLM client**

```python
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
        self.api_key = settings.llm.api_key
        self.model = settings.llm.model
        
        # Initialize OpenAI client with custom base URL
        self.client = AsyncOpenAI(
            api_key=self.api_key or "dummy-key",  # Some servers don't require real key
            base_url=f"{self.base_url}/v1"  # Assumes OpenAI-compatible endpoint
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
```

---

### Task 4.2: Create Backend Connection Helper

**Files:**
- Create: `desktop/src/utils/backend.py`

**Steps:**

- [ ] **Step 1: Write backend connection utilities**

```python
"""Backend connection utilities."""
import httpx

from src.config import Settings


async def test_backend_connection(settings: Settings) -> tuple[bool, str]:
    """
    Test connection to the Alfred backend.
    
    Returns:
        Tuple of (success, message)
    """
    url = settings.get_backend_url()
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            if response.status_code == 200:
                return True, f"Connected to {url}"
            else:
                return False, f"Backend returned status {response.status_code}"
    except httpx.ConnectError:
        return False, f"Cannot connect to {url}"
    except Exception as e:
        return False, f"Connection error: {e}"


def print_connection_help():
    """Print help for backend connection configuration."""
    print("\nBackend Connection Configuration:")
    print("=" * 50)
    print("\nConfigure the backend URL in config/settings.yaml:")
    print()
    print("  backend:")
    print("    url: http://localhost:8000")
    print()
    print("Connection options:")
    print()
    print("  Local:")
    print("    url: http://localhost:8000")
    print()
    print("  LAN (local network):")
    print("    url: http://192.168.1.100:8000")
    print("    url: http://hostname.local:8000")
    print()
    print("  Tailscale/VPN:")
    print("    url: http://your-tailscale-hostname:8000")
    print("    url: http://100.x.y.z:8000  # Tailscale IP")
    print()
    print("  Cloudflare Tunnel (for remote access without VPN):")
    print("    url: https://your-subdomain.trycloudflare.com")
    print()
    print("On your Alfred backend server, run:")
    print("  cloudflared tunnel --url http://localhost:8000")
    print()
    print("=" * 50)
```
```

---

### Task 4.3: Create Phase 4 Pipeline

**Files:**
- Modify: `desktop/src/pipeline/phases.py`

**Steps:**

- [ ] **Step 1: Add Phase 4 function**

```python
async def run_phase_4(settings: Settings):
    """
    Phase 4: Full conversation with LLM.
    
    User speaks → STT → LLM → TTS → user hears response.
    """
    print("=== Phase 4: Voice Conversation with LLM ===")
    
    from src.services.whisper_stt import WhisperSTTService
    from src.services.chatterbox_tts import ChatterboxTTSService
    from src.services.remote_llm import create_llm_service
    from src.utils.backend import test_backend_connection, print_connection_help
    import pyaudio
    import audioop
    
    # Check LLM is enabled
    if not settings.llm.enabled:
        print("❌ LLM not enabled in config/settings.yaml")
        print("   Set llm.enabled: true and configure backend.url")
        print_connection_help()
        return
    
    # Test backend connection
    print("Testing backend connection...")
    success, msg = await test_backend_connection(settings)
    if not success:
        print(f"❌ {msg}")
        print_connection_help()
        return
    print(f"✓ {msg}\n")
    
    # Initialize services
    stt_service = WhisperSTTService(settings)
    tts_service = ChatterboxTTSService(settings)
    llm_service = await create_llm_service(settings)
    
    if not llm_service:
        print("❌ Failed to initialize LLM service")
        return
    
    # Conversation history
    messages = [
        {"role": "system", "content": "You are Alfred, a helpful AI assistant. Respond naturally and conversationally."}
    ]
    
    # Audio configuration
    INPUT_RATE = 16000
    OUTPUT_RATE = settings.tts.sample_rate
    CHUNK = 1024
    
    p = pyaudio.PyAudio()
    
    input_stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=INPUT_RATE,
        input=True,
        frames_per_buffer=CHUNK
    )
    
    output_stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=OUTPUT_RATE,
        output=True
    )
    
    print("🎤 Listening... (speak naturally)")
    print("Press Ctrl+C to exit.\n")
    
    frames = []
    silence_count = 0
    SILENCE_THRESHOLD = 30
    VOLUME_THRESHOLD = 500
    
    try:
        while True:
            data = input_stream.read(CHUNK, exception_on_overflow=False)
            rms = audioop.rms(data, 2)
            
            if rms > VOLUME_THRESHOLD:
                frames.append(data)
                silence_count = 0
            elif len(frames) > 0:
                silence_count += 1
                
                if silence_count >= SILENCE_THRESHOLD:
                    # Process utterance
                    audio_data = b"".join(frames)
                    
                    print("🔊 Transcribing...")
                    text = await stt_service.transcribe(audio_data, INPUT_RATE)
                    
                    if text:
                        print(f"📝 You: \"{text}\"")
                        
                        # Add to history
                        messages.append({"role": "user", "content": text})
                        
                        # Get LLM response
                        print("🤖 Thinking...")
                        response_text = await llm_service.generate(messages)
                        
                        print(f"🤖 Alfred: \"{response_text}\"")
                        
                        # Add to history
                        messages.append({"role": "assistant", "content": response_text})
                        
                        # Synthesize and play
                        response_audio = tts_service.generate_audio(response_text)
                        output_stream.write(response_audio)
                        
                        print("\n🎤 Listening...")
                    else:
                        print("⚠ No speech detected\n🎤 Listening...")
                    
                    frames = []
                    silence_count = 0
            
            await asyncio.sleep(0.01)
    
    except KeyboardInterrupt:
        print("\n\nStopping...")
    
    finally:
        input_stream.stop_stream()
        input_stream.close()
        output_stream.stop_stream()
        output_stream.close()
        p.terminate()
        print("✓ Audio streams closed")
```

---

### Task 4.4: Test Phase 4 End-to-End

**Steps:**

- [ ] **Step 1: Configure backend connection in settings.yaml**

```yaml
llm:
  enabled: true
  model: gpt-4o

backend:
  url: http://localhost:8000  # Or your Tailscale/VPN/LAN URL
```

- [ ] **Step 2: Run Phase 4**

```bash
python src/main.py --phase 4
```

Expected output:
```
=== Phase 4: Voice Conversation with LLM ===
Testing backend connection...
✓ Connected to http://localhost:8000

🎤 Listening... (speak naturally)
Press Ctrl+C to exit.

🔊 Transcribing...
📝 You: "Hello Alfred, how are you today?"
🤖 Thinking...
🤖 Alfred: "Hello! I'm doing well, thank you for asking. How can I help you today?"

🎤 Listening...
```

- [ ] **Step 3: Commit Phase 4**

```bash
git add desktop/
git commit -m "feat(desktop): add phase 4 LLM connection

- Remote LLM client with OpenAI-compatible API
- Simple backend URL configuration (matches frontend pattern)
- Backend connection testing and help utilities
- Full conversation pipeline: STT → LLM → TTS"
```

---

## Phase 5: Filler Response System

**Goal:** Context-aware filler responses to mitigate LLM latency. Fillers play while waiting for LLM, then complete naturally before real response.

**Duration:** 2 days

### Task 5.1: Create Filler Configuration

**Files:**
- Create: `desktop/config/fillers.json`

**Steps:**

- [ ] **Step 1: Create default fillers JSON**

```json
{
  "version": 1,
  "description": "Context-aware filler responses to play while waiting for LLM",
  "fillers": {
    "thinking": [
      "Hmm, let me think about that...",
      "Good question, give me a moment...",
      "Let me work through that..."
    ],
    "looking_up": [
      "Let me check on that for you...",
      "One sec, pulling that up...",
      "Looking into it now..."
    ],
    "acknowledgment": [
      "Got it, just a moment...",
      "Sure thing, working on it...",
      "Right, let me see..."
    ],
    "clarification": [
      "That's an interesting one, let me think...",
      "Okay, working through it...",
      "Let me make sure I get this right..."
    ],
    "casual": [
      "Mm, one second...",
      "Yeah, hold on...",
      "Alright, give me a sec..."
    ],
    "neutral": [
      "One moment...",
      "Let me think...",
      "Just a second..."
    ]
  },
  "classification_rules": {
    "thinking": {
      "keywords": ["explain", "how does", "why", "complex", "difference between", "compare"],
      "description": "Complex questions requiring reasoning"
    },
    "looking_up": {
      "keywords": ["what is", "who is", "where", "when", "search", "find", "look up", "tell me about"],
      "description": "Factual queries and lookups"
    },
    "acknowledgment": {
      "keywords": ["schedule", "remind", "set", "create", "send", "write", "make"],
      "description": "Action requests and commands"
    },
    "clarification": {
      "keywords": ["can you", "could you", "would you", "help me"],
      "description": "Requests for assistance"
    },
    "casual": {
      "keywords": ["hey", "hi", "hello", "yo", "morning", "evening"],
      "description": "Greetings and casual phrases"
    }
  }
}
```

---

### Task 5.2: Create Filler Processor

**Files:**
- Create: `desktop/src/processors/filler_processor.py`

**Steps:**

- [ ] **Step 1: Write filler classification and caching logic**

```python
"""Filler response processor for mitigating LLM latency."""
import json
import random
from pathlib import Path
from typing import Optional, Tuple
import hashlib

from src.config import Settings


class FillerProcessor:
    """Manages filler responses: classification, caching, and playback."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.fillers = {}
        self.rules = {}
        self.audio_cache = {}
        
        # Load fillers
        self._load_fillers()
    
    def _load_fillers(self):
        """Load filler phrases from JSON files."""
        if not self.settings.fillers.enabled:
            print("Fillers disabled in config")
            return
        
        # Load default fillers
        if self.settings.fillers.use_defaults:
            default_path = Path("config/fillers.json")
            if default_path.exists():
                with open(default_path) as f:
                    data = json.load(f)
                    self.fillers = data.get("fillers", {})
                    self.rules = data.get("classification_rules", {})
                print(f"✓ Loaded {sum(len(v) for v in self.fillers.values())} default fillers")
        
        # Load custom fillers (overrides defaults for matching categories)
        if self.settings.fillers.custom_file:
            custom_path = Path(self.settings.fillers.custom_file)
            if custom_path.exists():
                with open(custom_path) as f:
                    data = json.load(f)
                    custom_fillers = data.get("fillers", {})
                    self.fillers.update(custom_fillers)
                    print(f"✓ Loaded custom fillers from {custom_path.name}")
    
    def classify_text(self, text: str) -> str:
        """
        Classify user text into a filler category.
        
        Args:
            text: User's transcribed speech
        
        Returns:
            Category name (thinking, looking_up, acknowledgment, etc.)
        """
        text_lower = text.lower()
        
        # Score each category
        scores = {}
        for category, rule in self.rules.items():
            keywords = rule.get("keywords", [])
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[category] = score
        
        # Return highest scoring category, or neutral
        if scores:
            return max(scores, key=scores.get)
        
        return "neutral"
    
    def get_filler(self, category: str) -> Tuple[str, Optional[bytes]]:
        """
        Get a random filler phrase and its cached audio.
        
        Args:
            category: Filler category
        
        Returns:
            Tuple of (phrase, cached_audio_bytes)
        """
        if category not in self.fillers:
            category = "neutral"
        
        phrases = self.fillers[category]
        phrase = random.choice(phrases)
        
        # Check cache
        cache_key = f"{category}_{self.fillers[category].index(phrase)}"
        audio = self.audio_cache.get(cache_key)
        
        return phrase, audio
    
    def load_audio_cache(self, cache_dir: Path):
        """Load pre-generated filler audio from cache directory."""
        if not cache_dir.exists():
            print("⚠ Filler audio cache not found - will generate on demand")
            return
        
        for pcm_file in cache_dir.glob("*.pcm"):
            category_idx = pcm_file.stem  # e.g., "thinking_0"
            with open(pcm_file, "rb") as f:
                self.audio_cache[category_idx] = f.read()
        
        print(f"✓ Loaded {len(self.audio_cache)} cached filler audio files")
    
    def generate_audio_cache(self, tts_service, cache_dir: Path):
        """
        Generate audio cache for all fillers.
        
        Args:
            tts_service: ChatterboxTTSService instance
            cache_dir: Directory to save cached audio
        """
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        total = sum(len(phrases) for phrases in self.fillers.values())
        count = 0
        
        for category, phrases in self.fillers.items():
            for idx, phrase in enumerate(phrases):
                count += 1
                print(f"  [{count}/{total}] Generating: {phrase[:30]}...")
                
                audio = tts_service.generate_audio(phrase)
                
                output_path = cache_dir / f"{category}_{idx}.pcm"
                with open(output_path, "wb") as f:
                    f.write(audio)
        
        print(f"✓ Generated {count} filler audio files")


async def create_filler_processor(settings: Settings) -> FillerProcessor:
    """Create filler processor with audio cache loaded."""
    processor = FillerProcessor(settings)
    processor.load_audio_cache(Path("cache/fillers"))
    return processor
```

---

### Task 5.3: Update Setup Script to Generate Filler Cache

**Files:**
- Modify: `desktop/setup.sh`

**Steps:**

- [ ] **Step 1: Add filler cache generation to setup.sh**

Add after model download:

```bash
# ============================================
# Filler Audio Cache Generation
# ============================================

if [[ -f "config/settings.yaml" ]] && grep -q "fillers:" "config/settings.yaml"; then
    echo ""
    echo "Generating filler audio cache..."
    
    python - << 'PYTHON_SCRIPT'
import sys
import asyncio
from pathlib import Path

async def generate_fillers():
    from src.config import Settings
    from src.services.chatterbox_tts import ChatterboxTTSService
    from src.processors.filler_processor import FillerProcessor
    
    try:
        settings = Settings.load()
        if not settings.fillers.enabled:
            print("  Fillers disabled, skipping cache generation")
            return
        
        tts = ChatterboxTTSService(settings)
        processor = FillerProcessor(settings)
        processor.generate_audio_cache(tts, Path("cache/fillers"))
        
    except Exception as e:
        print(f"  ⚠ Filler generation failed: {e}", file=sys.stderr)

asyncio.run(generate_fillers())
PYTHON_SCRIPT

    echo "✓ Filler audio cache generated"
    echo ""
fi
```

---

### Task 5.4: Integrate Fillers into Phase 4 Pipeline

**Files:**
- Modify: `desktop/src/pipeline/phases.py`

**Steps:**

- [ ] **Step 1: Update run_phase_4 to use fillers**

Replace the LLM response section:

```python
# After getting user text:
if text:
    print(f"📝 You: \"{text}\"")
    
    # Classify and play filler
    if settings.fillers.enabled and llm_service:
        category = filler_processor.classify_text(text)
        filler_phrase, filler_audio = filler_processor.get_filler(category)
        
        if filler_audio:
            print(f"🔊 Filler: \"{filler_phrase}\"")
            output_stream.write(filler_audio)
    
    # Add to history
    messages.append({"role": "user", "content": text})
    
    # Get LLM response
    print("🤖 Thinking...")
    response_text = await llm_service.generate(messages)
    
    print(f"🤖 Alfred: \"{response_text}\"")
    
    # Add to history
    messages.append({"role": "assistant", "content": response_text})
    
    # Synthesize and play response
    response_audio = tts_service.generate_audio(response_text)
    output_stream.write(response_audio)
```

---

### Task 5.5: Test Phase 5 End-to-End

**Steps:**

- [ ] **Step 1: Regenerate filler cache**

```bash
rm -rf cache/fillers
./setup.sh  # Will regenerate fillers
```

- [ ] **Step 2: Run Phase 4 (now with fillers)**

```bash
python src/main.py --phase 4
```

Expected output:
```
=== Phase 4: Voice Conversation with LLM ===
✓ Connected to http://localhost:8000
✓ Loaded 18 default fillers
✓ Loaded 18 cached filler audio files

🎤 Listening...
📝 You: "What is the capital of France?"
🔊 Filler: "Let me check on that for you..."
🤖 Thinking...
🤖 Alfred: "The capital of France is Paris."

🎤 Listening...
```

- [ ] **Step 3: Test filler completion timing**

Verify that:
1. Filler starts within ~300ms of user stopping speech
2. Filler completes naturally (not cut off by response)
3. Response starts immediately after filler ends

- [ ] **Step 4: Commit Phase 5**

```bash
git add desktop/
git commit -m "feat(desktop): add phase 5 filler response system

- Context-aware filler classification (thinking/looking_up/etc.)
- Pre-generated filler audio cache
- Custom filler support via config/custom_fillers.json
- Fillers play while waiting for LLM, complete before response"
```

---

## Phase 6: Polish & Interruption

**Goal:** Robust interruption handling and echo cancellation. Agent doesn't interrupt itself when user tests without headphones.

**Duration:** 1-2 days

### Task 6.1: Implement Echo Cancellation

**Files:**
- Create: `desktop/src/processors/echo_cancellation.py`

**Steps:**

- [ ] **Step 1: Write echo cancellation processor**

```python
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
            self._vad = webrtcvad.Vad(2)  # Aggressiveness 0-3
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
                return None  # Drop audio while bot speaking
            return audio_data
        
        # WebRTC mode would go here (simplified for POC)
        # Full AEC requires reference signal from speaker output
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
```

---

### Task 6.2: Implement Interruption Handling

**Files:**
- Modify: `desktop/src/pipeline/phases.py`

**Steps:**

- [ ] **Step 1: Add interruption detection to Phase 4**

Add before the main loop:

```python
# Echo cancellation
from src.processors.echo_cancellation import create_echo_cancellation

echo_cancel = create_echo_cancellation(settings.pipeline.echo_cancellation)

# Interruption tracking
MIN_WORDS_INTERRUPTION = settings.pipeline.min_words_interruption
interrupt_buffer = []
is_playing_response = False
```

Update the audio processing loop:

```python
# In the main loop, when processing audio:
if rms > VOLUME_THRESHOLD:
    # Check for interruption
    if is_playing_response and len(interrupt_buffer) < MIN_WORDS_INTERRUPTION:
        interrupt_buffer.append(data)
    elif is_playing_response and len(interrupt_buffer) >= MIN_WORDS_INTERRUPTION:
        # User is interrupting
        print("\n⚠ User interruption detected")
        is_playing_response = False
        # Stop TTS playback
        output_stream.stop_stream()
        echo_cancel.on_bot_stopped_speaking()
        frames = []
        interrupt_buffer = []
    
    if not echo_cancel.should_mute_mic():
        frames.append(data)
    silence_count = 0
```

---

### Task 6.3: Create README

**Files:**
- Create: `desktop/README.md`

**Steps:**

- [ ] **Step 1: Write comprehensive README**

```markdown
# Alfred Desktop Voice Agent POC

A proof-of-concept voice AI agent with real-time conversational voice interaction on Apple Silicon Mac (M4/M5).

## Features

- **Local STT/TTS**: Whisper MLX for speech-to-text, Chatterbox-Turbo for text-to-speech
- **Voice Cloning**: Zero-shot voice cloning with a 10-15 second reference audio
- **Remote LLM**: Connect to your Alfred backend via VPN, Tailscale, or Cloudflare Tunnel
- **Context-Aware Fillers**: Mitigates LLM latency with smart filler responses
- **Interruption Support**: Talk over the agent to interrupt
- **Simple Configuration**: Just a backend URL, works like the web frontend

## Requirements

- **Hardware**: Apple Silicon Mac (M4/M5 recommended)
- **OS**: macOS 14 (Sonoma) or later
- **Memory**: 16GB minimum, 32GB+ recommended
- **Python**: 3.12+ (managed automatically by UV)

## Quick Start

### 1. Setup

```bash
cd desktop
./setup.sh
```

This will:
- Verify your platform (macOS 14+ on Apple Silicon)
- Install UV package manager
- Create an isolated Python environment
- Install all dependencies
- Download model weights (Whisper, Chatterbox)
- Generate filler audio cache

**Time**: ~10-20 minutes on first run

### 2. Configure

Edit `config/settings.yaml`:

```yaml
# Voice cloning (optional)
tts:
  reference_voice: reference_voices/my_voice.wav

# Backend connection (Phase 4+)
llm:
  enabled: true

backend:
  url: http://localhost:8000  # See connection options below
```

### 3. Add Reference Voice (Optional)

Place a 10-15 second WAV file in `reference_voices/`:

```bash
# Requirements:
# - Format: WAV (uncompressed)
# - Duration: 10-15 seconds
# - Sample rate: 24kHz+
# - Channels: Mono, single speaker
# - Style: Conversational, natural
```

### 4. Run

```bash
source .venv/bin/activate

# Phase 1: STT only
python src/main.py --phase 1

# Phase 2: TTS only
python src/main.py --phase 2

# Phase 3: Voice echo loop
python src/main.py --phase 3

# Phase 4: Full conversation with LLM
python src/main.py --phase 4
```

## Backend Connection

Configure the backend URL based on your network setup:

### Local

```yaml
backend:
  url: http://localhost:8000
```

Use when Alfred backend runs on the same machine.

### LAN (Local Network)

```yaml
backend:
  url: http://192.168.1.100:8000
  # or
  url: http://hostname.local:8000
```

Use when backend runs on another machine on your local network.

### Tailscale / VPN

```yaml
backend:
  url: http://your-tailscale-hostname:8000
  # or use Tailscale IP
  url: http://100.x.y.z:8000
```

Use when you have Tailscale or another VPN connecting your machines. This is the recommended remote access method.

### Cloudflare Tunnel

```yaml
backend:
  url: https://your-subdomain.trycloudflare.com
```

For remote access without a VPN. On your Alfred backend server, run:

```bash
cloudflared tunnel --url http://localhost:8000
```

Copy the generated URL to your config. Free tier has session limits but works for personal use.

## Configuration

All settings are in `config/settings.yaml`. No environment variables needed.

### Custom Fillers

Create `config/custom_fillers.json`:

```json
{
  "version": 1,
  "fillers": {
    "thinking": [
      "My custom thinking filler..."
    ]
  }
}
```

Update `config/settings.yaml`:
```yaml
fillers:
  custom_file: config/custom_fillers.json
```

Regenerate cache:
```bash
rm -rf cache/fillers
./setup.sh
```

## Troubleshooting

### MPS Placeholder Errors

If you see "placeholder storage" errors:
```yaml
tts:
  device: cpu  # Force CPU mode
```

Or set in config:
```yaml
debug:
  force_cpu: true
```

### Audio Device Issues

Check available devices:
```bash
python -c "import pyaudio; p = pyaudio.PyAudio(); print([p.get_device_info_by_index(i) for i in range(p.get_device_count())])"
```

### Backend Connection Failed

Run connection test:

```bash
python -c "
import asyncio
from src.config import Settings
from src.utils.backend import test_backend_connection, print_connection_help

async def test():
    settings = Settings.load()
    success, msg = await test_backend_connection(settings)
    print(msg)
    if not success:
        print_connection_help()

asyncio.run(test())
"
```

### Headphones Recommended

For best results without echo cancellation issues, use headphones. If testing without headphones:

```yaml
pipeline:
  echo_cancellation: mute_during_speech
```

This mutes the mic while the bot is speaking (prevents self-interruption but limits interruption capability).

## Development

### Running Tests

```bash
uv run pytest tests/
```

### Debug Mode

```yaml
debug:
  log_level: DEBUG
  save_audio: true
  audio_output_dir: debug/audio
```

## Architecture

```
Mic Input
  → Echo Cancellation
  → VAD (Volume Detection)
  → Whisper STT (local, MPS)
  → Filler Classification
  → Remote LLM (Alfred backend)
  → Sentence Chunking
  → Chatterbox TTS (MPS, voice cloning)
  → Audio Output
```

## Future Enhancements

- Desktop GUI (system tray, conversation window)
- Wake word detection (local)
- Push-to-talk mode
- Session tracking with Alfred backend
- Mobile support (iOS/Android)

## License

Part of the Alfred AI Assistant project.
```

---

### Task 6.4: Test Phase 6 End-to-End

**Steps:**

- [ ] **Step 1: Test echo cancellation**

```bash
python src/main.py --phase 4
```

Speak while the agent is responding. Verify:
1. Agent stops speaking when interrupted
2. Agent doesn't respond to its own voice
3. Interruption requires at least 2 words (no false positives from background noise)

- [ ] **Step 2: Test without headphones**

Set in config:
```yaml
pipeline:
  echo_cancellation: mute_during_speech
```

Run Phase 4 and verify the agent doesn't interrupt itself when playing audio through speakers.

- [ ] **Step 3: Final commit**

```bash
git add desktop/
git commit -m "feat(desktop): add phase 6 echo cancellation and interruption

- Echo cancellation with multiple modes (webrtc/mute_during_speech)
- Robust interruption detection (min 2 words)
- Comprehensive README with troubleshooting
- Phase 6 complete - POC ready for testing"
```

---

## Success Criteria

- [ ] **Phase 0:** Research documentation complete, implementer understands all libraries
- [ ] Run `./setup.sh` once on a fresh M4/M5 Mac with macOS 14+
- [ ] Setup completes in < 20 minutes with no manual intervention
- [ ] **Phase 1:** Speak into mic, see transcript printed
- [ ] **Phase 2:** Type text, hear it in cloned voice (with reference WAV)
- [ ] **Phase 3:** Speak, hear it repeated back (STT + TTS integration verified)
- [ ] **Phase 4:** Full conversation with Alfred backend
- [ ] **Phase 5:** Fillers play within 300ms, match utterance type, complete before response
- [ ] **Phase 6:** Can interrupt agent by speaking over it (2+ words)
- [ ] **Phase 6:** Agent doesn't interrupt itself without headphones (with mute_during_speech mode)
- [ ] Voice is consistent across fillers, responses, and multiple turns
- [ ] Backend connection works with configured URL (local/LAN/Tailscale/Cloudflare)
- [ ] README is comprehensive enough for someone unfamiliar with the project

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Chatterbox MPS dependency conflicts | Automated setup script with correct install order, CPU fallback |
| Filler cuts off prematurely | Filler-completion gate ensures natural finish (except on interruption) |
| Agent hears itself and interrupts | Echo cancellation with multiple modes |
| High latency from remote LLM | Context-aware fillers mitigate dead air |
| Voice inconsistency | Single reference WAV, pre-loaded in TTS service constructor |
| Setup fails on non-M4/M5 | Platform verification with clear error messages |
| Backend connection issues | Simple URL config, connection testing utility, multiple access options (VPN/Tailscale/Cloudflare) |

---

## Notes for Implementation

- **Phase 0 is required** - Familiarize with libraries before coding to prevent architectural mistakes
- **UV is already used in Alfred backend** - developers familiar with the project will know how to use it
- **No environment variables** - all config in `settings.yaml` for simplicity
- **Phased approach** - each phase produces testable, working software
- **Phase 3 is the integration test** - validates STT + TTS work together before adding LLM
- **Simple backend connection** - just a URL like the frontend uses (no complex mode switching)
- **File-based storage** - no database needed for POC, keeps it simple
- **Pipecat framework** - provides built-in VAD, turn detection, and frame processing
- **Apple Silicon focus** - MPS support is critical, CPU fallback for compatibility

---

## Next Steps After POC

1. **Desktop GUI** - System tray app with conversation window (Flet or native)
2. **Session tracking** - Integrate with Alfred backend for history
3. **Wake word** - Local "Hey Alfred" detection
4. **Push-to-talk** - Alternative activation method
5. **Mobile support** - iOS/Android via Flet or React Native
6. **Advanced fillers** - LLM-generated fillers based on context
7. **Multiple voices** - Switch between different reference voices
