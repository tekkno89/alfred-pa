"""Pipeline builders for each development phase."""
import asyncio
import pyaudio
import audioop
from pathlib import Path

from src.config import Settings
from src.services.whisper_stt import WhisperSTTService
from src.services.chatterbox_tts import ChatterboxTTSService
from src.services.remote_llm import create_llm_service
from src.utils.backend import test_backend_connection, print_connection_help
from src.processors.filler_processor import FillerProcessor
from src.processors.echo_cancellation import create_echo_cancellation


async def run_phase_1(settings: Settings):
    """
    Phase 1: STT only.
    
    Listen to microphone, transcribe with Whisper, print transcript.
    No TTS, no LLM.
    """
    print("=== Phase 1: Speech-to-Text Test ===")
    print("Speak into your microphone. Press Ctrl+C to exit.\n")
    
    stt_service = WhisperSTTService(settings)
    await stt_service.warmup()  # Pre-load model weights
    
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    
    p = pyaudio.PyAudio()
    
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )
    
    print("🎤 Listening... (speak now)")
    
    frames = []
    pre_buffer = []  # Buffer recent audio to catch speech start
    MAX_PRE_BUFFER = 10  # ~100ms of audio
    silence_count = 0
    SILENCE_THRESHOLD = 25  # ~250ms of silence to end speech
    VOLUME_THRESHOLD = 300
    
    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            rms = audioop.rms(data, 2)
            
            # Keep pre-buffer of recent audio
            pre_buffer.append(data)
            if len(pre_buffer) > MAX_PRE_BUFFER:
                pre_buffer.pop(0)
            
            if rms > VOLUME_THRESHOLD:
                # Include pre-buffered audio when speech starts
                if len(frames) == 0:
                    frames.extend(pre_buffer)
                frames.append(data)
                silence_count = 0
            elif len(frames) > 0:
                frames.append(data)  # Continue recording during silence
                silence_count += 1
                
                if silence_count >= SILENCE_THRESHOLD:
                    audio_data = b"".join(frames)
                    
                    print("\n🔊 Processing speech...")
                    text = await stt_service.transcribe(audio_data, RATE)
                    
                    if text:
                        print(f"📝 Transcript: \"{text}\"")
                    else:
                        print("⚠ No speech detected")
                    
                    print("\n🎤 Listening...")
                    frames = []
                    pre_buffer = []
                    silence_count = 0
            
            await asyncio.sleep(0.01)
    
    except KeyboardInterrupt:
        print("\n\nStopping...")
    
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        print("✓ Audio stream closed")


async def run_phase_2(settings: Settings):
    """
    Phase 2: TTS only.
    
    Text input from user, synthesize with Chatterbox, play audio.
    Tests voice cloning.
    """
    print("=== Phase 2: Text-to-Speech Test ===")
    print("Type text and press Enter to hear it synthesized.")
    print("Press Ctrl+C to exit.\n")
    
    tts_service = ChatterboxTTSService(settings)
    tts_service.warmup()  # Pre-load model weights
    
    p = pyaudio.PyAudio()
    
    try:
        while True:
            text = input("Text > ").strip()
            
            if not text:
                continue
            
            if text.lower() in ["exit", "quit"]:
                break
            
            print("🔊 Synthesizing...")
            audio_data = tts_service.generate_audio(text)
            
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


