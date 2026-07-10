import json
import re
from openai import OpenAI
from .cache import ContentCache

DEEPSEEK_MODEL = "deepseek-v4-flash"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_PHRASES_PER_CALL = 20


class PhraseTranslator:
    """
    Unified phrase generator + Persian translator.

    Generates English phrases and their Persian translations in a single
    LLM call using deepseek-v4-flash via OpenRouter.
    Batches are capped at MAX_PHRASES_PER_CALL (20) to keep the model
    focused and reduce hallucinated / polluted output.
    """

    def __init__(self, api_key: str):
        self.client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
        )
        self.cache = ContentCache()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_and_translate(
        self,
        topic: str = "common English phrases",
        count: int = 20,
    ) -> list[dict]:
        """
        Return a list of dicts, each with keys 'english' and 'persian'.

        Results are served from cache when available; only uncached
        phrase-slots trigger an LLM call. The LLM is never asked for
        more than MAX_PHRASES_PER_CALL phrases at once.

        Args:
            topic: Description of the kind of phrases to generate.
            count: Total number of phrase pairs to return.

        Returns:
            List of {'english': str, 'persian': str} dicts.
        """
        # Load any previously cached pairs for this topic+count key.
        pairs = self._load_cached_pairs(topic, count)
        if pairs and len(pairs) >= count:
            print(f"  [PhraseTranslator] Loaded {len(pairs)} pairs from cache.")
            return pairs[:count]

        already_have = len(pairs)
        needed = count - already_have
        print(
            f"  [PhraseTranslator] Cache has {already_have}/{count} pairs. "
            f"Requesting {needed} more from LLM..."
        )

        existing_english = {p["english"] for p in pairs}

        # Fetch in chunks of MAX_PHRASES_PER_CALL
        new_pairs: list[dict] = []
        remaining = needed
        while remaining > 0:
            batch_size = min(remaining, MAX_PHRASES_PER_CALL)
            batch = self._fetch_batch(
                topic=topic,
                count=batch_size,
                exclude=existing_english | {p["english"] for p in new_pairs},
            )
            if not batch:
                print("  [PhraseTranslator] LLM returned no usable pairs — stopping early.")
                break
            new_pairs.extend(batch)
            remaining -= len(batch)

        all_pairs = pairs + new_pairs
        self._save_cached_pairs(topic, count, all_pairs)
        return all_pairs[:count]

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(self, topic: str, count: int) -> str:
        return f"__pairs__{topic}_{count}"

    def _load_cached_pairs(self, topic: str, count: int) -> list[dict]:
        key = self._cache_key(topic, count)
        raw = self.cache.phrases_cache.get(key)
        if isinstance(raw, list):
            # Validate each entry is a proper dict with both keys
            valid = [
                p for p in raw
                if isinstance(p, dict)
                and isinstance(p.get("english"), str)
                and isinstance(p.get("persian"), str)
                and self._is_valid_persian(p["persian"])
            ]
            return valid
        return []

    def _save_cached_pairs(self, topic: str, count: int, pairs: list[dict]):
        key = self._cache_key(topic, count)
        self.cache.phrases_cache[key] = pairs
        self.cache._save_json(self.cache.phrases_cache, self.cache.phrases_cache_path)

        # Also persist each translation individually so the old
        # translate_batch() interface still works if called elsewhere.
        for p in pairs:
            if self._is_valid_persian(p["persian"]):
                self.cache.save_translation(p["english"], p["persian"])

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _fetch_batch(
        self,
        topic: str,
        count: int,
        exclude: set[str],
    ) -> list[dict]:
        """
        Ask the LLM for `count` phrase+translation pairs.
        Returns a list of validated {'english', 'persian'} dicts.
        """
        exclusion_note = ""
        if exclude:
            sample = list(exclude)[:10]
            exclusion_note = (
                f"\nDo NOT repeat these already-used phrases: "
                + ", ".join(f'"{e}"' for e in sample)
                + ("..." if len(exclude) > 10 else "")
            )

        system_msg = (
            "You are a language-learning content creator. "
            "Output ONLY a valid JSON array. Each element must be an object "
            'with exactly two keys: "english" and "persian". '
            "The persian value must be a clean, idiomatic Persian (Farsi) translation "
            "with NO extra commentary, bullet points, asterisks, or analysis — "
            "just the translated sentence."
        )

        user_msg = (
            f"Generate exactly {count} practical, conversational English phrases "
            f"suitable for language learners (topic: {topic}). "
            f"For each phrase provide its Persian (Farsi) translation.{exclusion_note}\n\n"
            "Return ONLY a JSON array like:\n"
            '[\n  {"english": "...", "persian": "..."},\n  ...\n]'
        )

        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.3,
                    max_tokens=1200,
                )
                content = response.choices[0].message.content.strip()
                pairs = self._parse_json_pairs(content)
                valid = [
                    p for p in pairs
                    if self._is_valid_persian(p.get("persian", ""))
                    and isinstance(p.get("english"), str)
                    and p["english"].strip()
                ]
                if valid:
                    print(
                        f"  [PhraseTranslator] Got {len(valid)}/{count} valid pairs "
                        f"(attempt {attempt + 1})."
                    )
                    return valid[:count]

                print(
                    f"  [PhraseTranslator] Attempt {attempt + 1}: "
                    f"0 valid pairs parsed from response."
                )
            except Exception as exc:
                print(f"  [PhraseTranslator] Attempt {attempt + 1} error: {exc}")

        return []

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_json_pairs(self, content: str) -> list[dict]:
        """Extract a JSON array from the model response."""
        # Try direct parse first
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

        # Try to extract the first [...] block
        match = re.search(r"\[.*?\]", content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass

        return []

    def _is_valid_persian(self, text: str) -> bool:
        if not text or len(text) < 2:
            return False
        persian_chars = sum(
            1 for c in text
            if "\u0600" <= c <= "\u06ff" or "\ufb50" <= c <= "\ufdff"
        )
        non_space = len(text.replace(" ", ""))
        if non_space == 0:
            return False
        return (persian_chars / non_space) > 0.3 and persian_chars >= 2


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# Keep PersianTranslator importable so nothing outside pipeline.py breaks.
# ---------------------------------------------------------------------------

class PersianTranslator:
    """
    Thin wrapper retained for backwards compatibility.
    New code should use PhraseTranslator directly.
    """

    def __init__(self):
        from config import OPENROUTER_API_KEY
        self._inner = PhraseTranslator(api_key=OPENROUTER_API_KEY)
        self.cache = self._inner.cache

    def translate_batch(self, phrases: list[str]) -> list[str]:
        results = [""] * len(phrases)
        uncached, uncached_idx = [], []

        for i, phrase in enumerate(phrases):
            cached = self.cache.get_translation(phrase)
            if cached:
                results[i] = cached
            else:
                uncached.append(phrase)
                uncached_idx.append(i)

        if not uncached:
            print("  [Translator] All phrases cached — skipping API.")
            return results

        # Translate uncached phrases through the unified call
        for start in range(0, len(uncached), MAX_PHRASES_PER_CALL):
            batch = uncached[start: start + MAX_PHRASES_PER_CALL]
            pairs = self._inner._fetch_batch(
                topic="translation only",
                count=len(batch),
                exclude=set(),
            )
            # The batch asked for translations of specific phrases; if the
            # model generated different English text, fall back to positional
            # matching.
            for j, phrase in enumerate(batch):
                global_idx = uncached_idx[start + j]
                if j < len(pairs):
                    results[global_idx] = pairs[j].get("persian", phrase)
                    if self._inner._is_valid_persian(results[global_idx]):
                        self.cache.save_translation(phrase, results[global_idx])

        return results

    def translate_to_persian(self, text: str) -> str:
        cached = self.cache.get_translation(text)
        if cached:
            return cached
        pairs = self._inner._fetch_batch(
            topic="translation only", count=1, exclude=set()
        )
        if pairs:
            result = pairs[0].get("persian", text)
            if self._inner._is_valid_persian(result):
                self.cache.save_translation(text, result)
                return result
        return text
