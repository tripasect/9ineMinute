#!/usr/bin/env python3
"""
9-Minute English Content Generator Pipeline

Generates bilingual English-Persian language learning videos with:
1. Phrase generation
2. Persian translation
3. Reverse translation (15% of content)
4. Audio generation
5. Loop until 9-minute mark is reached
6. Video assembly
"""

import concurrent.futures
import os
import random
import subprocess
import sys
from typing import Dict, List

# Add modules to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    DEFAULT_ORIGIN_LANGUAGE,
    DEFAULT_TARGET_LANGUAGE,
    LANGUAGES,
    OPENROUTER_API_KEY,
    OUTPUT_DIR,
    REVERSE_RATIO,
    TEMP_DIR,
    VIDEO_SETTINGS,
)
from modules.audio import AudioGenerator
from modules.reverse import ReverseTranslator
from modules.translator import PhraseTranslator
from modules.video import VideoMuxer
from runtime import bundle_dir

# Hard-coded sample phrases used by --preview so a dry-run never touches
# the LLM or TTS APIs.
PREVIEW_SAMPLE_PHRASES = {
    "en": "The quick brown fox jumps over the lazy dog",
    "fa": "این یک جمله آزمایشی برای ویدیوی آموزشی است",
    "ar": "هذه جملة تجريبية لفيديو تعليمي",
    "es": "El veloz zorro marrón salta sobre el perro perezoso",
    "fr": "Le renard brun rapide saute par-dessus le chien paresseux",
    "de": "Der schnelle braune Fuchs springt über den faulen Hund",
    "hi": "यह एक परीक्षण वाक्य है",
    "ja": "これはテスト用の文です",
    "zh": "这是一个测试句子",
}

PREVIEW_FALLBACK = "This is a sample phrase for your language video."