async def run_phase_3(settings: Settings):
    """
    Phase 3: STT → TTS echo loop.
    
    User speaks, hears it repeated in cloned voice.
    Tests end-to-end audio flow.
    """
    print("=== Phase 3: Voice Echo Loop ===")
    print("Speak into your microphone. You'll hear it repeated back.")
    print("Press Ctrl+C to exit.\n")
    
    stt_service = WhisperSTTService(settings)
    await stt_service.warmup()  # Pre-load model weights
    tts_service = ChatterboxTTSService(settings)
    tts_service.warmup()  # Pre-load model weights
    
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
    
    print("🎤 Listening...")
    
    frames = []
    pre_buffer = []  # Buffer recent audio to catch speech start
    MAX_PRE_BUFFER = 10  # ~100ms of audio
    silence_count = 0
    SILENCE_THRESHOLD = 25
    VOLUME_THRESHOLD = 500
    
    try:
        while True:
            data = input_stream.read(CHUNK, exception_on_overflow=False)
            rms = audioop.rms(data, 2)
            
            # Keep pre-buffer of recent audio
            pre_buffer.append(data)
            if len(pre_buffer) > MAX_PRE_BUFFER:
                pre_buffer.pop(0)
            
            if rms > VOLUME_THRESHOLD:
                # Include pre-buffered audio when speech starts
                if len(frames) == 0:
                    frames.extend(pre_buffer)
                frames.append(data)
                silence_count = 0
            elif len(frames) > 0:
                frames.append(data)  # Continue recording during silence
                silence_count += 1
                
                if silence_count >= SILENCE_THRESHOLD:
                    audio_data = b"".join(frames)
                    
                    print("\n🔊 Transcribing...")
                    text = await stt_service.transcribe(audio_data, INPUT_RATE)
                    
                    if text:
                        print(f"📝 You said: \"{text}\"")
                        
                        print("🔊 Synthesizing response...")
                        response_audio = tts_service.generate_audio(text)
                        
                        print("🔊 Playing response...")
                        output_stream.write(response_audio)
                        
                        print("✓ Done")
                    else:
                        print("⚠ No speech detected")
                    
                    print("\n🎤 Listening...")
                    frames = []
                    pre_buffer = []
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


async def run_phase_4(settings: Settings):
    """
    Phase 4: Full conversation with LLM.
    
    User speaks → STT → LLM → TTS → user hears response.
    """
    print("=== Phase 4: Voice Conversation with LLM ===")
    
    if not settings.llm.enabled:
        print("❌ LLM not enabled in config/settings.yaml")
        print("   Set llm.enabled: true and configure backend.url")
        print_connection_help()
        return
    
    print("Testing backend connection...")
    success, msg = await test_backend_connection(settings)
    if not success:
        print(f"❌ {msg}")
        print_connection_help()
        return
    print(f"✓ {msg}\n")
    
    stt_service = WhisperSTTService(settings)
    await stt_service.warmup()  # Pre-load model weights
    tts_service = ChatterboxTTSService(settings)
    tts_service.warmup()  # Pre-load model weights
    llm_service = await create_llm_service(settings)
    
    if not llm_service:
        print("❌ Failed to initialize LLM service")
        return
    
    messages = [
        {"role": "system", "content": "You are Alfred, a helpful AI assistant. Respond naturally and conversationally."}
    ]
    
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
    pre_buffer = []  # Buffer recent audio to catch speech start
    MAX_PRE_BUFFER = 10  # ~100ms of audio
    silence_count = 0
    SILENCE_THRESHOLD = 25
    VOLUME_THRESHOLD = 500
    
    try:
        while True:
            data = input_stream.read(CHUNK, exception_on_overflow=False)
            rms = audioop.rms(data, 2)
            
            # Keep pre-buffer of recent audio
            pre_buffer.append(data)
            if len(pre_buffer) > MAX_PRE_BUFFER:
                pre_buffer.pop(0)
            
            if rms > VOLUME_THRESHOLD:
                # Include pre-buffered audio when speech starts
                if len(frames) == 0:
                    frames.extend(pre_buffer)
                frames.append(data)
                silence_count = 0
            elif len(frames) > 0:
                frames.append(data)  # Continue recording during silence
                silence_count += 1
                
                if silence_count >= SILENCE_THRESHOLD:
                    audio_data = b"".join(frames)
                    
                    print("🔊 Transcribing...")
                    text = await stt_service.transcribe(audio_data, INPUT_RATE)
                    
                    if text:
                        print(f"📝 You: \"{text}\"")
                        
                        messages.append({"role": "user", "content": text})
                        
                        print("🤖 Thinking...")
                        response_text = await llm_service.generate(messages)
                        
                        print(f"🤖 Alfred: \"{response_text}\"")
                        
                        messages.append({"role": "assistant", "content": response_text})
                        
                        response_audio = tts_service.generate_audio(response_text)
                        output_stream.write(response_audio)
                        
                        print("\n🎤 Listening...")
                    else:
                        print("⚠ No speech detected\n🎤 Listening...")
                    
                    frames = []
                    pre_buffer = []
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


