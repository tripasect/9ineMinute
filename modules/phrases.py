"""
PhraseGenerator — delegates to the unified PhraseTranslator so that phrases
and their Persian translations are always produced in a single LLM call.
"""

from config import OPENROUTER_API_KEY
from .translator import PhraseTranslator


class PhraseGenerator:
    def __init__(self):
        self._translator = PhraseTranslator(api_key=OPENROUTER_API_KEY)

    def generate_phrases(
        self,
        topic: str = "common English phrases",
        count: int = 20,
    ) -> list[str]:
        """
        Return a list of English phrases (strings only).

        Internally calls PhraseTranslator.generate_and_translate() which
        also stores Persian translations in the cache. The caller can
        retrieve translations later via ContentCache.get_translation().
        """
        # Clamp to avoid very large single calls
        from .translator import MAX_PHRASES_PER_CALL
        effective_count = min(count, MAX_PHRASES_PER_CALL)
        if count > MAX_PHRASES_PER_CALL:
            print(
                f"  [PhraseGenerator] count={count} exceeds MAX_PHRASES_PER_CALL "
                f"({MAX_PHRASES_PER_CALL}). Clamping to {effective_count}."
            )

        pairs = self._translator.generate_and_translate(
            topic=topic, count=effective_count
        )
        return [p["english"] for p in pairs]
