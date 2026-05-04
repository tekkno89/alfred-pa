"""
NaturalSentenceAggregator - Quality-focused text chunking for TTS.

Implements smart sentence segmentation, chunk merging, and streaming
to produce natural-sounding audio without audible chunk boundaries.

CRITICAL: Chatterbox has an MPS conv1d limit. Chunks MUST stay under
25 words to avoid "Output channels > 65536" errors.
"""
import logging
import re
from dataclasses import dataclass
from typing import Iterator, List, Optional, Callable
import numpy as np

try:
    import pysbd
    HAS_PYSBD = True
except ImportError:
    HAS_PYSBD = False
    import nltk
    nltk.download('punkt', quiet=True)
    nltk.download('punkt_tab', quiet=True)

logger = logging.getLogger(__name__)

COORDINATING_CONJUNCTIONS = r"(?:and|but|or|so|yet|for|nor)"


def force_split_long_sentence(sentence: str, max_words: int = 25) -> List[str]:
    """
    Split a long sentence at natural break points.
    
    Priority order:
    1. Semicolons (;)
    2. Em-dashes (—)
    3. Colons (:)
    4. Commas followed by coordinating conjunction
    5. Plain commas
    6. Hard word boundary (last resort)
    
    Args:
        sentence: The sentence to potentially split
        max_words: Maximum words per chunk (default 25 for MPS safety)
    
    Returns:
        List of sentence fragments, each under max_words
    """
    if len(sentence.split()) <= max_words:
        return [sentence]
    
    # Try splitting at semicolons / em-dashes / colons first
    for delimiter in [';', '—', ':']:
        if delimiter in sentence:
            parts = [p.strip() for p in sentence.split(delimiter) if p.strip()]
            result = []
            for p in parts:
                result.extend(force_split_long_sentence(p, max_words))
            return result
    
    # Try splitting at "comma + coordinating conjunction"
    pattern = rf",\s+{COORDINATING_CONJUNCTIONS}\s+"
    matches = list(re.finditer(pattern, sentence))
    if matches:
        result = []
        last_end = 0
        for m in matches:
            part = sentence[last_end:m.start()].strip()
            if part:
                result.append(part)
            last_end = m.start() + 2  # skip ", "
        tail = sentence[last_end:].strip()
        if tail:
            result.append(tail)
        # Recursively check parts that are still too long
        final = []
        for p in result:
            final.extend(force_split_long_sentence(p, max_words))
        return final
    
    # Fall back to plain commas
    if "," in sentence:
        parts = [p.strip() for p in sentence.split(",") if p.strip()]
        result = []
        buffer = []
        for p in parts:
            buffer.append(p)
            buffer_text = ", ".join(buffer)
            if len(buffer_text.split()) >= max_words // 2:
                result.append(buffer_text)
                buffer = []
        if buffer:
            result.append(", ".join(buffer))
        # Recursively check
        final = []
        for p in result:
            final.extend(force_split_long_sentence(p, max_words))
        return final
    
    # Last resort: hard split at word boundary
    words = sentence.split()
    return [" ".join(words[i:i+max_words]) for i in range(0, len(words), max_words)]


@dataclass
class ChunkInfo:
    """Information about a processed chunk."""
    text: str
    is_final: bool
    ends_with_punctuation: str  # '.', '?', '!', ',', ';', '\n\n', ''


def crossfade_concat(chunks: List[np.ndarray], sample_rate: int, ms: int = 20) -> np.ndarray:
    """
    Concatenate audio chunks with linear crossfade to eliminate clicks.
    
    Args:
        chunks: List of audio arrays (float32 or int16)
        sample_rate: Audio sample rate in Hz
        ms: Crossfade duration in milliseconds
    
    Returns:
        Concatenated audio array (float32)
    """
    if not chunks:
        return np.array([], dtype=np.float32)
    
    n_xfade = int(sample_rate * ms / 1000)
    result = chunks[0].astype(np.float32)
    
    for nxt in chunks[1:]:
        nxt = nxt.astype(np.float32)
        if len(result) < n_xfade or len(nxt) < n_xfade:
            result = np.concatenate([result, nxt])
            continue
        
        fade_out = np.linspace(1.0, 0.0, n_xfade, dtype=np.float32)
        fade_in = np.linspace(0.0, 1.0, n_xfade, dtype=np.float32)
        
        blended = result[-n_xfade:] * fade_out + nxt[:n_xfade] * fade_in
        result = np.concatenate([result[:-n_xfade], blended, nxt[n_xfade:]])
    
    return result


