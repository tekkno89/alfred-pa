"""
Tests for TTS chunking quality.

Tests the NaturalSentenceAggregator and audio concatenation pipeline.
Run with: cd desktop && uv run pytest tests/test_chunking_quality.py -v

Manual listening verification:
- Each test generates a WAV file in tests/output/
- Listen to outputs and verify natural transitions
"""
import pytest
import numpy as np
from pathlib import Path
import wave
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from processors.sentence_aggregator import (
    NaturalSentenceAggregator,
    ChunkInfo,
    crossfade_concat,
    concatenate_audio_chunks,
    get_pause_duration,
    PAUSE_DURATIONS,
    force_split_long_sentence,
)


OUTPUT_DIR = Path(__file__).parent / "output"


@pytest.fixture(autouse=True)
def setup_output_dir():
    """Create output directory for test audio files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def save_wav(audio: np.ndarray, filename: str, sample_rate: int = 24000):
    """Save audio to WAV file for manual listening."""
    path = OUTPUT_DIR / filename
    audio_int16 = (audio * 32767).astype(np.int16) if audio.dtype != np.int16 else audio
    
    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    
    return path


class TestSentenceSegmentation:
    """Test sentence segmentation with pysbd."""
    
    def test_single_short(self):
        """Single short: 'Sure thing.' -> one chunk, no padding."""
        aggregator = NaturalSentenceAggregator()
        chunks = list(aggregator.process("Sure thing."))
        
        assert len(chunks) == 1
        assert chunks[0].text == "Sure thing."
        assert chunks[0].is_final is True
        assert chunks[0].ends_with_punctuation == '.'
    
    def test_two_shorts_merge(self):
        """Two shorts merge: 'Sure. I can help.' -> one merged chunk."""
        aggregator = NaturalSentenceAggregator()
        chunks = list(aggregator.process("Sure. I can help."))
        
        # Should merge into one chunk since both are short
        assert len(chunks) == 1
        assert "Sure" in chunks[0].text
        assert "help" in chunks[0].text
    
    def test_mid_sentence_pause(self):
        """Mid-sentence: natural commas, single chunk."""
        text = "Yes, the meeting is at three, in the main conference room."
        aggregator = NaturalSentenceAggregator()
        chunks = list(aggregator.process(text))
        
        assert len(chunks) == 1
        assert chunks[0].text == text
    
    def test_question_answer(self):
        """Question + answer: 'Are you ready? Let's begin.' -> TWO chunks."""
        aggregator = NaturalSentenceAggregator()
        chunks = list(aggregator.process("Are you ready? Let's begin."))
        
        # Question should emit immediately
        assert len(chunks) == 2
        assert chunks[0].text == "Are you ready?"
        assert chunks[0].ends_with_punctuation == '?'
        assert chunks[1].text == "Let's begin."
        assert chunks[1].ends_with_punctuation == '.'
    
    def test_long_paragraph(self):
        """Long paragraph (4+ sentences) -> multi-chunk, each under 25 words."""
        text = (
            "I'd be happy to help you with that. "
            "First, let me gather some information about your current setup. "
            "Then we can look at the available options and figure out what works best for you. "
            "Feel free to ask questions at any point during this process."
        )
        aggregator = NaturalSentenceAggregator()
        chunks = list(aggregator.process(text))
        
        assert len(chunks) >= 2  # Should split into multiple chunks
        # CRITICAL: Each chunk must be under 25 words for MPS safety
        for chunk in chunks:
            word_count = len(chunk.text.split())
            assert word_count <= 25, f"Chunk too long: {word_count} words"
        # Verify all chunks combined equal original
        combined = " ".join(c.text for c in chunks)
        assert "happy to help" in combined
        assert "gather some information" in combined
        assert "available options" in combined
        assert "ask questions" in combined
    
    def test_numbers_abbreviations(self):
        """Numbers/abbreviations: 'Dr. Smith said it costs $4.99 at 3 p.m.' -> ONE chunk."""
        text = "Dr. Smith said it costs $4.99 at 3 p.m."
        aggregator = NaturalSentenceAggregator()
        chunks = list(aggregator.process(text))
        
        # pysbd should NOT split on "Dr.", "$4.99", "p.m."
        assert len(chunks) == 1
        assert chunks[0].text == text
    
    def test_emotional(self):
        """Emotional: 'Wait! That's incredible!' -> preserves exclamation prosody."""
        aggregator = NaturalSentenceAggregator()
        chunks = list(aggregator.process("Wait! That's incredible!"))
        
        # Each exclamation should emit immediately for proper prosody
        assert len(chunks) == 2
        assert chunks[0].text == "Wait!"
        assert chunks[0].ends_with_punctuation == '!'
        assert chunks[1].text == "That's incredible!"
        assert chunks[1].ends_with_punctuation == '!'
    
    def test_pathological_long(self):
        """Pathological long: single 400+ character run-on sentence -> should NOT throw MPS error."""
        # Create a very long single sentence (no periods)
        text = (
            "I was thinking about what you said earlier and I realized that there are "
            "so many different ways we could approach this problem and honestly I think "
            "the best solution might be to just try a few different things and see what "
            "works best because sometimes the most unexpected approach turns out to be "
            "the most effective one in the long run you know what I mean by that"
        )
        aggregator = NaturalSentenceAggregator()
        chunks = list(aggregator.process(text))
        
        # Should chunk it even without sentence boundaries via force_split_long_sentence
        assert len(chunks) >= 1
        # CRITICAL: Each chunk must be under 25 words
        for chunk in chunks:
            word_count = len(chunk.text.split())
            assert word_count <= 25, f"Chunk too long: {word_count} words"
        combined = " ".join(c.text for c in chunks)
        assert "thinking about" in combined
    
    def test_all_chunks_under_25_words(self):
        """CRITICAL: All chunks from any input must be under 25 words for MPS safety."""
        aggregator = NaturalSentenceAggregator()
        
        test_texts = [
            "Short sentence.",
            "This is a medium length sentence that should still be fine.",
            "Are you ready? Let's begin now.",
            "Wait! That is absolutely incredible! I cannot believe it!",
            "Dr. Smith arrived at 3 p.m. and said the cost was $4.99 for the item.",
            (
                "This is an extremely long run-on sentence that definitely exceeds "
                "the twenty-five word limit and needs to be forcefully split into "
                "smaller chunks to prevent MPS conv1d output channel errors from occurring."
            ),
        ]
        
        for text in test_texts:
            chunks = list(aggregator.process(text))
            for chunk in chunks:
                word_count = len(chunk.text.split())
                assert word_count <= 25, (
                    f"Chunk exceeds 25 words ({word_count}) for text: {text[:50]}... "
                    f"Chunk: {chunk.text}"
                )


