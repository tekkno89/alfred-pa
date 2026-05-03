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

### Setup Issues

**Missing portaudio**: PyAudio requires the PortAudio library. The setup script installs it via Homebrew, but if you see build errors:
```bash
brew install portaudio
```

**pyenv version conflict**: If you use pyenv and see `pyenv: version '3.12' is not installed`:
```bash
rm desktop/.python-version  # Remove the file if it exists
```

**Model download slow**: Set `HF_TOKEN` for faster HuggingFace downloads:
```bash
export HF_TOKEN=your_token_here
./setup.sh
```
Get a token at https://huggingface.co/settings/tokens

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
