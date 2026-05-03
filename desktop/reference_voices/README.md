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
