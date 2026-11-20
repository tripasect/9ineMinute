import os
import subprocess
import time

import requests

from config import (
    LANGUAGES,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    TTS_ORIGIN_MODEL,
    TTS_TRANSLATION_MODEL,
)
from runtime import resolve_binary

from modules.cache import ContentCache

TTS_MAX_ATTEMPTS = 3
TTS_REQUEST_TIMEOUT = (10, 45)
FFMPEG_TIMEOUT_SECONDS = 60


class OpenRouterAudioGenerator:
    """TTS using OpenRouter API."""

    def __init__(self, temp_dir: str = "temp", origin_language: str = "en"):
        self.temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)
        self.api_key = OPENROUTER_API_KEY
        self.origin_model = TTS_ORIGIN_MODEL
        self.translation_model = TTS_TRANSLATION_MODEL
        self.origin_language = origin_language
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self.cache = ContentCache()

    def generate_silent_audio(self, output_path: str, duration: float = 1.5) -> bool:
        """Create a local silent MP3 with zero network/API calls (used by --preview)."""
        self._create_silent_fallback(output_path, duration=duration)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0

    def _create_silent_fallback(self, output_path: str, duration: float = 2.0):
        """Generates a valid silent MP3 audio file using FFmpeg with pure Python fallback."""
        print(
            f"  [TTS] Generating silent fallback audio ({duration}s) for {output_path}..."
        )
        cmd = [
            resolve_binary("ffmpeg"),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            str(duration),
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            output_path,
        ]
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=FFMPEG_TIMEOUT_SECONDS,
            )
        except Exception as e:
            print(f"  [TTS] Fallback silent audio generation failed: {e}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            try:
                frame = b"\xff\xfb\x90\xc4" + b"\x00" * 413
                num_frames = int(duration * 38.28) + 1
                with open(output_path, "wb") as f:
                    f.write(frame * num_frames)
            except Exception as e2:
                print(f"  [TTS] Pure-Python fallback silent audio failed: {e2}")

    def generate_audio(
        self, text: str, language: str, output_path: str, use_cache: bool = True
    ) -> bool:
        """Generate audio using OpenRouter TTS, optionally bypassing cache.

        Regular generation reuses cached speech. Preview passes
        ``use_cache=False`` so it always verifies a fresh provider request.
        """
        # Check local cache first unless the caller explicitly requests a
        # fresh provider sample (the Preview button).
        if use_cache and self.cache.get_audio_file(text, language, output_path):
            print(f"  [TTS] Loaded audio from cache for: '{text[:25]}...' ({language})")
            return True

        api_key = os.getenv("OPENROUTER_API_KEY", "").strip() or self.api_key
        base_url = OPENROUTER_BASE_URL
        url = f"{base_url.rstrip('/')}/audio/speech"

        if not api_key:
            print("  [TTS] OPENROUTER_API_KEY is not set. Generating silent fallback audio.")
            self._create_silent_fallback(output_path)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Resolve TTS model, voice and response format from the language
        # catalog, falling back to Kokoro + MP3 for unknown languages.
        lang_cfg = LANGUAGES.get(language, {})
        model = (
            self.origin_model
            if language == self.origin_language
            else self.translation_model
        )
        voice = lang_cfg.get("voice", "af_sky")
        response_format = "pcm" if lang_cfg.get("tts_format") == "pcm" else "mp3"
        is_gemini = response_format == "pcm"

        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": response_format,
        }

        try:
            print(
                f"  [TTS] Cache miss. Generating {language} audio for: '{text[:30]}...' using {model}"
            )
            response = None
            for attempt in range(TTS_MAX_ATTEMPTS):
                try:
                    response = requests.post(
                        url, headers=headers, json=payload, stream=True,
                        timeout=TTS_REQUEST_TIMEOUT,
                    )
                    if response.status_code < 500 and response.status_code != 429:
                        break
                    if attempt + 1 < TTS_MAX_ATTEMPTS:
                        response.close()
                        time.sleep(2 ** attempt)
                except requests.RequestException:
                    if attempt + 1 == TTS_MAX_ATTEMPTS:
                        raise
                    time.sleep(2 ** attempt)

            if response.status_code != 200:
                print(
                    f"  [TTS] API Error (Status {response.status_code}): {response.text}"
                )
                self._create_silent_fallback(output_path)
                return os.path.exists(output_path) and os.path.getsize(output_path) > 0

            # Save raw bytes
            temp_pcm_path = output_path + ".raw" if is_gemini else output_path
            try:
                with open(temp_pcm_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            finally:
                response.close()

            # If we downloaded raw PCM (Gemini), convert it to standard MP3 using FFmpeg
            if is_gemini:
                cmd = [
                    resolve_binary("ffmpeg"),
                    "-y",
                    "-f",
                    "s16le",
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-i",
                    temp_pcm_path,
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "192k",
                    output_path,
                ]
                try:
                    subprocess.run(
                        cmd, capture_output=True, text=True, check=True,
                        timeout=FFMPEG_TIMEOUT_SECONDS,
                    )
                    if os.path.exists(temp_pcm_path):
                        os.remove(temp_pcm_path)
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                    print(f"  [TTS] FFmpeg PCM convert error: {getattr(e, 'stderr', None) or e}")
                    self._create_silent_fallback(output_path)
                    return os.path.exists(output_path) and os.path.getsize(output_path) > 0

            # 2. Save generated file to cache
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                self.cache.save_audio_file(text, language, output_path)
                return True

            self._create_silent_fallback(output_path)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            print(f"  [TTS] Exception: {e}")
            self._create_silent_fallback(output_path)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