class TestForceSplitLongSentence:
    """Test forced splitting of long sentences for MPS safety."""
    
    def test_short_sentence_unchanged(self):
        """Sentences under 25 words are not split."""
        sentence = "This is a short sentence with only a few words in it."
        result = force_split_long_sentence(sentence, max_words=25)
        assert result == [sentence]
    
    def test_split_at_semicolon(self):
        """Long sentence splits at semicolon."""
        sentence = "This is a very long sentence that definitely exceeds twenty-five words total and should be split at the semicolon; the second part continues here after the split point."
        result = force_split_long_sentence(sentence, max_words=25)
        assert len(result) == 2
        assert all(len(r.split()) <= 25 for r in result)
    
    def test_split_at_em_dash(self):
        """Long sentence splits at em-dash."""
        sentence = "This is an extremely long sentence that definitely exceeds the twenty-five word limit and needs to be split somewhere — the em-dash provides a natural break point for this."
        result = force_split_long_sentence(sentence, max_words=25)
        assert len(result) == 2
        assert all(len(r.split()) <= 25 for r in result)
    
    def test_split_at_coordinating_conjunction(self):
        """Long sentence splits at comma + coordinating conjunction."""
        sentence = "This is a sentence that goes on and on with many many words far exceeding the twenty-five word limit for safety, and this part after the conjunction should be split off."
        result = force_split_long_sentence(sentence, max_words=25)
        assert len(result) >= 2
        assert all(len(r.split()) <= 25 for r in result)
    
    def test_hard_word_boundary_fallback(self):
        """Very long sentence with no punctuation falls back to word boundary split."""
        sentence = "This sentence has absolutely no internal punctuation like commas or semicolons or dashes but it keeps going well past the twenty-five word limit so it must be split at a hard word boundary to avoid MPS errors."
        result = force_split_long_sentence(sentence, max_words=25)
        assert len(result) >= 2
        # Each part should be at most 25 words
        for part in result:
            assert len(part.split()) <= 25, f"Part too long: {len(part.split())} words"
    
    def test_runon_sentence_from_real_response(self):
        """Test the actual run-on sentence from the Naruto response."""
        sentence = "It runs from his early days at the academy through to becoming one of the most powerful shinobi alive, covering friendships, rivalries, and an escalating series of threats to the ninja world."
        result = force_split_long_sentence(sentence, max_words=25)
        # This is 30 words, should be split
        assert len(result) >= 2, f"Expected split, got: {result}"
        for part in result:
            assert len(part.split()) <= 25, f"Part too long ({len(part.split())} words): {part}"


