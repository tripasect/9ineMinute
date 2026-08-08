import json
import re

from openai import OpenAI

from config import (
    DEFAULT_ORIGIN_LANGUAGE,
    DEFAULT_TARGET_LANGUAGE,
    LANGUAGES,
    OPENROUTER_BASE_URL,
    PHRASE_MODEL,
)

from .cache import ContentCache

MAX_PHRASES_PER_CALL = 20

# Unicode ranges used to sanity-check that a translation actually uses the
# expected script for non-Latin target languages.
SCRIPT_RANGES = {
    "fa": [(0x0600, 0x06FF), (0xFB50, 0xFDFF)],
    "ar": [(0x0600, 0x06FF), (0xFB50, 0xFDFF)],
    "ur": [(0x0600, 0x06FF), (0xFB50, 0xFDFF)],
    "he": [(0x0590, 0x05FF)],
    "hi": [(0x0900, 0x097F)],
    "mr": [(0x0900, 0x097F)],
    "ne": [(0x0900, 0x097F)],
    "ja": [(0x3040, 0x30FF), (0x4E00, 0x9FFF)],
    "zh": [(0x4E00, 0x9FFF)],
    "ru": [(0x0400, 0x04FF)],
    "uk": [(0x0400, 0x04FF)],
    "el": [(0x0370, 0x03FF)],
    "th": [(0x0E00, 0x0E7F)],
    "ko": [(0xAC00, 0xD7AF)],
}


