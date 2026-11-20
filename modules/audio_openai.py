"""Backward-compatible import for the OpenRouter audio generator."""

from .audio_openrouter import OpenRouterAudioGenerator


# Keep old imports working, while routing them through OpenRouter.
OpenAIAudioGenerator = OpenRouterAudioGenerator
