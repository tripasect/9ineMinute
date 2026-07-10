import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

BASE_DIR: str = "/Users/tripasect/Development/9-minute-english"
OUTPUT_DIR: str = os.path.join(BASE_DIR, "output")
TEMP_DIR: str = os.path.join(BASE_DIR, "temp")

LLM_CONFIG: dict = {
    "base_url": os.getenv("LLM_BASE_URL", "https://freellmapi.dragon-tail.ir/v1"),
    "api_key": os.getenv("LLM_API_KEY", "freellmapi-d17a14a6fb6ff09e7689a66f5469d587211ce0ba43838f53"),
    "model": os.getenv("LLM_MODEL", "auto")
}

OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
TTS_AUDIO_MODEL: str = os.getenv("TTS_AUDIO_MODEL", "google/gemini-3.1-flash-tts-preview")

VIDEO_SETTINGS: dict = {
    "duration_seconds": 540,
    "phrases_per_minute": 5,
    "pause_duration": 2.5,
    "translation_pause": 4,
    "phrase_gap_duration": 3.5,
    "repeat_pause_duration": 0.5,
    "background_audio": "background-music.mp3"
}

REVERSE_RATIO: float = 0.15