class ContentPipeline:
    """Main orchestrator for the video generation pipeline."""

    def __init__(
        self,
        origin_language: str = None,
        target_language: str = None,
        repetitions: int = None,
        background_image: str = None,
        background_music: str = None,
        settings: dict = None,
        preview: bool = False,
    ):
        self.origin_language = origin_language or DEFAULT_ORIGIN_LANGUAGE
        self.target_language = target_language or DEFAULT_TARGET_LANGUAGE
        self.repetitions = (
            repetitions
            if repetitions is not None
            else VIDEO_SETTINGS.get("repetitions", 0)
        )
        self.background_music = background_music
        self.settings = dict(settings or {})
        self.preview = preview

        muxer_settings = dict(self.settings)
        if background_image:
            muxer_settings["background_image"] = background_image

        self.phrase_translator = PhraseTranslator(api_key=OPENROUTER_API_KEY)
        self.reverse_gen = ReverseTranslator()
        self.audio_gen = AudioGenerator(TEMP_DIR)
        self.video_muxer = VideoMuxer(settings=muxer_settings)

    def _resolve_language(self, value: str) -> str:
        """Resolve a language code from a code or a language name."""
        if not value:
            return DEFAULT_ORIGIN_LANGUAGE
        if value in LANGUAGES:
            return value
        lower = str(value).strip().lower()
        for code, cfg in LANGUAGES.items():
            if cfg["name"].lower() == lower:
                return code
        return None

    def run(
        self,
        topic: str = "common English phrases",
        count: int = 30,
        output_filename: str = None,
        duration: int = None,
        repeat_english: bool = False,
        repetitions: int = None,
        custom_phrases_file: str = None,
        origin_language: str = None,
        target_language: str = None,
        background_image: str = None,
        background_music: str = None,
        reverse_ratio: float = None,
    ) -> str:
        """
        Run the complete pipeline from phrase generation to final video.

        Args:
            topic: Topic for phrase generation
            count: Number of phrases to generate
            output_filename: Custom output filename
            duration: Override target video duration in seconds
            repeat_english: Legacy flag; when True, equivalent to repetitions=1.
            repetitions: How many times to repeat the origin-language phrase after
                the translation (origin → target → origin × N). Applies only to
                normal (non-reverse) segments. Overrides repeat_english when > 0.
            custom_phrases_file: Path to a JSON file of phrase pairs. Each item may
                use 'origin'/'target' keys or the legacy 'english'/'persian' keys.
            origin_language: Language code (or name) of the phrase language.
            target_language: Language code (or name) of the translation language.
            background_image: Path to a background image (overrides config).
            background_music: Path to background music (overrides config).
            reverse_ratio: Fraction of segments shown in reverse order
                (defaults to REVERSE_RATIO from config).

        Returns:
            Path to generated video file
        """
        origin_code = self._resolve_language(origin_language or self.origin_language)
        target_code = self._resolve_language(target_language or self.target_language)
        if not origin_code or origin_code not in LANGUAGES:
            print(
                f"  [Warning] Unknown origin language '{origin_language}', falling back to '{DEFAULT_ORIGIN_LANGUAGE}'."
            )
            origin_code = DEFAULT_ORIGIN_LANGUAGE
        if not target_code or target_code not in LANGUAGES:
            print(
                f"  [Warning] Unknown target language '{target_language}', falling back to '{DEFAULT_TARGET_LANGUAGE}'."
            )
            target_code = DEFAULT_TARGET_LANGUAGE

        reps = repetitions if repetitions is not None else self.repetitions
        if repeat_english:
            reps = max(reps, 1)
        reps = max(0, reps)

        if background_image:
            self.video_muxer.update_settings({"background_image": background_image})
        if background_music:
            self.background_music = background_music

        origin_name = LANGUAGES[origin_code]["name"]
        target_name = LANGUAGES[target_code]["name"]

        print("=" * 60)
        print("          9-Minute English Content Pipeline")
        print("=" * 60)
        print(f"  Origin language : {origin_name} ({origin_code})")
        print(f"  Target language : {target_name} ({target_code})")
        print(f"  Repetitions     : {reps}")

        # Step 1: Generate phrases + translations in one LLM call
        if custom_phrases_file:
            print(
                f"\n[1/5] Loading custom phrases and translations from {custom_phrases_file}..."
            )
            import json

            with open(custom_phrases_file, "r", encoding="utf-8") as f:
                pairs = json.load(f)

            def _pick(p, keys):
                for k in keys:
                    if k in p:
                        return p[k]
                return None

            if not isinstance(pairs, list) or not all(
                isinstance(p, dict)
                and _pick(p, ("origin", "english")) is not None
                and _pick(p, ("target", "persian")) is not None
                for p in pairs
            ):
                print(
                    "  [Error] Custom phrases file must be a JSON array of objects with "
                    "'origin'/'target' (or legacy 'english'/'persian') keys."
                )
                sys.exit(1)

            phrases = [_pick(p, ("origin", "english")) for p in pairs]
            target_translations = [_pick(p, ("target", "persian")) for p in pairs]
            print(
                f"  Loaded {len(phrases)} custom phrase+translation pairs (LLM bypassed)."
            )
        else:
            print("\n[1/5] Generating phrases and translations (unified call)...")
            pairs = self.phrase_translator.generate_and_translate(
                topic=topic,
                count=count,
                origin_lang=origin_code,
                target_lang=target_code,
            )
            if not pairs:
                print("  [Error] No phrase pairs generated.")
                sys.exit(1)
            phrases = [p["origin"] for p in pairs]
            target_translations = [p["target"] for p in pairs]
            print(f"  Generated {len(phrases)} phrase+translation pairs.")

        # Step 2 is now merged into Step 1 — kept as a no-op label for clarity
        print("\n[2/5] Translations ready (included in unified call).")

        # Step 3: Create segments (Normal / Reverse ~REVERSE_RATIO)
        print("\n[3/5] Creating translation segments...")
        ratio = REVERSE_RATIO if reverse_ratio is None else reverse_ratio
        segments = self.reverse_gen.generate_reverse_segments(
            phrases, target_translations, reverse_ratio=ratio
        )
        reverse_count = sum(1 for s in segments if s["type"] == "reverse")
        print(f"  Total segments: {len(segments)}")
        print(f"  Reverse segments ({int(ratio * 100)}%): {reverse_count}")

        # Step 4: Generate unique TTS audio files and cache them
        print("\n[4/5] Generating unique TTS audio files in parallel...")
        unique_audio_cache = {}
        audio_tasks = []

        for i, segment in enumerate(segments):
            # Normal segment: slide 1 is origin language, slide 2 is target language.
            # Reverse segment: slide 1 is target language, slide 2 is origin language.
            normal_or_reverse = segment["type"]

            # Origin-language audio
            origin_text = (
                segment["translation"]
                if normal_or_reverse == "reverse"
                else segment["content"]
            )
            origin_audio_path = os.path.join(TEMP_DIR, f"audio_origin_{i}.mp3")
            if origin_text not in unique_audio_cache:
                unique_audio_cache[origin_text] = origin_audio_path
                audio_tasks.append((origin_text, origin_code, origin_audio_path))

            # Target-language audio
            target_text = (
                segment["content"]
                if normal_or_reverse == "reverse"
                else segment["translation"]
            )
            target_audio_path = os.path.join(TEMP_DIR, f"audio_target_{i}.mp3")
            if target_text not in unique_audio_cache:
                unique_audio_cache[target_text] = target_audio_path
                audio_tasks.append((target_text, target_code, target_audio_path))

            segment["audio_origin"] = unique_audio_cache[origin_text]
            segment["audio_target"] = unique_audio_cache[target_text]

        if audio_tasks:
            if self.preview:
                print(
                    f"  Preview mode: generating {len(audio_tasks)} real TTS audio clips..."
                )
            else:
                print(f"  Launching {len(audio_tasks)} audio generation tasks...")

            # Preview deliberately uses real TTS so it is an accurate sample
            # of a regular run. A failed request must stop generation instead
            # of allowing fallback/silent audio to produce a false success.
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(
                        self.audio_gen.generate_audio,
                        text,
                        lang,
                        path,
                        use_cache=not self.preview,
                    )
                    for text, lang, path in audio_tasks
                ]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        if not future.result():
                            raise RuntimeError(
                                "TTS provider did not generate an audio file."
                            )
                    except Exception as e:
                        raise RuntimeError(f"Audio generation failed: {e}") from e

        # Step 5: Build up clips to hit target duration
        if duration == -1:
            target_duration = float("inf")
            loop_once = True
        else:
            target_duration = (
                duration
                if duration is not None
                else VIDEO_SETTINGS.get("duration_seconds", 540)
            )
            loop_once = False

        print(
            f"\n[5/5] Building clips & looping to reach target of {'Auto (1 pass)' if loop_once else str(target_duration) + 's'}..."
        )

        clip_paths = []
        current_duration = 0.0
        current_frame_global_offset = 0  # Track total frames processed
        fps = self.video_muxer.fps  # Frames per second for video generation

        # Estimate total frames for the entire video (used for consistent wave animation)
        # This needs to be a reasonable upper bound for accurate wave phase calculation
        if target_duration == float("inf"):
            estimated_total_frames_global = (
                36000 * fps
            )  # 10 hour upper bound for Auto mode
        else:
            estimated_total_frames_global = int(
                target_duration * fps * 1.5
            )  # 1.5x buffer

        pause_after_tts = self.settings.get(
            "pause_duration", VIDEO_SETTINGS.get("pause_duration", 2.5)
        )
        repeat_pause = self.settings.get(
            "repeat_pause_duration", VIDEO_SETTINGS.get("repeat_pause_duration", 0.0)
        )
        gap_dur = self.settings.get(
            "phrase_gap_duration", VIDEO_SETTINGS.get("phrase_gap_duration", 3.0)
        )

        loop_count = 0
        while current_duration < target_duration:
            loop_count += 1
            print(
                f"  --- Running Loop #{loop_count} (Current total: {current_duration:.1f}s) ---"
            )

            # Shuffle segments on subsequent loops to keep order dynamic
            current_loop_segments = list(segments)
            if loop_count > 1:
                random.shuffle(current_loop_segments)

            for i, segment in enumerate(current_loop_segments):
                if current_duration >= target_duration:
                    break

                print(
                    f"    [Segment {i + 1:02d}/{len(current_loop_segments)}] Generating clips (Current total: {current_duration:.1f}s)...",
                    flush=True,
                )

                seg_id = f"loop{loop_count}_seg{i}"
                is_reverse = segment["type"] == "reverse"

                # Slide 1 and Slide 2 details
                if not is_reverse:
                    # Slide 1: Origin language only
                    txt_1, txt_2_1, lang_1, lang_2_1 = (
                        segment["content"],
                        "",
                        origin_code,
                        target_code,
                    )
                    audio_1 = segment["audio_origin"]

                    # Slide 2: Origin + Target translation
                    txt_2, txt_2_2, lang_2, lang_2_2 = (
                        segment["content"],
                        segment["translation"],
                        origin_code,
                        target_code,
                    )
                    audio_2 = segment["audio_target"]
                else:
                    # Slide 1: Target language only
                    txt_1, txt_2_1, lang_1, lang_2_1 = (
                        segment["content"],
                        "",
                        target_code,
                        origin_code,
                    )
                    audio_1 = segment["audio_target"]

                    # Slide 2: Target + Origin translation
                    txt_2, txt_2_2, lang_2, lang_2_2 = (
                        segment["content"],
                        segment["translation"],
                        target_code,
                        origin_code,
                    )
                    audio_2 = segment["audio_origin"]

                clip_path_1 = os.path.join(TEMP_DIR, f"clip_{seg_id}_s1.mov")
                clip_path_2 = os.path.join(TEMP_DIR, f"clip_{seg_id}_s2.mov")
                gap_clip_path = os.path.join(TEMP_DIR, f"clip_{seg_id}_gap.mov")

                # Calculate durations
                dur_1 = self.video_muxer.get_audio_duration(audio_1) + pause_after_tts
                dur_2 = self.video_muxer.get_audio_duration(audio_2) + pause_after_tts

                # Generate Clip 1 (Primary Text Only)
                success_1 = self.video_muxer.create_video_clip(
                    primary_text=txt_1,
                    secondary_text=txt_2_1,
                    primary_lang=lang_1,
                    secondary_lang=lang_2_1,
                    audio_path=audio_1,
                    total_duration=dur_1,
                    output_path=clip_path_1,
                    current_frame_global_offset=current_frame_global_offset,
                    total_frames_global=estimated_total_frames_global,
                )
                if not success_1:
                    raise RuntimeError(
                        f"Failed to create the origin-language video clip for segment {i + 1}."
                    )
                clip_paths.append(clip_path_1)
                current_duration += dur_1
                current_frame_global_offset += int(dur_1 * fps)

                # Generate Clip 2 (Primary + Translation Text)
                success_2 = self.video_muxer.create_video_clip(
                    primary_text=txt_2,
                    secondary_text=txt_2_2,
                    primary_lang=lang_2,
                    secondary_lang=lang_2_2,
                    audio_path=audio_2,
                    total_duration=dur_2,
                    output_path=clip_path_2,
                    current_frame_global_offset=current_frame_global_offset,
                    total_frames_global=estimated_total_frames_global,
                )
                if not success_2:
                    raise RuntimeError(
                        f"Failed to create the translated video clip for segment {i + 1}."
                    )
                clip_paths.append(clip_path_2)
                current_duration += dur_2
                current_frame_global_offset += int(dur_2 * fps)

                # Optional repeat clips: origin phrase repeated with the target
                # translation kept visible. Only applies to normal segments.
                if reps > 0 and not is_reverse:
                    for rep in range(reps):
                        clip_path_3 = os.path.join(
                            TEMP_DIR, f"clip_{seg_id}_s3r{rep}.mov"
                        )
                        dur_3 = (
                            self.video_muxer.get_audio_duration(audio_1) + repeat_pause
                        )
                        success_3 = self.video_muxer.create_video_clip(
                            primary_text=txt_1,
                            secondary_text=txt_2_2,  # keep target translation visible below
                            primary_lang=lang_1,
                            secondary_lang=lang_2_2,
                            audio_path=audio_1,
                            total_duration=dur_3,
                            output_path=clip_path_3,
                            current_frame_global_offset=current_frame_global_offset,
                            total_frames_global=estimated_total_frames_global,
                            keep_text_visible=True,  # keep text on screen for the repeat
                        )
                        if not success_3:
                            raise RuntimeError(
                                f"Failed to create the repeated origin-language clip for segment {i + 1}."
                            )
                        clip_paths.append(clip_path_3)
                        current_duration += dur_3
                        current_frame_global_offset += int(dur_3 * fps)

                # Generate Phrase Gap Clip (silence pause between phrases)
                success_gap = self.video_muxer.create_silence_clip(
                    gap_dur,
                    gap_clip_path,
                    current_frame_global_offset=current_frame_global_offset,
                    total_frames_global=estimated_total_frames_global,
                )
                if success_gap:
                    clip_paths.append(gap_clip_path)
                    current_duration += gap_dur
                    current_frame_global_offset += int(gap_dur * fps)

            # Safeguard to prevent infinite loops if no clips are generated
            if not clip_paths and loop_count > 1:
                print(
                    "  [Error] No new video clips were successfully generated in this loop. Exiting to prevent infinite loop."
                )
                sys.exit(1)

            if loop_once:
                break

        # Assemble the final video
        print(
            f"\n[Assembly] Assembling final video from {len(clip_paths)} clips (Total: {current_duration:.1f}s)..."
        )
        bg_audio = self._get_background_audio()

        if output_filename is None:
            output_filename = "9_minute_language_video.mp4"

        final_video_path = self.video_muxer.assemble_final_video(
            clip_paths=clip_paths,
            ambient_audio=bg_audio,
            output_filename=output_filename,
        )

        print(f"\n{'=' * 60}")
        print("🎉 Video generated successfully!")
        print(f"🎬 Location: {final_video_path}")
        print(
            f"⏱️  Duration: {current_duration:.1f}s ({current_duration / 60:.1f} mins)"
        )
        print(f"{'=' * 60}")

        return final_video_path

    def _get_background_audio(self) -> str:
        """Get background ambient audio file path if configured."""
        bg_audio = (
            self.background_music
            or self.settings.get("background_audio")
            or VIDEO_SETTINGS.get("background_audio", "background-music.mp3")
        )

        # 1. Direct path
        if os.path.exists(bg_audio):
            return bg_audio

        # 2. Bundled path (PyInstaller)
        bundled_bg = os.path.join(bundle_dir(), os.path.basename(bg_audio))
        if os.path.exists(bundled_bg):
            return bundled_bg

        # 3. Project-relative path (Dev)
        abs_bg = os.path.join(os.path.dirname(os.path.abspath(__file__)), bg_audio)
        if os.path.exists(abs_bg):
            return abs_bg

        return None


