import os
import requests
import subprocess
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, TTS_AUDIO_MODEL, TTS_KOKORO_MODEL, LANGUAGES
from .cache import ContentCache
from ..runtime import resolve_binary


class OpenRouterAudioGenerator:
    """TTS using OpenRouter API."""
    
    def __init__(self, temp_dir: str = "temp"):
        self.temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)
        self.api_key = OPENROUTER_API_KEY
        self.model = TTS_AUDIO_MODEL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.cache = ContentCache()
    
    def _create_silent_fallback(self, output_path: str, duration: float = 2.0):
        """Generates a valid silent MP3 audio file using FFmpeg."""
        print(f"  [TTS] Generating silent fallback audio ({duration}s) for {output_path}...")
        cmd = [
            resolve_binary("ffmpeg"), "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", str(duration),
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            output_path
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except Exception as e:
            print(f"  [TTS] Fallback silent audio generation failed: {e}")
            with open(output_path, "wb") as f:
                pass

    def generate_audio(self, text: str, language: str, output_path: str) -> bool:
        """Generate audio using OpenRouter TTS API with bulletproof caching and silent fallback."""
        # 1. Check local cache first to avoid hitting expensive API
        if self.cache.get_audio_file(text, language, output_path):
            print(f"  [TTS] Loaded audio from cache for: '{text[:25]}...' ({language})")
            return True
            
        url = f"{OPENROUTER_BASE_URL.rstrip('/')}/audio/speech"

        # Resolve TTS model, voice and response format from the language
        # catalog, falling back to Kokoro + MP3 for unknown languages.
        lang_cfg = LANGUAGES.get(language, {})
        model = lang_cfg.get("tts_model", TTS_KOKORO_MODEL)
        voice = lang_cfg.get("voice", "af_sky")
        response_format = "pcm" if lang_cfg.get("tts_format") == "pcm" else "mp3"
        is_gemini = response_format == "pcm"

        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": response_format
        }
        
        try:
            print(f"  [TTS] Cache miss. Generating {language} audio for: '{text[:30]}...' using {model}")
            response = requests.post(
                url, headers=self.headers, json=payload,
                stream=True, timeout=30
            )
            
            if response.status_code != 200:
                print(f"  [TTS] API Error (Status {response.status_code}): {response.text}")
                self._create_silent_fallback(output_path)
                return False
            
            # Save raw bytes
            temp_pcm_path = output_path + ".raw" if is_gemini else output_path
            with open(temp_pcm_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # If we downloaded raw PCM (Gemini), convert it to standard MP3 using FFmpeg
            if is_gemini:
                cmd = [
            resolve_binary("ffmpeg"), "-y",
            "-f", "s16le",
                    "-ar", "24000",
                    "-ac", "1",
                    "-i", temp_pcm_path,
                    "-c:a", "libmp3lame",
                    "-b:a", "192k",
                    output_path
                ]
                try:
                    subprocess.run(cmd, capture_output=True, text=True, check=True)
                    if os.path.exists(temp_pcm_path):
                        os.remove(temp_pcm_path)
                except subprocess.CalledProcessError as e:
                    print(f"  [TTS] FFmpeg PCM convert error: {e.stderr}")
                    self._create_silent_fallback(output_path)
                    return False
            
            # 2. Save generated file to cache
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                self.cache.save_audio_file(text, language, output_path)
                
            return True
        except Exception as e:
            print(f"  [TTS] Exception: {e}")
            self._create_silent_fallback(output_path)
            return False