class PhraseTranslator:
    """
    Unified phrase generator + translator for the origin/target language pair.

    Generates phrases in the origin language and their translations in the
    target language within a single LLM call using PHRASE_MODEL via
    OpenRouter. Batches are capped at MAX_PHRASES_PER_CALL (20) to keep the
    model focused and reduce hallucinated / polluted output.
    """

    def __init__(self, api_key: str):
        # The OpenAI SDK now raises at construction time if api_key is falsy,
        # even though this client may never be used (e.g. --preview mode,
        # which never calls the LLM). Fall back to a placeholder so building
        # a ContentPipeline doesn't require API keys up front; a real call
        # without a valid key will simply fail with a normal API error.
        self.client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key or "unset",
        )
        self.cache = ContentCache()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_and_translate(
        self,
        topic: str = "common English phrases",
        count: int = 20,
        origin_lang: str = DEFAULT_ORIGIN_LANGUAGE,
        target_lang: str = DEFAULT_TARGET_LANGUAGE,
    ) -> list[dict]:
        """
        Return a list of dicts, each with keys 'origin' and 'target'.

        Results are cached per topic, count, and language pair. Only missing
        phrase slots trigger an LLM call. The LLM is never asked for more
        than MAX_PHRASES_PER_CALL phrases at once.

        Args:
            topic: Description of the kind of phrases to generate.
            count: Total number of phrase pairs to return.
            origin_lang: Language code for the source language (default from config).
            target_lang: Language code for the translation language (default from config).

        Returns:
            List of {'origin': str, 'target': str} dicts.
        """
        # Load any previously cached pairs for this topic+count key.
        pairs = self._load_cached_pairs(topic, count, origin_lang, target_lang)
        if pairs and len(pairs) >= count:
            print(f"  [PhraseTranslator] Loaded {len(pairs)} pairs from cache.")
            return pairs[:count]

        already_have = len(pairs)
        needed = count - already_have
        print(
            f"  [PhraseTranslator] Cache has {already_have}/{count} pairs. "
            f"Requesting {needed} more from LLM..."
        )

        existing_origin = {p["origin"] for p in pairs}

        # Fetch in chunks of MAX_PHRASES_PER_CALL
        new_pairs: list[dict] = []
        remaining = needed
        while remaining > 0:
            batch_size = min(remaining, MAX_PHRASES_PER_CALL)
            batch = self._fetch_batch(
                topic=topic,
                count=batch_size,
                origin_lang=origin_lang,
                target_lang=target_lang,
                exclude=existing_origin | {p["origin"] for p in new_pairs},
            )
            if not batch:
                print(
                    "  [PhraseTranslator] LLM returned no usable pairs — stopping early."
                )
                break
            new_pairs.extend(batch)
            remaining -= len(batch)

        all_pairs = pairs + new_pairs
        self._save_cached_pairs(topic, count, all_pairs, origin_lang, target_lang)
        return all_pairs[:count]

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(
        self, topic: str, count: int, origin_lang: str, target_lang: str
    ) -> str:
        return f"__pairs__{origin_lang}_{target_lang}__{topic}_{count}"

    def _load_cached_pairs(
        self, topic: str, count: int, origin_lang: str, target_lang: str
    ) -> list[dict]:
        key = self._cache_key(topic, count, origin_lang, target_lang)
        raw = self.cache.phrases_cache.get(key)
        if raw is None and origin_lang == "en" and target_lang == "fa":
            # Fall back to the pre-parameterization cache key format.
            raw = self.cache.phrases_cache.get(f"__pairs__{topic}_{count}")
        if not isinstance(raw, list):
            return []

        # Accept legacy 'english'/'persian' keys and normalize to 'origin'/'target'.
        valid = []
        for p in raw:
            if not isinstance(p, dict):
                continue
            origin = p.get("origin") or p.get("english")
            target = p.get("target") or p.get("persian")
            if not isinstance(origin, str) or not origin.strip():
                continue
            if not isinstance(target, str) or not self._is_valid_translation(
                target, target_lang
            ):
                continue
            valid.append({"origin": origin, "target": target})
        return valid

    def _save_cached_pairs(
        self,
        topic: str,
        count: int,
        pairs: list[dict],
        origin_lang: str,
        target_lang: str,
    ):
        key = self._cache_key(topic, count, origin_lang, target_lang)
        normalized = [
            {"origin": p["origin"], "target": p["target"]}
            for p in pairs
            if isinstance(p, dict) and p.get("origin") and p.get("target")
        ]
        self.cache.phrases_cache[key] = normalized
        self.cache._save_json(self.cache.phrases_cache, self.cache.phrases_cache_path)

        # Also persist translations individually so the legacy
        # translate_batch() interface still works (en -> fa only).
        if origin_lang == "en" and target_lang == "fa":
            for p in normalized:
                if self._is_valid_translation(p["target"], target_lang):
                    self.cache.save_translation(p["origin"], p["target"])

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _fetch_batch(
        self,
        topic: str,
        count: int,
        origin_lang: str = DEFAULT_ORIGIN_LANGUAGE,
        target_lang: str = DEFAULT_TARGET_LANGUAGE,
        exclude: set[str] = None,
    ) -> list[dict]:
        """
        Ask the LLM for `count` origin+target phrase pairs.
        Returns a list of validated {'origin', 'target'} dicts.
        """
        origin_name = LANGUAGES.get(origin_lang, {}).get("name", origin_lang)
        target_name = LANGUAGES.get(target_lang, {}).get("name", target_lang)

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
            'with exactly two keys: "origin" and "target". '
            f'The "target" value must be a clean, idiomatic {target_name} translation '
            "with NO extra commentary, bullet points, asterisks, or analysis — "
            "just the translated sentence."
        )

        user_msg = (
            f"Generate exactly {count} practical, conversational {origin_name} phrases "
            f"suitable for language learners (topic: {topic}). "
            f"For each phrase provide its {target_name} translation.{exclusion_note}\n\n"
            "Return ONLY a JSON array like:\n"
            '[\n  {"origin": "...", "target": "..."},\n  ...\n]'
        )

        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=PHRASE_MODEL,
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
                    p
                    for p in pairs
                    if isinstance(p.get("origin"), str)
                    and p["origin"].strip()
                    and isinstance(p.get("target"), str)
                    and self._is_valid_translation(p["target"], target_lang)
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

    def _is_valid_translation(self, text: str, lang_code: str) -> bool:
        if not text or len(text) < 2:
            return False
        ranges = SCRIPT_RANGES.get(lang_code)
        non_space = len(text.replace(" ", ""))
        if non_space == 0:
            return False
        if not ranges:
            # Latin-script languages: any non-empty text is acceptable.
            return True
        script_chars = sum(
            1 for c in text if any(lo <= ord(c) <= hi for lo, hi in ranges)
        )
        return (script_chars / non_space) > 0.3 and script_chars >= 2


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
            batch = uncached[start : start + MAX_PHRASES_PER_CALL]
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
                    results[global_idx] = pairs[j].get("target", phrase)
                    if self._inner._is_valid_translation(results[global_idx], "fa"):
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
            result = pairs[0].get("target", text)
            if self._inner._is_valid_translation(result, "fa"):
                self.cache.save_translation(text, result)
                return result
        return text
