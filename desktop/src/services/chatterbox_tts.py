"""
Chatterbox TTS service with voice cloning support.

Features:
- Speaker conditioning prepared once at model load, reused for all chunks
- CPU fallback for MPS conv1d channel limit errors
- Natural sentence chunking with forced splitting
- Crossfade concatenation for seamless audio
- Inter-chunk pause shaping based on punctuation
- Locked generation parameters for consistent voice
- Detailed timing logs for streaming diagnosis
"""
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional, Callable

import numpy as np
import torch

from chatterbox.tts import ChatterboxTTS

from src.config import Settings, get_device
from src.processors.sentence_aggregator import (
    NaturalSentenceAggregator,
    ChunkInfo,
    crossfade_concat,
    get_pause_duration,
    generate_silence,
    trim_silence,
)
from src.utils.device import get_device_with_fallback

logger = logging.getLogger(__name__)


@dataclass
class GeneratedChunk:
    """Audio chunk with metadata."""
    audio: np.ndarray
    punctuation: str
    is_final: bool
    chunk_index: int = 0


class StreamingTimers:
    """
    Timing coordinator for TTS streaming diagnosis.
    
    Tracks elapsed time from response start and logs events
    with consistent format for analysis.
    """
    
    def __init__(self):
        self._start_time: Optional[float] = None
        self._lock = threading.Lock()
    
    def start_response(self):
        """Mark the start of a new response (TEXT_RECEIVED)."""
        with self._lock:
            self._start_time = time.time()
            tid = threading.get_ident()
            logger.info(f"[+0.000s] TEXT_RECEIVED [tid={tid}]")
    
    def rel_time(self) -> float:
        """Get seconds elapsed since response start."""
        with self._lock:
            if self._start_time is None:
                return 0.0
            return time.time() - self._start_time
    
    def log_event(self, chunk_index: int, event: str, details: str = ""):
        """Log a timing event with consistent format."""
        rel = self.rel_time()
        tid = threading.get_ident()
        chunk_label = f"chunk_{chunk_index}" if chunk_index > 0 else "init"
        msg = f"[+{rel:.3f}s] [{chunk_label}] {event} [tid={tid}]"
        if details:
            msg += f" {details}"
        logger.info(msg)


# Global timers instance - shared across TTS service and playback
_streaming_timers = StreamingTimers()


def get_streaming_timers() -> StreamingTimers:
    """Get the global streaming timers instance."""
    return _streaming_timers