def trim_silence(audio: np.ndarray, threshold: float = 0.01, sample_rate: int = 24000) -> tuple[np.ndarray, int, int]:
    """
    Detect and return start/end silence samples.
    
    Returns:
        (audio, start_silence_samples, end_silence_samples)
    """
    if len(audio) == 0:
        return audio, 0, 0
    
    audio_float = audio.astype(np.float32) / 32767.0 if audio.dtype == np.int16 else audio.astype(np.float32)
    
    start_silence = 0
    for i in range(len(audio_float)):
        if abs(audio_float[i]) > threshold:
            break
        start_silence = i + 1
    
    end_silence = 0
    for i in range(len(audio_float) - 1, -1, -1):
        if abs(audio_float[i]) > threshold:
            break
        end_silence = len(audio_float) - i
    
    return audio, start_silence, end_silence


PAUSE_DURATIONS = {
    '.': 100,    # sentence end
    '?': 180,    # question
    '!': 130,    # exclamation
    '\n\n': 300, # paragraph break
    ',': 0,      # mid-sentence (no pause)
    ';': 0,      # mid-sentence
    '': 50,      # default
}


def get_pause_duration(punctuation: str, sample_rate: int) -> int:
    """Get pause duration in samples based on ending punctuation."""
    ms = PAUSE_DURATIONS.get(punctuation, PAUSE_DURATIONS[''])
    return int(sample_rate * ms / 1000)


def generate_silence(duration_samples: int) -> np.ndarray:
    """Generate silence as float32 array."""
    return np.zeros(duration_samples, dtype=np.float32)


class NaturalSentenceAggregator:
    """
    Quality-focused text chunker for TTS.
    
    Features:
    - Smart sentence segmentation (pysbd or nltk)
    - FORCED splitting of long sentences (>25 words) for MPS safety
    - Chunk merging with min/max size targets
    - Immediate emission on ? ! and paragraph breaks
    - Crossfade concatenation
    - Inter-chunk pause shaping
    """
    
    MIN_WORDS = 8
    MIN_CHARS = 50
    MAX_WORDS = 25  # CRITICAL: Lowered from 30 to 25 for MPS conv1d safety
    MAX_CHARS = 180  # Lowered proportionally
    
    def __init__(
        self,
        min_words: int = None,
        min_chars: int = None,
        max_words: int = None,
        max_chars: int = None,
        on_chunk_ready: Optional[Callable[[ChunkInfo], None]] = None,
    ):
        self.min_words = min_words or self.MIN_WORDS
        self.min_chars = min_chars or self.MIN_CHARS
        self.max_words = max_words or self.MAX_WORDS
        self.max_chars = max_chars or self.MAX_CHARS
        self.on_chunk_ready = on_chunk_ready
        
        if HAS_PYSBD:
            self._segmenter = pysbd.Segmenter(language="en", clean=False)
        else:
            self._segmenter = None
    
    def _segment_sentences(self, text: str) -> List[str]:
        """Segment text into sentences using pysbd or nltk."""
        if self._segmenter:
            return self._segmenter.segment(text)
        else:
            return nltk.sent_tokenize(text)
    
    def _count_words(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())
    
    def _get_ending_punctuation(self, text: str) -> str:
        """Get the punctuation that ends this text."""
        text = text.rstrip()
        if text.endswith('\n\n'):
            return '\n\n'
        if text.endswith('?'):
            return '?'
        if text.endswith('!'):
            return '!'
        if text.endswith('.'):
            return '.'
        if text.endswith(','):
            return ','
        if text.endswith(';'):
            return ';'
        return ''
    
    def _should_emit_immediately(self, text: str) -> bool:
        """Check if chunk should be emitted immediately regardless of size."""
        text = text.rstrip()
        return (
            text.endswith('?') or
            text.endswith('!') or
            text.endswith('\n\n')
        )
    
    def _is_above_min(self, text: str) -> bool:
        """Check if text meets minimum chunk size."""
        words = self._count_words(text)
        chars = len(text)
        return words >= self.min_words or chars >= self.min_chars
    
    def _is_above_max(self, text: str) -> bool:
        """Check if text exceeds maximum chunk size."""
        words = self._count_words(text)
        chars = len(text)
        return words > self.max_words or chars > self.max_chars
    
    def process(self, text: str) -> Iterator[ChunkInfo]:
        """
        Process text into chunks for TTS.
        
        Yields ChunkInfo objects with text and metadata.
        """
        logger.info(f"[chunker] received text: {len(text)} chars, {len(text.split())} words")
        
        sentences = self._segment_sentences(text)
        logger.info(f"[chunker] segmented into {len(sentences)} sentences")
        
        if not sentences:
            return
        
        # CRITICAL: Force-split any sentences that exceed max_words
        # This prevents MPS conv1d errors from long run-on sentences
        expanded = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            splits = force_split_long_sentence(s, max_words=self.max_words)
            if len(splits) > 1:
                logger.info(f"[chunker] force-split long sentence ({len(s.split())} words) into {len(splits)} parts")
            expanded.extend(splits)
        sentences = expanded
        
        if len(sentences) > 1:
            logger.debug(f"[chunker] after force-split: {len(sentences)} segments")
        
        buffer = ""
        chunks_emitted = 0
        
        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if not sentence:
                continue
            
            is_last = (i == len(sentences) - 1)
            
            # Check if current buffer + sentence exceeds max
            test_buffer = (buffer + " " + sentence).strip() if buffer else sentence
            
            if self._is_above_max(test_buffer) and buffer:
                # Emit current buffer first
                logger.debug(f"[chunker] emitting buffer (exceeds max): {len(buffer.split())} words")
                yield ChunkInfo(
                    text=buffer.strip(),
                    is_final=False,
                    ends_with_punctuation=self._get_ending_punctuation(buffer)
                )
                chunks_emitted += 1
                buffer = sentence
            else:
                buffer = test_buffer
            
            # Check for immediate emission triggers (? ! \n\n)
            if self._should_emit_immediately(buffer):
                logger.debug(f"[chunker] emitting immediately (punctuation trigger): {len(buffer.split())} words")
                yield ChunkInfo(
                    text=buffer.strip(),
                    is_final=is_last,
                    ends_with_punctuation=self._get_ending_punctuation(buffer)
                )
                chunks_emitted += 1
                buffer = ""
                continue
            
            # Check if buffer meets minimum size
            if self._is_above_min(buffer):
                logger.debug(f"[chunker] emitting (above min): {len(buffer.split())} words")
                yield ChunkInfo(
                    text=buffer.strip(),
                    is_final=is_last,
                    ends_with_punctuation=self._get_ending_punctuation(buffer)
                )
                chunks_emitted += 1
                buffer = ""
        
        # Emit remaining buffer
        if buffer.strip():
            logger.debug(f"[chunker] emitting final buffer: {len(buffer.split())} words")
            yield ChunkInfo(
                text=buffer.strip(),
                is_final=True,
                ends_with_punctuation=self._get_ending_punctuation(buffer)
            )
            chunks_emitted += 1
        
        logger.info(f"[chunker] total chunks emitted: {chunks_emitted}")
    
    def process_streaming(self, text_stream: Iterator[str]) -> Iterator[ChunkInfo]:
        """
        Process streaming text input.
        
        Accumulates text and yields chunks as they become ready.
        """
        buffer = ""
        sentence_buffer = ""
        
        for token in text_stream:
            buffer += token
            
            # Check for potential sentence boundaries
            if any(buffer.rstrip().endswith(p) for p in ['.', '!', '?', '\n']):
                # Try to segment what we have
                sentences = self._segment_sentences(buffer)
                
                if len(sentences) > 1:
                    # We have complete sentences
                    for sentence in sentences[:-1]:
                        sentence = sentence.strip()
                        if not sentence:
                            continue
                        # Force-split long sentences
                        for split in force_split_long_sentence(sentence, max_words=self.max_words):
                            sentence_buffer = (sentence_buffer + " " + split).strip() if sentence_buffer else split
                            
                            if self._is_above_min(sentence_buffer) or self._should_emit_immediately(sentence_buffer):
                                yield ChunkInfo(
                                    text=sentence_buffer.strip(),
                                    is_final=False,
                                    ends_with_punctuation=self._get_ending_punctuation(sentence_buffer)
                                )
                                sentence_buffer = ""
                    
                    # Keep last partial sentence in buffers
                    buffer = sentences[-1]
                    sentence_buffer = buffer
        
        # Process remaining text
        if buffer.strip() or sentence_buffer.strip():
            final_text = (sentence_buffer + " " + buffer).strip()
            for chunk in self.process(final_text):
                yield chunk


