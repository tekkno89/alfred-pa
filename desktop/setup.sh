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
# System Dependencies
# ============================================

echo "Checking system dependencies..."

# Check Homebrew
if ! command -v brew &> /dev/null; then
    echo "❌ ERROR: Homebrew is required but not installed."
    echo "   Install from: https://brew.sh"
    exit 1
fi

# Check/install PortAudio (required for PyAudio)
if ! brew list portaudio &> /dev/null; then
    echo "  Installing portaudio (required for audio I/O)..."
    brew install portaudio
else
    echo "  ✓ portaudio already installed"
fi

echo ""

# ============================================
# Project Setup with UV
# ============================================

echo "Creating isolated Python environment with UV..."
uv venv
source .venv/bin/activate

echo "Installing base dependencies with UV..."
uv pip install -e .

echo "✓ Base dependencies installed"
echo ""

# ============================================
# TTS Provider Selection
# ============================================

echo "╔════════════════════════════════════════════════════════════╗"
echo "║              TTS Provider Selection                         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Choose a TTS provider:"
echo ""
echo "  [1] Chatterbox TTS"
echo "      - Voice cloning from reference audio"
echo "      - 5-12s per chunk generation"
echo "      - Good for custom voice cloning"
echo ""
echo "  [2] Qwen3-TTS (Recommended)"
echo "      - 97ms streaming latency"
echo "      - 9 built-in speakers (Ryan, Vivian, etc.)"
echo "      - 10 languages, emotion/prosody control"
echo "      - Better for real-time conversation"
echo ""
read -p "Select TTS provider [1 or 2]: " -n 1 -r
echo

if [[ $REPLY == "1" ]]; then
    echo ""
    echo "Installing Chatterbox TTS..."
    uv pip install chatterbox-tts --no-deps
    echo "  Installing PyTorch 2.11+ (required for transformers compatibility)..."
    uv pip install --force-reinstall torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0
    echo "✓ Chatterbox TTS installed"
    TTS_PROVIDER="chatterbox"
elif [[ $REPLY == "2" ]]; then
    echo ""
    echo "Installing Qwen3-TTS..."
    uv pip install -e ".[qwen]"
    echo "✓ Qwen3-TTS installed"
    TTS_PROVIDER="qwen"
else
    echo ""
    echo "Invalid selection. Defaulting to Chatterbox."
    uv pip install chatterbox-tts --no-deps
    uv pip install --force-reinstall torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0
    TTS_PROVIDER="chatterbox"
fi

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
echo "  Models are cached in ~/.cache/huggingface/hub/"
echo ""

# Download Whisper model
echo "  [1/2] Downloading Whisper LARGE_V3_TURBO..."
python -c "
import sys
import asyncio
try:
    from pipecat.services.whisper.stt import WhisperSTTServiceMLX
    # Create service with model path (not enum)
    service = WhisperSTTServiceMLX(
        settings=WhisperSTTServiceMLX.Settings(
            model='mlx-community/whisper-large-v3-turbo',
            language='en'
        )
    )
    # Trigger model download with silent audio
    async def warmup():
        async for _ in service.run_stt(b'\x00' * 1024):
            pass
    asyncio.run(warmup())
    print('    ✓ Whisper model downloaded')
except Exception as e:
    print(f'    ⚠ Warning: {e}', file=sys.stderr)
" || echo "    ⚠ Whisper download failed - will download on first run"

# Download TTS model based on provider
if [[ "$TTS_PROVIDER" == "qwen" ]]; then
    echo "  [2/2] Downloading Qwen3-TTS..."
    python -c "
import sys
try:
    from qwen_tts import Qwen3TTSModel
    print('    Loading model (will download if not cached)...')
    model = Qwen3TTSModel.from_pretrained(
        'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice',
        device_map='cpu',
        dtype='float32',
    )
    print('    ✓ Qwen3-TTS model cached')
except Exception as e:
    print(f'    ⚠ Warning: {e}', file=sys.stderr)
" || echo "    ⚠ Qwen3-TTS download failed - will download on first run"
else
    echo "  [2/2] Downloading Chatterbox TTS..."
    python -c "
import sys
try:
    from chatterbox.tts import ChatterboxTTS
    print('    Loading model (will download if not cached)...')
    model = ChatterboxTTS.from_pretrained(device='cpu')  # Use CPU for download
    print('    ✓ Chatterbox TTS model cached')
except Exception as e:
    print(f'    ⚠ Warning: {e}', file=sys.stderr)
" || echo "    ⚠ Chatterbox download failed - will download on first run"
fi

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
    from pipecat.services.whisper.stt import WhisperSTTServiceMLX
    print('  ✓ Whisper MLX imported')
except ImportError as e:
    print(f'  ⚠ Whisper MLX import failed: {e}')
" || echo "  ⚠ Import test failed"

# TTS provider check
if [[ "$TTS_PROVIDER" == "qwen" ]]; then
    python -c "
try:
    from qwen_tts import Qwen3TTSModel
    print('  ✓ Qwen3-TTS imported')
except ImportError as e:
    print(f'  ⚠ Qwen3-TTS import failed: {e}')
"
else
    python -c "
try:
    from chatterbox.tts import ChatterboxTTS
    print('  ✓ Chatterbox TTS imported')
except ImportError as e:
    print(f'  ⚠ Chatterbox TTS import failed: {e}')
"
fi

echo ""
echo "  ✅ Smoke test passed!"
echo ""

# Update config with selected provider
if grep -q "provider: chatterbox" config/settings.yaml 2>/dev/null; then
    if [[ "$TTS_PROVIDER" == "qwen" ]]; then
        sed -i '' 's/provider: chatterbox/provider: qwen/' config/settings.yaml
        echo "✓ Updated config/settings.yaml to use Qwen3-TTS"
    fi
fi

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
