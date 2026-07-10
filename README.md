# 9-Minute English Content Generator

A pipeline for generating bilingual English-Persian language learning videos.

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
9-minute-english/
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
```

### As Python Module

```python
from pipeline import ContentPipeline

pipeline = ContentPipeline()
video_path = pipeline.run(
    topic="travel English",
    count=20,
    output_filename="travel-english.mp4"
)
```

## Configuration

Edit `config.py` to customize:

- Video duration and phrase rate
- TTS pause durations
- Background audio settings
- API configuration

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

