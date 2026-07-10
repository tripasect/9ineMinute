from config import LLM_CONFIG
from openai import OpenAI
import os


class OpenAIAudioGenerator:
    """OpenAI Text-to-Speech audio generator."""
    
    def __init__(self, temp_dir: str = "temp"):
        self.client = OpenAI(
            base_url=LLM_CONFIG["base_url"],
            api_key=LLM_CONFIG["api_key"]
        )
        self.temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)
    
    def generate_audio(self, text: str, language: str, output_path: str) -> bool:
        """Generate audio using OpenAI TTS API."""
        # Map language codes to OpenAI voice models
        voice_map = {
            "en": "alloy",
            "fa": "nova"
        }
        
        voice = voice_map.get(language, "alloy")
        
        try:
            response = self.client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
                speed=0.9  # Slightly slower for clarity
            )
            
            response.stream_to_file(output_path)
            return True
            
        except Exception as e:
            print(f"Audio generation error: {e}")
            return False
