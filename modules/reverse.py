from config import LLM_CONFIG, REVERSE_RATIO
from openai import OpenAI
import random


class ReverseTranslator:
    """Handles the reverse translation mode where the target language is shown first."""
    
    def __init__(self):
        self.client = OpenAI(
            base_url=LLM_CONFIG["base_url"],
            api_key=LLM_CONFIG["api_key"]
        )
    
    def reverse_translate(self, text: str, source_lang: str = "English") -> str:
        """Given a translation, recover the phrase that would produce it."""
        prompt = f"""Given this {source_lang} text, recover the original phrase that would produce it.
        Return ONLY the phrase, nothing else.
        Text: {text}"""
        
        response = self.client.chat.completions.create(
            model=LLM_CONFIG["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        
        return response.choices[0].message.content.strip()
    
    def generate_reverse_segments(
        self,
        origin_phrases: list[str],
        target_translations: list[str],
        reverse_ratio: float = REVERSE_RATIO,
    ) -> list[dict]:
        """
        Create segments, flipping a fraction of them so the target language
        appears first. Returns a list of segment dicts with 'type', 'content',
        and 'translation'.
        """
        reverse_count = int(len(origin_phrases) * reverse_ratio)
        reverse_indices = set(random.sample(range(len(origin_phrases)), reverse_count))
        
        segments = []
        for i, phrase in enumerate(origin_phrases):
            if i in reverse_indices:
                segments.append({
                    "type": "reverse",
                    "content": target_translations[i],
                    "translation": phrase
                })
            else:
                segments.append({
                    "type": "normal",
                    "content": phrase,
                    "translation": target_translations[i]
                })
        
        return segments