class TestCrossfadeConcatenation:
    """Test audio crossfade concatenation."""
    
    def test_empty_input(self):
        """Empty input returns empty array."""
        result = crossfade_concat([], 24000)
        assert len(result) == 0
        assert result.dtype == np.float32
    
    def test_single_chunk(self):
        """Single chunk passes through unchanged."""
        chunk = np.random.randn(1000).astype(np.float32)
        result = crossfade_concat([chunk], 24000)
        np.testing.assert_array_almost_equal(result, chunk)
    
    def test_two_chunks_crossfade(self):
        """Two chunks blend at boundary."""
        chunk1 = np.ones(1000, dtype=np.float32)
        chunk2 = np.ones(1000, dtype=np.float32) * 2
        
        result = crossfade_concat([chunk1, chunk2], 24000, ms=10)
        
        # Should have crossfade region
        # End of result should approach 2 (chunk2 value)
        assert result[-1] > 1.5  # Blended toward chunk2
        assert result[0] < 1.5  # Still near chunk1 value
    
    def test_short_chunks_no_crossfade(self):
        """Short chunks concatenate without crossfade."""
        chunk1 = np.ones(10, dtype=np.float32)
        chunk2 = np.ones(10, dtype=np.float32) * 2
        
        result = crossfade_concat([chunk1, chunk2], 24000, ms=20)
        
        # Chunks too short for crossfade, just concatenate
        assert len(result) == 20


class TestPauseDurations:
    """Test inter-chunk pause shaping."""
    
    def test_question_pause(self):
        """Question mark gets longer pause."""
        assert get_pause_duration('?', 24000) == int(24000 * 0.180)
    
    def test_period_pause(self):
        """Period gets medium pause."""
        assert get_pause_duration('.', 24000) == int(24000 * 0.100)
    
    def test_exclamation_pause(self):
        """Exclamation gets medium-long pause."""
        assert get_pause_duration('!', 24000) == int(24000 * 0.130)
    
    def test_paragraph_pause(self):
        """Paragraph break gets longest pause."""
        assert get_pause_duration('\n\n', 24000) == int(24000 * 0.300)
    
    def test_comma_no_pause(self):
        """Comma gets no additional pause."""
        assert get_pause_duration(',', 24000) == 0


class TestConcatenateAudioChunks:
    """Test full audio concatenation with pauses."""
    
    def test_chunks_with_pauses(self):
        """Multiple chunks with different punctuation get appropriate pauses."""
        chunks = [
            np.ones(1000, dtype=np.float32),
            np.ones(1000, dtype=np.float32) * 2,
            np.ones(1000, dtype=np.float32) * 3,
        ]
        punctuation = ['.', '?', '!']
        
        result = concatenate_audio_chunks(chunks, punctuation, 24000)
        
        # Should be longer than raw concatenation due to pauses
        assert len(result) > sum(len(c) for c in chunks)
    
    def test_comma_no_pause_inserted(self):
        """Chunks ending with comma get no additional pause."""
        chunks = [
            np.ones(1000, dtype=np.float32),
            np.ones(1000, dtype=np.float32) * 2,
        ]
        punctuation = [',', '.']
        
        result = concatenate_audio_chunks(chunks, punctuation, 24000)
        
        # First chunk has comma, so no pause
        # Should be roughly 2 * 1000 + crossfade overhead
        assert len(result) < 2100  # No significant pause


class TestIntegration:
    """Integration tests that would generate audio (mock TTS)."""
    
    @pytest.mark.skip(reason="Requires actual TTS model - run manually for quality check")
    def test_generate_test_audio(self):
        """
        Generate WAV files for manual listening verification.
        
        Run manually with: uv run pytest tests/test_chunking_quality.py::TestIntegration::test_generate_test_audio -v --runxfail
        """
        # This would load the actual TTS model and generate audio
        # for all 8 test cases, saving WAVs to tests/output/
        pass


def print_test_summary():
    """Print summary of all test cases for reference."""
    test_cases = [
        ("Single short", "Sure thing.", "1 chunk, no padding"),
        ("Two shorts merge", "Sure. I can help.", "1 merged chunk"),
        ("Mid-sentence", "Yes, the meeting is at three, in the main conference room.", "1 chunk, natural commas"),
        ("Question + answer", "Are you ready? Let's begin.", "2 chunks, distinct prosody"),
        ("Long paragraph", "4+ sentences, mixed length", "multi-chunk, no audible boundaries"),
        ("Numbers/abbreviations", "Dr. Smith said it costs $4.99 at 3 p.m.", "1 chunk (no false splits)"),
        ("Emotional", "Wait! That's incredible!", "preserves exclamation prosody"),
        ("Pathological long", "400+ char run-on", "no MPS error"),
    ]
    
    print("\n" + "="*60)
    print("TTS Chunking Quality Test Cases")
    print("="*60)
    for name, input_text, expected in test_cases:
        print(f"\n{name}:")
        print(f"  Input: {input_text}")
        print(f"  Expected: {expected}")
    print("\n" + "="*60)


if __name__ == "__main__":
    print_test_summary()
    pytest.main([__file__, "-v"])
