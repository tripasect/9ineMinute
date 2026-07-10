import os
import json
import hashlib
import shutil
from typing import List, Dict, Optional

class ContentCache:
    """Handles caching of phrases, translations, and TTS audio to minimize API usage."""
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = cache_dir
        self.audio_dir = os.path.join(cache_dir, "audio")
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.audio_dir, exist_ok=True)
        
        self.phrases_cache_path = os.path.join(self.cache_dir, "phrases.json")
        self.translations_cache_path = os.path.join(self.cache_dir, "translations.json")
        
        self.phrases_cache = self._load_json(self.phrases_cache_path)
        self.translations_cache = self._load_json(self.translations_cache_path)

    def _load_json(self, path: str) -> dict:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"  [Cache Warning] Failed to load {path}: {e}")
        return {}

    def _save_json(self, data: dict, path: str):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  [Cache Warning] Failed to save {path}: {e}")

    # --- Phrase Caching ---
    def get_phrases(self, topic: str, count: int) -> Optional[List[str]]:
        key = f"{topic}_{count}"
        return self.phrases_cache.get(key)

    def save_phrases(self, topic: str, count: int, phrases: List[str]):
        key = f"{topic}_{count}"
        self.phrases_cache[key] = phrases
        self._save_json(self.phrases_cache, self.phrases_cache_path)

    # --- Translation Caching ---
    def get_translation(self, english_text: str) -> Optional[str]:
        return self.translations_cache.get(english_text)

    def save_translation(self, english_text: str, persian_translation: str):
        self.translations_cache[english_text] = persian_translation
        self._save_json(self.translations_cache, self.translations_cache_path)

    # --- Audio Caching ---
    def _get_audio_key(self, text: str, language: str) -> str:
        # Generate a unique MD5 hash for the text and language
        hash_object = hashlib.md5(f"{text}_{language}".encode("utf-8"))
        return hash_object.hexdigest()

    def get_audio_file(self, text: str, language: str, dest_path: str) -> bool:
        key = self._get_audio_key(text, language)
        cached_file = os.path.join(self.audio_dir, f"{key}.mp3")
        
        if os.path.exists(cached_file) and os.path.getsize(cached_file) > 0:
            # Copy from cache to destination
            shutil.copy(cached_file, dest_path)
            return True
        return False

    def save_audio_file(self, text: str, language: str, source_path: str):
        if not os.path.exists(source_path) or os.path.getsize(source_path) == 0:
            return
            
        key = self._get_audio_key(text, language)
        cached_file = os.path.join(self.audio_dir, f"{key}.mp3")
        shutil.copy(source_path, cached_file)