def concatenate_audio_chunks(
    chunks: List[np.ndarray],
    punctuation_types: List[str],
    sample_rate: int,
    crossfade_ms: int = 20,
) -> np.ndarray:
    """
    Concatenate audio chunks with crossfade and appropriate pauses.
    
    Args:
        chunks: List of audio arrays
        punctuation_types: List of punctuation that ended each chunk
        sample_rate: Audio sample rate
        crossfade_ms: Crossfade duration in ms
    
    Returns:
        Concatenated audio array
    """
    if not chunks:
        return np.array([], dtype=np.float32)
    
    if len(chunks) == 1:
        return chunks[0].astype(np.float32)
    
    result_chunks = []
    
    for i, (chunk, punct) in enumerate(zip(chunks, punctuation_types)):
        chunk_float = chunk.astype(np.float32) if chunk.dtype == np.int16 else chunk.astype(np.float32)
        
        # Trim trailing silence from Chatterbox output (typically 50-100ms)
        _, _, end_silence = trim_silence(chunk_float)
        if end_silence > 0:
            chunk_float = chunk_float[:-end_silence] if end_silence < len(chunk_float) else chunk_float
        
        result_chunks.append(chunk_float)
        
        # Add structured pause between chunks (not after last)
        if i < len(chunks) - 1:
            pause_samples = get_pause_duration(punct, sample_rate)
            if pause_samples > 0:
                result_chunks.append(generate_silence(pause_samples))
    
    return crossfade_concat([c for c in result_chunks if len(c) > 0], sample_rate, crossfade_ms)
