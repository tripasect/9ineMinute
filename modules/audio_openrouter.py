import os
import re
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

TTS_MAX_ATTEMPTS = 5
TTS_REQUEST_TIMEOUT = (10, 45)
FFMPEG_TIMEOUT_SECONDS = 60
MAX_RETRY_BACKOFF_SECONDS = 15
KOKORO_LANGUAGES = {"en", "es", "fr", "hi", "ja", "zh"}
GEMINI_VOICE = "Zephyr"


class TTSGenerationError(RuntimeError):
    """Provider or audio conversion failure with actionable details."""


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

    def _model_supports_language(self, model: str, language: str):
        """Return False only when a known model family excludes the language."""
        normalized = model.lower()
        if "kokoro" in normalized:
            return language in KOKORO_LANGUAGES
        if "gemini" in normalized:
            return language in LANGUAGES
        return None

    def _select_model(self, language: str):
        preferred = (
            self.origin_model
            if language == self.origin_language
            else self.translation_model
        )
        alternate = (
            self.translation_model
            if language == self.origin_language
            else self.origin_model
        )
        for model in dict.fromkeys((preferred, alternate)):
            if model and self._model_supports_language(model, language) is not False:
                if model != preferred:
                    print(
                        f"  [TTS] {preferred} does not support {language}; "
                        f"using configured alternative {model}."
                    )
                return model
        return None

    @staticmethod
    def _format_for_model(model: str) -> str:
        """Choose a known model's format; let the API negotiate unknown models."""
        normalized = model.lower()
        if "gemini" in normalized:
            return "pcm"
        if "kokoro" in normalized:
            return "mp3"
        return "pcm"

    @staticmethod
    def _required_response_format(response) -> str | None:
        """Read a model's mp3/pcm-only requirement from an API error."""
        try:
            error_text = response.text.lower()
        except Exception:
            return None
        if "response_format" not in error_text or "only supports" not in error_text:
            return None
        requirement = error_text.split("only supports", 1)[1].split("got", 1)[0]
        for response_format in ("pcm", "mp3"):
            if response_format in requirement:
                return response_format
        return None

    @staticmethod
    def _remove_partial_audio(*paths):
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _fail_audio(self, output_path: str, message: str, *temporary_paths):
        print(f"  [TTS] Failed: {message}")
        self._remove_partial_audio(output_path, *temporary_paths)
        raise TTSGenerationError(message)

    @staticmethod
    def _retry_delay(response, attempt: int) -> float:
        """Honor Retry-After when available; otherwise use bounded backoff."""
        retry_after = response.headers.get("Retry-After") if response is not None else None
        if retry_after:
            try:
                return min(float(retry_after), MAX_RETRY_BACKOFF_SECONDS)
            except (TypeError, ValueError):
                pass
        return min(2 ** attempt, MAX_RETRY_BACKOFF_SECONDS)

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
            return self._fail_audio(output_path, "OPENROUTER_API_KEY is not set.")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Resolve the model by origin/translation role, but fall back to the
        # other configured model when the preferred known model excludes the
        # requested language.
        lang_cfg = LANGUAGES.get(language, {})
        model = self._select_model(language)
        if not model:
            return self._fail_audio(
                output_path,
                f"Neither configured TTS model supports language '{language}'. "
                "Choose a compatible model in Settings.",
            )
        voice = (
            GEMINI_VOICE
            if "gemini" in model.lower()
            else lang_cfg.get("voice", "af_sky")
        )
        response_format = self._format_for_model(model)
        is_pcm = response_format == "pcm"

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
            for format_attempt in range(2):
                for attempt in range(TTS_MAX_ATTEMPTS):
                    try:
                        response = requests.post(
                            url, headers=headers, json=payload, stream=True,
                            timeout=TTS_REQUEST_TIMEOUT,
                        )
                        if response.status_code < 500 and response.status_code != 429:
                            break
                        if attempt + 1 < TTS_MAX_ATTEMPTS:
                            delay = self._retry_delay(response, attempt)
                            print(
                                f"  [TTS] Temporary HTTP {response.status_code}; "
                                f"retrying in {delay:g}s ({attempt + 1}/{TTS_MAX_ATTEMPTS})."
                            )
                            response.close()
                            time.sleep(delay)
                    except requests.RequestException as exc:
                        if attempt + 1 == TTS_MAX_ATTEMPTS:
                            raise
                        delay = min(2 ** attempt, MAX_RETRY_BACKOFF_SECONDS)
                        print(
                            f"  [TTS] Network error ({exc}); retrying in {delay:g}s "
                            f"({attempt + 1}/{TTS_MAX_ATTEMPTS})."
                        )
                        time.sleep(delay)

                if response is None:
                    return self._fail_audio(output_path, "No response from TTS provider.")
                if response.status_code == 200:
                    break

                required_format = self._required_response_format(response)
                if required_format and required_format != response_format and format_attempt == 0:
                    print(
                        f"  [TTS] {model} requires {required_format.upper()} output; "
                        f"retrying with that format."
                    )
                    response.close()
                    response_format = required_format
                    is_pcm = response_format == "pcm"
                    payload["response_format"] = response_format
                    continue

                error_text = response.text
                response.close()
                return self._fail_audio(
                    output_path,
                    f"{model} returned HTTP {response.status_code}: {error_text}",
                )

            if response is None or response.status_code != 200:
                return self._fail_audio(output_path, f"{model} did not return audio.")

            # Save raw bytes
            temp_pcm_path = output_path + ".raw" if is_pcm else output_path
            try:
                with open(temp_pcm_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            finally:
                response.close()

            # Convert raw PCM to the MP3 files used by the video pipeline.
            if is_pcm:
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
                    return self._fail_audio(
                        output_path,
                        "PCM-to-MP3 conversion failed.",
                        temp_pcm_path,
                    )

            # 2. Save generated file to cache
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                self.cache.save_audio_file(text, language, output_path)
                return True

            return self._fail_audio(output_path, "Provider returned an empty audio file.", temp_pcm_path)
        except TTSGenerationError:
            raise
        except Exception as e:
            return self._fail_audio(output_path, str(e), locals().get("temp_pcm_path"))
