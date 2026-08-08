# 9-Minute English Content Generator

## 📥 Downloads (Desktop App)

This application is available as a standalone desktop app for Windows and macOS. You do **not** need to install Python or FFmpeg manually — everything is included in the bundle.

- **Windows**: [Download 9ineMinuteEnglish-Windows.exe](https://github.com/tripasect/9ineMinute/actions) (Go to latest "Build Binaries" run)
- **macOS**: [Download 9ineMinuteEnglish-macOS-App.zip](https://github.com/tripasect/9ineMinute/actions)

*Note: On first run, Windows or macOS might show a security warning because the app isn't signed. You can safely "Run anyway" or "Open anyway".*

## Overview

This project generates YouTube videos with the following structure:

1. English sentence displayed on screen
2. TTS reads the English phrase
3. Pause
4. Persian translation displayed on screen
5. Pause
6. TTS reads the Persian translation
7. Pause → Next phrase (loop until 9-minute mark)

~15% of the time, the order is reversed (Persian first, English second) to encourage active recall.

## Project Structure

```
9ineMinute/
├── config.py           # Configuration constants
├── pipeline.py         # Main orchestrator
├── requirements.txt    # Python dependencies
├── .env               # LLM API credentials
├── modules/
│   ├── phrases.py     # Phrase generator
│   ├── translator.py  # Persian translator
│   ├── reverse.py     # Reverse translation mode
│   ├── audio.py       # TTS audio generator interface
│   └── video.py       # FFmpeg video muxer
├── output/            # Generated videos (created at runtime)
└── temp/              # Temporary audio/video files
```

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Ensure FFmpeg is installed
brew install ffmpeg  # macOS
# or
sudo apt install ffmpeg  # Ubuntu
```

## Usage

### Command Line

```bash
# Generate a video with default settings
python pipeline.py

# Custom topic and count
python pipeline.py --topic "business English" --count 25

# Custom output filename
python pipeline.py -o "business-english-001.mp4"

# Different language pair (Spanish → Persian)
python pipeline.py --origin-lang es --target-lang fa

# Repeat the origin phrase twice after the translation
python pipeline.py --repetitions 2

# Custom background image and music
python pipeline.py --background-image my-bg.png --background-music my-track.mp3
```

The interactive `cli.py` prompts for languages, repetitions, and background
options, and the same options are available as flags:

```bash
python cli.py --origin-lang en --target-lang zh --repetitions 1 \
              --background-image bg.png --background-music music.mp3 -y
```

### As Python Module

```python
from pipeline import ContentPipeline

pipeline = ContentPipeline(
    origin_language="en",
    target_language="fa",
    repetitions=2,
    background_image="bg.png",
    background_music="music.mp3",
)
video_path = pipeline.run(
    topic="travel English",
    count=20,
    output_filename="travel-english.mp4"
)
```

## Configuration

Edit `config.py` to customize:

- `LANGUAGES` — language catalog: name, text direction, TTS model/voice,
  and font for every supported origin/target language. Add new languages
  by appending entries here.
- `DEFAULT_ORIGIN_LANGUAGE` / `DEFAULT_TARGET_LANGUAGE` — default language pair.
- `REVERSE_RATIO` — fraction of segments played in reverse order.
- `VIDEO_SETTINGS` — video duration, pause durations, background music/volume,
  background image, repetitions, resolution, fps, watermark, channel handle,
  and text colors.
- API configuration (`.env`).

Supported languages currently include `en`, `fa`, `ar`, `es`, `fr`, `de`,
`hi`, `ja`, `zh`. Extend `LANGUAGES` in `config.py` to add more.

## Audio Generation

Audio generation uses the OpenAI-compatible API. To implement a specific TTS backend:

1. Update `modules/audio.py` to implement your preferred TTS service
2. Supported backends: OpenAI TTS, ElevenLabs, PlayHT, etc.

## Requirements

- Python 3.8+
- FFmpeg installed
- OpenAI-compatible API endpoint configured in `.env`

## License

MIT License

