"""Pipeline builders for each development phase."""
import asyncio
import logging
import pyaudio
import audioop
import threading
import queue
import time
from pathlib import Path

from src.config import Settings
from src.services.whisper_stt import WhisperSTTService
from src.services.chatterbox_tts import ChatterboxTTSService, get_streaming_timers
from src.services.remote_llm import create_llm_service
from src.utils.backend import test_backend_connection, print_connection_help
from src.processors.filler_processor import FillerProcessor
from src.processors.echo_cancellation import create_echo_cancellation

logger = logging.getLogger(__name__)


def play_audio_stream(output_stream, text: str, tts_service, echo_cancel=None, on_start=None, on_end=None):
    """
    Play TTS audio stream with concurrent generation and playback.
    
    Uses a queue to decouple generation from playback:
    - Generator thread creates audio chunks
    - Main thread plays chunks as they arrive
    
    Instrumented with timing logs for streaming diagnosis.
    
    Args:
        output_stream: PyAudio output stream
        text: Text to synthesize
        tts_service: TTS service instance
        echo_cancel: Optional echo cancellation controller (deprecated, use on_start/on_end)
        on_start: Optional callback when playback starts
        on_end: Optional callback when playback ends
    """
    timers = get_streaming_timers()
    timers.start_response()
    
    audio_queue = queue.Queue()
    generation_complete = threading.Event()
    playback_tid = threading.get_ident()
    
    # Track chunk indices for playback logging
    chunk_playback_state = {'index': 0}
    
    # Handle echo_cancel for backwards compatibility
    if echo_cancel and not on_start:
        on_start = echo_cancel.on_bot_started_speaking
        on_end = echo_cancel.on_bot_stopped_speaking
    
    def generate_chunks():
        """Generate audio chunks in a background thread."""
        gen_tid = threading.get_ident()
        try:
            for chunk in tts_service.generate_audio_stream(text):
                # Get chunk index from the bytes (we'll track via state)
                audio_queue.put(chunk)
        finally:
            generation_complete.set()
            timers.log_event(0, "GENERATION_COMPLETE", f"queue_final_depth={audio_queue.qsize()}")
    
    # Signal playback start
    if on_start:
        on_start()
    
    # Start generation in background thread
    gen_thread = threading.Thread(target=generate_chunks, daemon=True)
    gen_thread.start()
    timers.log_event(0, "GEN_THREAD_STARTED", f"gen_tid={gen_thread.ident}")
    
    # Play chunks as they arrive
    while True:
        try:
            # Wait for chunk with timeout to check if generation is done
            chunk = audio_queue.get(timeout=0.1)
            
            chunk_playback_state['index'] += 1
            chunk_idx = chunk_playback_state['index']
            
            # PLAYBACK_STARTED
            timers.log_event(chunk_idx, "PLAYBACK_STARTED", f"queue_remaining={audio_queue.qsize()}")
            playback_start = time.time()
            
            output_stream.write(chunk)
            
            # PLAYBACK_FINISHED
            playback_dur = time.time() - playback_start
            timers.log_event(chunk_idx, "PLAYBACK_FINISHED", f"playback_dur={playback_dur:.3f}s")
            
        except queue.Empty:
            if generation_complete.is_set() and audio_queue.empty():
                break
    
    gen_thread.join()
    
    # Signal playback end
    if on_end:
        on_end()
    
    timers.log_event(0, "RESPONSE_COMPLETE", "")


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
                        response_text = ""
                        async for token in llm_service.generate_stream(messages):
                            response_text += token
                        
                        print(f"🤖 Alfred: \"{response_text}\"")
                        
                        messages.append({"role": "assistant", "content": response_text})
                        
                        # Stream TTS sentence by sentence with concurrent playback
                        play_audio_stream(output_stream, response_text, tts_service)
                        
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
                        response_text = ""
                        async for token in llm_service.generate_stream(messages):
                            response_text += token
                        
                        print(f"🤖 Alfred: \"{response_text}\"")
                        
                        messages.append({"role": "assistant", "content": response_text})
                        
                        # Stream TTS sentence by sentence with concurrent playback
                        play_audio_stream(output_stream, response_text, tts_service)
                        
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
                        response_text = ""
                        async for token in llm_service.generate_stream(messages):
                            response_text += token
                        
                        print(f"🤖 Alfred: \"{response_text}\"")
                        
                        messages.append({"role": "assistant", "content": response_text})
                        
                        # Stream TTS sentence by sentence with interruption tracking
                        is_playing_response = True
                        play_audio_stream(
                            output_stream, 
                            response_text, 
                            tts_service,
                            on_start=echo_cancel.on_bot_started_speaking,
                            on_end=echo_cancel.on_bot_stopped_speaking
                        )
                        is_playing_response = False
                        
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
