import os
from .audio_openrouter import OpenRouterAudioGenerator

# Use OpenRouterAudioGenerator as the standard AudioGenerator
AudioGenerator = OpenRouterAudioGenerator