async def run_phase_5(settings: Settings):
    """
    Phase 5: Filler system.
    
    User speaks → STT → Filler (while LLM thinks) → LLM → TTS → user hears response.
    """
    print("=== Phase 5: Filler Response System ===")
    
    if not settings.llm.enabled:
        print("❌ LLM not enabled in config/settings.yaml")
        print("   Set llm.enabled: true and configure backend.url")
        print_connection_help()
        return
    
    print("Testing backend connection...")
    success, msg = await test_backend_connection(settings)
    if not success:
        print(f"❌ {msg}")
        print_connection_help()
        return
    print(f"✓ {msg}\n")
    
    stt_service = WhisperSTTService(settings)
    await stt_service.warmup()  # Pre-load model weights
    tts_service = ChatterboxTTSService(settings)
    tts_service.warmup()  # Pre-load model weights
    llm_service = await create_llm_service(settings)
    
    if not llm_service:
        print("❌ Failed to initialize LLM service")
        return
    
    # Initialize filler processor
    filler_processor = FillerProcessor(settings)
    filler_processor.load_audio_cache(Path("cache/fillers"))
    
    messages = [
        {"role": "system", "content": "You are Alfred, a helpful AI assistant. Respond naturally and conversationally."}
    ]
    
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
    pre_buffer = []  # Buffer recent audio to catch speech start
    MAX_PRE_BUFFER = 10  # ~100ms of audio
    silence_count = 0
    SILENCE_THRESHOLD = 25
    VOLUME_THRESHOLD = 500
    
    try:
        while True:
            data = input_stream.read(CHUNK, exception_on_overflow=False)
            rms = audioop.rms(data, 2)
            
            # Keep pre-buffer of recent audio
            pre_buffer.append(data)
            if len(pre_buffer) > MAX_PRE_BUFFER:
                pre_buffer.pop(0)
            
            if rms > VOLUME_THRESHOLD:
                # Include pre-buffered audio when speech starts
                if len(frames) == 0:
                    frames.extend(pre_buffer)
                frames.append(data)
                silence_count = 0
            elif len(frames) > 0:
                frames.append(data)  # Continue recording during silence
                silence_count += 1
                
                if silence_count >= SILENCE_THRESHOLD:
                    audio_data = b"".join(frames)
                    
                    print("🔊 Transcribing...")
                    text = await stt_service.transcribe(audio_data, INPUT_RATE)
                    
                    if text:
                        print(f"📝 You: \"{text}\"")
                        
                        # Classify and play filler
                        if settings.fillers.enabled:
                            category = filler_processor.classify_text(text)
                            filler_phrase, filler_audio = filler_processor.get_filler(category)
                            
                            if filler_audio:
                                print(f"🔊 Filler: \"{filler_phrase}\"")
                                output_stream.write(filler_audio)
                            elif filler_phrase:
                                # Generate filler on demand
                                filler_audio = tts_service.generate_audio(filler_phrase)
                                output_stream.write(filler_audio)
                        
                        messages.append({"role": "user", "content": text})
                        
                        print("🤖 Thinking...")
                        response_text = await llm_service.generate(messages)
                        
                        print(f"🤖 Alfred: \"{response_text}\"")
                        
                        messages.append({"role": "assistant", "content": response_text})
                        
                        response_audio = tts_service.generate_audio(response_text)
                        output_stream.write(response_audio)
                        
                        print("\n🎤 Listening...")
                    else:
                        print("⚠ No speech detected\n🎤 Listening...")
                    
                    frames = []
                    pre_buffer = []
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


