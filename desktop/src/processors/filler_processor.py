"""Filler response processor for mitigating LLM latency."""
import json
import random
from pathlib import Path
from typing import Optional, Tuple

from src.config import Settings


class FillerProcessor:
    """Manages filler responses: classification, caching, and playback."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.fillers = {}
        self.rules = {}
        self.audio_cache = {}
        
        self._load_fillers()
    
    def _load_fillers(self):
        """Load filler phrases from JSON files."""
        if not self.settings.fillers.enabled:
            print("Fillers disabled in config")
            return
        
        if self.settings.fillers.use_defaults:
            default_path = Path("config/fillers.json")
            if default_path.exists():
                with open(default_path) as f:
                    data = json.load(f)
                    self.fillers = data.get("fillers", {})
                    self.rules = data.get("classification_rules", {})
                print(f"✓ Loaded {sum(len(v) for v in self.fillers.values())} default fillers")
        
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
        
        scores = {}
        for category, rule in self.rules.items():
            keywords = rule.get("keywords", [])
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[category] = score
        
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
        
        cache_key = f"{category}_{self.fillers[category].index(phrase)}"
        audio = self.audio_cache.get(cache_key)
        
        return phrase, audio
    
    def load_audio_cache(self, cache_dir: Path):
        """Load pre-generated filler audio from cache directory."""
        if not cache_dir.exists():
            print("⚠ Filler audio cache not found - will generate on demand")
            return
        
        for pcm_file in cache_dir.glob("*.pcm"):
            category_idx = pcm_file.stem
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