def main():
    """Main entry point for the pipeline."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate 9-minute English-Persian language learning videos"
    )
    parser.add_argument(
        "--topic",
        "-t",
        type=str,
        default="pivotal English phrases",
        help="Topic for phrase generation",
    )
    parser.add_argument(
        "--count",
        "-c",
        type=int,
        default=30,
        help="Number of unique phrases to generate (cached and looped to hit 9 minutes)",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None, help="Custom output filename"
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=int,
        default=None,
        help="Target video duration in seconds (defaults to 540 / 9 minutes)",
    )

    parser.add_argument(
        "--repeat",
        "-r",
        action="store_true",
        default=False,
        help="Repeat the origin-language phrase after the translation with a short gap",
    )

    parser.add_argument(
        "--repetitions",
        type=int,
        default=None,
        help="How many times to repeat the origin phrase after the translation (overrides --repeat)",
    )

    parser.add_argument(
        "--origin-lang",
        type=str,
        default=None,
        help="Origin language code or name (default: en)",
    )

    parser.add_argument(
        "--target-lang",
        type=str,
        default=None,
        help="Target language code or name (default: fa)",
    )

    parser.add_argument(
        "--background-image",
        type=str,
        default=None,
        help="Path to a background image (default: animated waves)",
    )

    parser.add_argument(
        "--background-music",
        type=str,
        default=None,
        help="Path to background music (default: background-music.mp3)",
    )

    parser.add_argument(
        "--custom-phrases",
        type=str,
        default=None,
        help="Path to a JSON file containing a list of custom phrase pairs",
    )

    parser.add_argument(
        "--settings",
        type=str,
        default=None,
        help="Path to a JSON file with video settings overrides "
        "(merged over VIDEO_SETTINGS) plus an optional 'reverse_ratio'",
    )

    parser.add_argument(
        "--reverse-ratio",
        type=float,
        default=None,
        help="Fraction of segments shown in reverse order (e.g. 0.15)",
    )

    parser.add_argument(
        "--preview",
        action="store_true",
        default=False,
        help="Short real sample: one hard-coded phrase, real TTS audio, "
        "single pass — no LLM API call",
    )

    args = parser.parse_args()

    settings = {}
    reverse_ratio = args.reverse_ratio
    if args.settings:
        import json

        with open(args.settings, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("video_settings"), dict):
            settings = data["video_settings"]
        if reverse_ratio is None and isinstance(
            data.get("reverse_ratio"), (int, float)
        ):
            reverse_ratio = data["reverse_ratio"]

    preview_mode = args.preview
    if preview_mode:
        # Build a hard-coded, single-pair custom phrases file so no LLM call
        # is made, then force a one-pass assembly with no repeats/reversals.
        def _resolve_lang(value, default):
            if value and value in LANGUAGES:
                return value
            if value:
                lower = str(value).strip().lower()
                for code, cfg in LANGUAGES.items():
                    if cfg["name"].lower() == lower:
                        return code
            return default

        import json as _json

        p_origin = _resolve_lang(args.origin_lang, DEFAULT_ORIGIN_LANGUAGE)
        p_target = _resolve_lang(args.target_lang, DEFAULT_TARGET_LANGUAGE)
        preview_pairs_path = os.path.join(TEMP_DIR, "preview_phrases.json")
        content = PREVIEW_SAMPLE_PHRASES.get(p_origin, PREVIEW_FALLBACK)
        translation = PREVIEW_SAMPLE_PHRASES.get(p_target, PREVIEW_FALLBACK)
        with open(preview_pairs_path, "w", encoding="utf-8") as f:
            _json.dump(
                [{"origin": content, "target": translation}], f, ensure_ascii=False
            )
        args.custom_phrases = preview_pairs_path
        args.count = 1
        args.duration = -1
        # Keep the caller's --repetitions value so previews reflect repetition
        # settings. Only force it to 0 when the caller didn't specify one.
        if args.repetitions is None:
            args.repetitions = 0
        args.repeat = False
        reverse_ratio = 0.0
        print(
            "Preview mode: 1 hard-coded phrase, real TTS audio, single pass "
            "— no LLM API call."
        )

    pipeline = ContentPipeline(
        origin_language=args.origin_lang,
        target_language=args.target_lang,
        repetitions=args.repetitions,
        background_image=args.background_image,
        background_music=args.background_music,
        settings=settings,
        preview=preview_mode,
    )
    pipeline.run(
        topic=args.topic,
        count=args.count,
        output_filename=args.output,
        duration=args.duration,
        repeat_english=args.repeat,
        repetitions=args.repetitions,
        custom_phrases_file=args.custom_phrases,
        origin_language=args.origin_lang,
        target_language=args.target_lang,
        background_image=args.background_image,
        background_music=args.background_music,
        reverse_ratio=reverse_ratio,
    )


if __name__ == "__main__":
    main()