class ChatterboxTTSService:
    """
    Chatterbox-Turbo TTS service with voice cloning.
    
    Uses natural sentence chunking for high-quality streaming audio
    without audible boundaries between chunks.
    """
    
    LOCKED_EXAGGERATION = 0.4
    LOCKED_CFG_WEIGHT = 0.45
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.device = get_device_with_fallback() if settings.tts.device == "auto" else get_device(settings.tts.device)
        self.sample_rate = settings.tts.sample_rate
        
        self.reference_path = None
        if settings.tts.reference_voice:
            ref_path = Path(settings.tts.reference_voice)
            if not ref_path.exists():
                logger.warning(f"Reference voice not found: {ref_path}, using default")
            else:
                self.reference_path = ref_path
                logger.info(f"Reference voice loaded: {ref_path.name}")
        
        self._model = None
        self._cpu_model = None  # Lazy-loaded for fallback
        
        self._aggregator = NaturalSentenceAggregator()
        
        self._generation_lock = threading.Lock()
        self._timers = get_streaming_timers()
    
    def _ensure_model_loaded(self):
        """Load model on first use."""
        if self._model is None:
            logger.info(f"Loading Chatterbox model on {self.device}...")
            try:
                self._model = ChatterboxTTS.from_pretrained(device=self.device)
                logger.info("Chatterbox model loaded")
            except Exception as e:
                logger.error(f"Chatterbox load error: {e}")
                if "placeholder" in str(e).lower() and self.device == "mps":
                    logger.warning("MPS placeholder error, falling back to CPU")
                    self.device = "cpu"
                    self._model = ChatterboxTTS.from_pretrained(device=self.device)
                    logger.info("Chatterbox loaded on CPU (fallback)")
                else:
                    raise
            
            # Prepare speaker conditioning once after model load
            if self.reference_path:
                logger.info(f"Preparing speaker conditioning from {self.reference_path.name}...")
                self._model.prepare_conditionals(
                    str(self.reference_path),
                    exaggeration=self.LOCKED_EXAGGERATION
                )
                logger.info("Speaker conditioning prepared")
    
    def _ensure_cpu_model_loaded(self):
        """Load CPU model for fallback (lazy)."""
        if self._cpu_model is None:
            logger.info("Loading Chatterbox CPU model for fallback...")
            self._cpu_model = ChatterboxTTS.from_pretrained(device="cpu")
            
            # Prepare speaker conditioning for CPU model too
            if self.reference_path:
                logger.info("Preparing speaker conditioning for CPU fallback...")
                self._cpu_model.prepare_conditionals(
                    str(self.reference_path),
                    exaggeration=self.LOCKED_EXAGGERATION
                )
            
            logger.info("CPU model loaded")
    
    def warmup(self):
        """Pre-load model and generate test audio."""
        self._ensure_model_loaded()
        logger.info("Warming up TTS model...")
        self._generate_chunk_with_fallback("Ready.", is_final=True, chunk_index=0)
        logger.info("TTS model ready")
    
    def _generate_chunk_on_device(self, text: str, model) -> np.ndarray:
        """
        Generate audio for text using a specific model instance.
        
        Assumes speaker conditioning is already prepared via prepare_conditionals().
        
        Args:
            text: Text to synthesize
            model: The ChatterboxTTS model instance to use
        
        Returns:
            Audio as float32 numpy array
        """
        logger.debug(f"[tts] generate() called with cached conditioning (device={model.device})")
        
        wav = model.generate(
            text,
            exaggeration=self.LOCKED_EXAGGERATION,
            cfg_weight=self.LOCKED_CFG_WEIGHT,
        )
        
        if isinstance(wav, torch.Tensor):
            audio = wav.squeeze().cpu().numpy().astype(np.float32)
        else:
            audio = np.array(wav).astype(np.float32)
        
        return audio
    
    def _generate_chunk_with_fallback(self, text: str, is_final: bool, chunk_index: int) -> np.ndarray:
        """
        Generate audio for a chunk with MPS->CPU fallback.
        
        If generation fails on MPS due to conv1d output channel limit,
        automatically retries on CPU.
        
        Args:
            text: Text to synthesize
            is_final: Whether this is the final chunk in the response
            chunk_index: 1-indexed chunk number for logging
        
        Returns:
            Audio as float32 numpy array
        """
        self._ensure_model_loaded()
        
        word_count = len(text.split())
        
        # GEN_STARTED
        self._timers.log_event(chunk_index, "GEN_STARTED", f"words={word_count}")
        gen_start = time.time()
        
        try:
            audio = self._generate_chunk_on_device(text, self._model)
            gen_duration = time.time() - gen_start
            audio_duration = len(audio) / self.sample_rate
            
            # GEN_FINISHED
            self._timers.log_event(
                chunk_index, "GEN_FINISHED",
                f"gen_dur={gen_duration:.3f}s audio_dur={audio_duration:.3f}s device={self.device}"
            )
            return audio
        
        except NotImplementedError as e:
            if "Output channels" in str(e) or "MPS" in str(e):
                logger.warning(
                    f"[tts] MPS conv1d limit hit on chunk ({word_count} words). "
                    f"Retrying on CPU. Text: {text[:80]!r}"
                )
                self._ensure_cpu_model_loaded()
                audio = self._generate_chunk_on_device(text, self._cpu_model)
                gen_duration = time.time() - gen_start
                audio_duration = len(audio) / self.sample_rate
                
                self._timers.log_event(
                    chunk_index, "GEN_FINISHED",
                    f"gen_dur={gen_duration:.3f}s audio_dur={audio_duration:.3f}s device=cpu_fallback"
                )
                return audio
            raise
        
        except RuntimeError as e:
            # Catch other MPS errors
            if "MPS" in str(e) or "Metal" in str(e):
                logger.warning(
                    f"[tts] MPS runtime error on chunk ({word_count} words). "
                    f"Retrying on CPU. Error: {e}"
                )
                self._ensure_cpu_model_loaded()
                audio = self._generate_chunk_on_device(text, self._cpu_model)
                gen_duration = time.time() - gen_start
                audio_duration = len(audio) / self.sample_rate
                
                self._timers.log_event(
                    chunk_index, "GEN_FINISHED",
                    f"gen_dur={gen_duration:.3f}s audio_dur={audio_duration:.3f}s device=cpu_fallback"
                )
                return audio
            raise
    
    def generate_audio(self, text: str) -> bytes:
        """
        Generate audio for text (non-streaming).
        
        Args:
            text: Text to synthesize
        
        Returns:
            Audio data as int16 PCM bytes
        """
        chunks = list(self._generate_chunks(text))
        
        if not chunks:
            return b''
        
        if len(chunks) == 1:
            audio = chunks[0].audio
        else:
            audio = self._concatenate_chunks(chunks)
        
        audio_int16 = (audio * 32767).astype(np.int16)
        return audio_int16.tobytes()
    
    def _generate_chunks(self, text: str) -> Iterator[GeneratedChunk]:
        """
        Generate audio chunks from text using natural chunking.
        
        Yields chunks with audio and punctuation metadata.
        """
        chunk_index = 0
        
        for chunk_info in self._aggregator.process(text):
            chunk_index += 1
            
            # CHUNK_QUEUED
            word_count = len(chunk_info.text.split())
            self._timers.log_event(
                chunk_index, "CHUNK_QUEUED",
                f"words={word_count} text={chunk_info.text[:50]!r}"
            )
            
            with self._generation_lock:
                audio = self._generate_chunk_with_fallback(
                    chunk_info.text, chunk_info.is_final, chunk_index
                )
            
            yield GeneratedChunk(
                audio=audio,
                punctuation=chunk_info.ends_with_punctuation,
                is_final=chunk_info.is_final,
                chunk_index=chunk_index,
            )
    
    def _concatenate_chunks(self, chunks: List[GeneratedChunk]) -> np.ndarray:
        """
        Concatenate audio chunks with crossfade and appropriate pauses.
        
        Handles:
        - Crossfade to eliminate clicks
        - Structured pauses based on punctuation
        - Trimming of Chatterbox's natural trailing silence
        """
        if not chunks:
            return np.array([], dtype=np.float32)
        
        result_chunks = []
        
        for i, chunk in enumerate(chunks):
            audio = chunk.audio.astype(np.float32)
            
            _, _, end_silence = trim_silence(audio)
            if end_silence > 0 and end_silence < len(audio):
                audio = audio[:-end_silence]
            
            result_chunks.append(audio)
            
            if i < len(chunks) - 1:
                pause_samples = get_pause_duration(chunk.punctuation, self.sample_rate)
                if pause_samples > 0:
                    result_chunks.append(generate_silence(pause_samples))
        
        return crossfade_concat([c for c in result_chunks if len(c) > 0], self.sample_rate, ms=20)
    
    def generate_audio_stream(
        self,
        text: str,
        on_chunk_queued: Optional[Callable[[int, int], None]] = None,
    ) -> Iterator[bytes]:
        """
        Generate audio chunks for text with natural chunking.
        
        Yields audio chunks as soon as they're ready for streaming playback.
        Each chunk is a complete, playable audio segment.
        
        Args:
            text: Text to synthesize
            on_chunk_queued: Callback(chunk_index, queue_depth) when audio is queued
        
        Yields:
            Audio data chunks as int16 PCM bytes
        """
        for chunk in self._generate_chunks(text):
            # Add pause based on punctuation (if not final chunk)
            audio = chunk.audio
            if not chunk.is_final:
                pause_samples = get_pause_duration(chunk.punctuation, self.sample_rate)
                if pause_samples > 0:
                    audio = np.concatenate([audio, generate_silence(pause_samples)])
            
            audio_int16 = (audio * 32767).astype(np.int16)
            
            # AUDIO_QUEUED - immediately after generation
            self._timers.log_event(
                chunk.chunk_index, "AUDIO_QUEUED",
                f"is_final={chunk.is_final}"
            )
            
            if on_chunk_queued:
                on_chunk_queued(chunk.chunk_index, 0)
            
            yield audio_int16.tobytes()
    
    def save_audio(self, text: str, output_path: str):
        """Generate and save audio to file."""
        audio_bytes = self.generate_audio(text)
        
        import wave
        with wave.open(output_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_bytes)
        
        logger.info(f"Audio saved to {output_path}")


async def create_tts_service(settings: Settings) -> ChatterboxTTSService:
    """Create TTS service."""
    return ChatterboxTTSService(settings)
