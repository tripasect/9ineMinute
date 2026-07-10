# 9-Minute English - Audio Generator Notes

## Audio Generation Options

Here are several TTS options you can use. Let me know which you prefer and I'll implement it:

### 1. **OpenAI TTS** (Currently implemented in `audio_openai.py`)
- Pros: High quality, easy to use, fast
- Cons: Requires API key, costs money
- Usage: See `modules/audio_openai.py`

### 2. **ElevenLabs** (High quality, popular for YouTube)
- Pros: Excellent voice quality, wide range of voices
- Cons: API costs, rate limits
- Requires: API key from elevenlabs.io

### 3. **PlayHT** (Good quality, competitive pricing)
- Pros: Good voices, reasonable pricing
- Cons: API complexity

### 4. **Local TTS** (Free, offline)
- Options: pyttsx3, espnet, Coqui TTS
- Pros: Free, no API dependency
- Cons: Lower quality, requires more setup

### 5. **Google Cloud TTS**
- Pros: Good quality, free tier
- Cons: API complexity, requires Google Cloud setup

### 6. **DeepL TTS** (Great for translations)
- Pros: Excellent for multilingual
- Cons: API costs

## My Recommendation

For YouTube content, I'd suggest **ElevenLabs** for best quality, or **OpenAI TTS** for good quality with simpler setup.

Which would you prefer? Or do you have another option in mind?
