import os

from dotenv import load_dotenv

from runtime import app_data_dir

# BASE_DIR is a stable, writable directory: the project directory in dev
# mode, or a per-user Application Support directory in frozen builds (since
# the frozen executable's own directory/temp extraction dir aren't reliable
# places to persist .env, settings, or output across runs).
BASE_DIR: str = app_data_dir()
OUTPUT_DIR: str = os.path.join(BASE_DIR, "output")
TEMP_DIR: str = os.path.join(BASE_DIR, "temp")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Load .env explicitly from BASE_DIR so it doesn't depend on the current
# working directory (which may differ when launched from Finder/subprocess).
load_dotenv(os.path.join(BASE_DIR, ".env"))

LLM_CONFIG: dict = {
    "base_url": os.getenv("LLM_BASE_URL", "https://freellmapi.dragon-tail.ir/v1"),
    "api_key": os.getenv(
        "LLM_API_KEY", "freellmapi-f0d2a6fe0e87bf3d5ea87a00a8fb4c530f98ebedd7fb8e0a"
    ),
    "model": os.getenv("LLM_MODEL", "auto"),
}

OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = os.getenv(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)
PHRASE_MODEL: str = os.getenv("PHRASE_MODEL", "deepseek-v4-flash")
TTS_AUDIO_MODEL: str = os.getenv(
    "TTS_AUDIO_MODEL", "google/gemini-3.1-flash-tts-preview"
)

VIDEO_SETTINGS: dict = {
    "duration_seconds": 540,
    "phrases_per_minute": 5,
    "pause_duration": 2,
    "translation_pause": 3,
    "phrase_gap_duration": 2,
    "repeat_pause_duration": 0.5,
    "background_audio": "background-music.mp3",
    "background_audio_volume": 0.3,
    "background_image": None,
    "repetitions": 0,
    "width": 1920,
    "height": 1080,
    "fps": 25,
    "watermark": "watermark.png",
    "channel_handle": "YouTube.com/@9ineMinuteEnglish",
    "fade_duration": 0.5,
}

REVERSE_RATIO: float = 0.15

TTS_KOKORO_MODEL: str = os.getenv("TTS_KOKORO_MODEL", "hexgrad/kokoro-82m")


LANGUAGES = {
    "en": {
        "name": "English",
        "direction": "ltr",
        "voice": "af_sky",
        "tts_model": TTS_AUDIO_MODEL,
        "tts_format": "pcm",
        "font": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    },
    "fa": {
        "name": "Persian (Farsi)",
        "direction": "rtl",
        "voice": "Zephyr",
        "tts_model": TTS_KOKORO_MODEL,
        "tts_format": "pcm",
        "font": "opensourcefont.ttf",
    },
    "ar": {
        "name": "Arabic",
        "direction": "rtl",
        "voice": "Zephyr",
        "tts_model": TTS_KOKORO_MODEL,
        "tts_format": "mp3",
        "font": "opensourcefont.ttf",
    },
    "es": {
        "name": "Spanish",
        "direction": "ltr",
        "voice": "ef_dora",
        "tts_model": TTS_KOKORO_MODEL,
        "tts_format": "mp3",
        "font": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    },
    "fr": {
        "name": "French",
        "direction": "ltr",
        "voice": "ff_siwis",
        "tts_model": TTS_KOKORO_MODEL,
        "tts_format": "mp3",
        "font": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    },
    "de": {
        "name": "German",
        "direction": "ltr",
        "voice": "af_sky",
        "tts_model": TTS_KOKORO_MODEL,
        "tts_format": "mp3",
        "font": "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    },
    "hi": {
        "name": "Hindi",
        "direction": "ltr",
        "voice": "hf_alpha",
        "tts_model": TTS_KOKORO_MODEL,
        "tts_format": "mp3",
        "font": "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",
    },
    "ja": {
        "name": "Japanese",
        "direction": "ltr",
        "voice": "jf_alpha",
        "tts_model": TTS_KOKORO_MODEL,
        "tts_format": "mp3",
        "font": "/System/Library/Fonts/Hiragino Sans GB.ttc",
    },
    "zh": {
        "name": "Chinese",
        "direction": "ltr",
        "voice": "zf_xiaobei",
        "tts_model": TTS_KOKORO_MODEL,
        "tts_format": "mp3",
        "font": "/System/Library/Fonts/Hiragino Sans GB.ttc",
    },
}

DEFAULT_ORIGIN_LANGUAGE = "en"
DEFAULT_TARGET_LANGUAGE = "fa"
