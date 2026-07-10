from config import LLM_CONFIG
from openai import OpenAI
import random


class ReverseTranslator:
    """Handles the reverse translation mode where Persian is shown first."""
    
    def __init__(self):
        self.client = OpenAI(
            base_url=LLM_CONFIG["base_url"],
            api_key=LLM_CONFIG["api_key"]
        )
    
    def reverse_translate(self, persian_text: str) -> str:
        """Given a Persian translation, generate the English phrase."""
        prompt = f"""Given this Persian translation, extract the original English phrase that would produce it.
        Return ONLY the English phrase, nothing else.
        Persian: {persian_text}"""
        
        response = self.client.chat.completions.create(
            model=LLM_CONFIG["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        
        return response.choices[0].message.content.strip()
    
    def generate_reverse_segments(self, phrases: list[str], persian_translations: list[str]) -> list[dict]:
        """
        Create reverse segments where Persian is shown first.
        Returns list of segment dicts with 'type', 'content', and 'translation'
        """
        reverse_count = int(len(phrases) * 0.15)
        reverse_indices = set(random.sample(range(len(phrases)), reverse_count))
        
        segments = []
        for i, phrase in enumerate(phrases):
            if i in reverse_indices:
                segments.append({
                    "type": "reverse",
                    "content": persian_translations[i],
                    "translation": phrase
                })
            else:
                segments.append({
                    "type": "normal",
                    "content": phrase,
                    "translation": persian_translations[i]
                })
        
        return segments