async def run_phase_6(settings: Settings):
    """
    Phase 6: Polish with echo cancellation and interruption handling.
    
    Full conversation with:
    - Echo cancellation (mute during speech or WebRTC)
    - Interruption detection (user speaks over bot)
    """
    print("=== Phase 6: Full Voice Agent with Interruption Support ===")
    
    if not settings.llm.enabled:
        print("❌ LLM not enabled in config/settings.yaml")
        print("   Set llm.enabled: true and configure backend.url")
        print_connection_help()
        return
    
    print("Testing backend connection...")
    success, msg = await test_backend_connection(settings)
    if not success:
        print(f"❌ {msg}")
        print_connection_help()
        return
    print(f"✓ {msg}\n")
    
    stt_service = WhisperSTTService(settings)
    await stt_service.warmup()  # Pre-load model weights
    tts_service = ChatterboxTTSService(settings)
    tts_service.warmup()  # Pre-load model weights
    llm_service = await create_llm_service(settings)
    
    if not llm_service:
        print("❌ Failed to initialize LLM service")
        return
    
    # Initialize filler processor
    filler_processor = FillerProcessor(settings)
    filler_processor.load_audio_cache(Path("cache/fillers"))
    
    # Initialize echo cancellation
    echo_cancel = create_echo_cancellation(settings.pipeline.echo_cancellation)
    
    messages = [
        {"role": "system", "content": "You are Alfred, a helpful AI assistant. Respond naturally and conversationally."}
    ]
    
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
    print("Press Ctrl+C to exit.")
    print("💡 You can interrupt the bot by speaking over it.\n")
    
    frames = []
    pre_buffer = []  # Buffer recent audio to catch speech start
    MAX_PRE_BUFFER = 10  # ~100ms of audio
    silence_count = 0
    SILENCE_THRESHOLD = 25
    VOLUME_THRESHOLD = 500
    MIN_WORDS_INTERRUPTION = settings.pipeline.min_words_interruption
    
    is_playing_response = False
    interrupt_buffer = []
    
    try:
        while True:
            data = input_stream.read(CHUNK, exception_on_overflow=False)
            rms = audioop.rms(data, 2)
            
            # Keep pre-buffer of recent audio
            pre_buffer.append(data)
            if len(pre_buffer) > MAX_PRE_BUFFER:
                pre_buffer.pop(0)
            
            # Check for interruption
            if rms > VOLUME_THRESHOLD and is_playing_response:
                interrupt_buffer.append(data)
                
                # Check if we have enough audio for interruption detection
                if len(interrupt_buffer) >= MIN_WORDS_INTERRUPTION * 10:  # Rough estimate
                    print("\n⚠ User interruption detected")
                    is_playing_response = False
                    output_stream.stop_stream()
                    echo_cancel.on_bot_stopped_speaking()
                    frames = []
                    pre_buffer = []
                    interrupt_buffer = []
            
            elif rms > VOLUME_THRESHOLD:
                if not echo_cancel.should_mute_mic():
                    # Include pre-buffered audio when speech starts
                    if len(frames) == 0:
                        frames.extend(pre_buffer)
                    frames.append(data)
                silence_count = 0
            
            elif len(frames) > 0:
                frames.append(data)  # Continue recording during silence
                silence_count += 1
                
                if silence_count >= SILENCE_THRESHOLD:
                    audio_data = b"".join(frames)
                    
                    print("🔊 Transcribing...")
                    text = await stt_service.transcribe(audio_data, INPUT_RATE)
                    
                    if text:
                        print(f"📝 You: \"{text}\"")
                        
                        # Play filler if enabled
                        if settings.fillers.enabled:
                            category = filler_processor.classify_text(text)
                            filler_phrase, filler_audio = filler_processor.get_filler(category)
                            
                            if filler_audio:
                                print(f"🔊 Filler: \"{filler_phrase}\"")
                                echo_cancel.on_bot_started_speaking()
                                output_stream.write(filler_audio)
                                echo_cancel.on_bot_stopped_speaking()
                            elif filler_phrase:
                                filler_audio = tts_service.generate_audio(filler_phrase)
                                echo_cancel.on_bot_started_speaking()
                                output_stream.write(filler_audio)
                                echo_cancel.on_bot_stopped_speaking()
                        
                        messages.append({"role": "user", "content": text})
                        
                        print("🤖 Thinking...")
                        response_text = await llm_service.generate(messages)
                        
                        print(f"🤖 Alfred: \"{response_text}\"")
                        
                        messages.append({"role": "assistant", "content": response_text})
                        
                        # Play response with interruption tracking
                        is_playing_response = True
                        echo_cancel.on_bot_started_speaking()
                        response_audio = tts_service.generate_audio(response_text)
                        output_stream.write(response_audio)
                        is_playing_response = False
                        echo_cancel.on_bot_stopped_speaking()
                        
                        print("\n🎤 Listening...")
                    else:
                        print("⚠ No speech detected\n🎤 Listening...")
                    
                    frames = []
                    pre_buffer = []
                    silence_count = 0
                    interrupt_buffer = []
            
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
