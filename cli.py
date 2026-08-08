#!/usr/bin/env python3
"""
9-Minute English CLI - Interactive terminal interface for content generation.
Supports both interactive prompts and one-shot flag-based commands.
"""

import sys
import os
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import LANGUAGES, DEFAULT_ORIGIN_LANGUAGE, DEFAULT_TARGET_LANGUAGE


PRESETS = {
    "9min":  {"duration": 540,  "count": 40, "label": "9-Minute Full Video"},
    "6min":  {"duration": 360,  "count": 30, "label": "6-Minute Video"},
    "3min":  {"duration": 180,  "count": 20, "label": "3-Minute Short"},
    "1min":  {"duration": 60,   "count": 10, "label": "1-Minute Test"},
    "30s":   {"duration": 30,   "count": 5,  "label": "30-Second Quick Test"},
}

TOPICS = [
    "pivotal English phrases",
    "travel English phrases",
    "business English conversations",
    "emotional and romantic phrases",
    "everyday English slang",
    "job interview questions",
    "restaurant and food language",
    "emergency and safety phrases",
    "small talk and networking",
    "English proverbs and idioms",
]

LEVELS = {
    "A1": "beginner (A1 CEFR)",
    "A2": "elementary (A2 CEFR)",
    "B1": "intermediate (B1 CEFR)",
    "B2": "upper-intermediate (B2 CEFR)",
    "C1": "advanced (C1 CEFR)",
    "any": "any level",
}

PRESET_KEYS = list(PRESETS.keys())


def print_header():
    print()
    print("╔" + "═" * 52 + "╗")
    print("║     🎬  9-Minute English Content Generator   ║")
    print("╚" + "═" * 52 + "╝")
    print()


def select_preset():
    print("📏 Choose video length:")
    for i, key in enumerate(PRESET_KEYS, 1):
        p = PRESETS[key]
        print(f"  [{i}]  {p['label']}  ({p['duration']}s)")

    try:
        choice = input(f"\n  Enter number [1-{len(PRESET_KEYS)}] (default 3): ").strip()
        if not choice:
            choice = "3"
        idx = int(choice) - 1
        return PRESETS[PRESET_KEYS[idx]]
    except (ValueError, IndexError):
        return PRESETS["3min"]


def select_topic():
    print("\n📝 Choose phrase topic:")
    for i, t in enumerate(TOPICS, 1):
        print(f"  [{i}]  {t}")
    print(f"  [{len(TOPICS) + 1}]  Custom topic...")

    try:
        choice = input(f"\n  Enter number [1-{len(TOPICS) + 1}] (default 1): ").strip()
        if not choice:
            return TOPICS[0]
        idx = int(choice) - 1
        if idx == len(TOPICS):
            return input("  Enter custom topic: ").strip()
        return TOPICS[idx]
    except (ValueError, IndexError):
        return TOPICS[0]


def select_level():
    print("\n🎯 Choose English proficiency level (CEFR):")
    keys = list(LEVELS.keys())
    for i, key in enumerate(keys, 1):
        print(f"  [{i}]  {key} — {LEVELS[key]}")

    try:
        choice = input(f"\n  Enter number [1-{len(keys)}] (default 6 = any level): ").strip()
        if not choice:
            return "any level"
        idx = int(choice) - 1
        return LEVELS[keys[idx]]
    except (ValueError, IndexError):
        return "any level"


def resolve_language_code(value: str, default: str) -> str:
    """Resolve a language code from a code or a language name."""
    if not value:
        return default
    if value in LANGUAGES:
        return value
    lower = str(value).strip().lower()
    for code, cfg in LANGUAGES.items():
        if cfg["name"].lower() == lower:
            return code
    return default


def select_language(prompt: str, default_code: str) -> str:
    keys = list(LANGUAGES.keys())
    default_idx = keys.index(default_code) + 1 if default_code in keys else 1
    print(f"\n{prompt}")
    for i, code in enumerate(keys, 1):
        print(f"  [{i}]  {code} — {LANGUAGES[code]['name']}")
    try:
        choice = input(f"\n  Enter number [1-{len(keys)}] (default {default_idx}): ").strip()
        if not choice:
            return default_code
        idx = int(choice) - 1
        return keys[idx]
    except (ValueError, IndexError):
        return default_code


def select_repetitions() -> int:
    print("\n🔁 Phrase repetitions:")
    print("    [0]  Origin → Translation            (default)")
    print("    [1]  Origin → Translation → Origin again")
    print("    [2]  Origin → Translation → Origin ×2")
    try:
        choice = input("\n  Enter number [0-5] (default 0): ").strip()
        if not choice:
            return 0
        return max(0, min(int(choice), 5))
    except ValueError:
        return 0


def select_background():
    print("\n🖼️  Background (Enter to keep defaults):")
    bg_image = input("  Background image path (blank = animated waves): ").strip()
    bg_music = input("  Background music path (blank = background-music.mp3): ").strip()
    return (bg_image or None), (bg_music or None)


def select_settings():
    """Interactive settings menu. Returns a dict of optional feature flags."""
    print()
    print("┌" + "─" * 52 + "┐")
    print("│  ⚙️  Settings                                     │")
    print("└" + "─" * 52 + "┘")

    settings = {}
    reps = select_repetitions()
    settings["repeat_english"] = reps > 0
    settings["repetitions"] = reps

    return settings


def confirm(preset, topic, level, output_name, count, settings):
    print()
    print(f"📋 Summary:")
    print(f"  Duration: {preset['duration']}s ({preset['duration']/60:.1f} min)")
    print(f"  Topic:    {topic}")
    print(f"  Level:    {level}")
    print(f"  Phrases:  {count}")
    print(f"  Output:   output/{output_name}")
    reps = settings.get("repetitions", 0)
    if reps > 0:
        repeat_label = f"Origin → Translation → Origin ×{reps}"
    else:
        repeat_label = "Origin → Translation"
    print(f"  Repeat:   {repeat_label}")
    print()

    ans = input("🚀 Generate? [Y/n]: ").strip().lower()
    return ans != "n"


def build_parser():
    parser = argparse.ArgumentParser(
        description="Generate bilingual English-Persian language learning videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python cli.py                             Interactive mode\n"
            "  python cli.py -p 30s                      Quick 30s test, non-interactive\n"
            "  python cli.py -p 9min --repeat -y         9-min video with origin repeat\n"
            "  python cli.py --origin-lang en --target-lang es --repetitions 2\n"
            "  python cli.py --background-image bg.png --background-music track.mp3\n"
            "  python cli.py -d 120 -c 15 -t \"slang\"     Custom 120s video, 15 phrases\n"
            "  python cli.py --help                      This message\n"
        ),
    )

    parser.add_argument(
        "--preset", "-p",
        type=str,
        choices=list(PRESETS.keys()),
        default=None,
        help="Video length preset (9min, 6min, 3min, 1min, 30s)"
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=None,
        help="Custom duration in seconds (overrides --preset)"
    )
    parser.add_argument(
        "--count", "-c",
        type=int,
        default=None,
        help="Number of phrases to generate"
    )
    parser.add_argument(
        "--topic", "-t",
        type=str,
        default=None,
        help="Phrase topic (name or index 1-10)"
    )
    parser.add_argument(
        "--level", "-l",
        type=str,
        choices=list(LEVELS.keys()),
        default=None,
        help="CEFR proficiency level"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output filename"
    )
    parser.add_argument(
        "--repeat", "-r",
        action="store_true",
        default=None,
        help="Enable origin → translation → origin repeat mode (shorthand for --repetitions 1)"
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=None,
        help="How many times to repeat the origin phrase after the translation (0-5)"
    )
    parser.add_argument(
        "--origin-lang",
        type=str,
        default=None,
        help="Origin language code or name (default: en)"
    )
    parser.add_argument(
        "--target-lang",
        type=str,
        default=None,
        help="Target language code or name (default: fa)"
    )
    parser.add_argument(
        "--background-image",
        type=str,
        default=None,
        help="Path to a background image (default: animated waves)"
    )
    parser.add_argument(
        "--background-music",
        type=str,
        default=None,
        help="Path to background music (default: background-music.mp3)"
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        default=False,
        help="Skip confirmation prompt"
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        default=False,
        help="Suppress ASCII header (clean output for scripts)"
    )
    parser.add_argument(
        "--custom-phrases",
        type=str,
        default=None,
        help="Path to a JSON file containing a list of custom phrase pairs "
             "(objects with 'origin'/'target' or legacy 'english'/'persian' keys)"
    )

    return parser


def resolve_topic(topic_arg: str) -> str:
    """Resolve topic from a name string or a 1-based index."""
    try:
        idx = int(topic_arg) - 1
        if 0 <= idx < len(TOPICS):
            return TOPICS[idx]
    except ValueError:
        pass
    # treat as custom topic string
    return topic_arg


def run():
    args = build_parser().parse_args()
    has_flags = any([
        args.preset, args.duration is not None, args.count is not None,
        args.topic, args.level, args.output, args.repeat is not None,
        args.custom_phrases is not None, args.repetitions is not None,
        args.origin_lang, args.target_lang, args.background_image, args.background_music
    ])

    if has_flags:
        # ── Non-interactive mode ──────────────────────────────────────────
        if args.preset:
            preset = dict(PRESETS[args.preset])
        elif args.custom_phrases:
            preset = {"duration": -1, "count": "Custom"}
        else:
            preset = dict(PRESETS["3min"])
            
        if args.duration is not None:
            preset["duration"] = args.duration
        if args.count is not None:
            preset["count"] = args.count

        topic = resolve_topic(args.topic) if args.topic else TOPICS[0]
        level = LEVELS.get(args.level, "any level") if args.level else "any level"
        
        phrases_count = preset['count']
        if args.custom_phrases:
            topic = f"Custom (from {args.custom_phrases})"
            try:
                import json
                with open(args.custom_phrases, 'r', encoding='utf-8') as f:
                    phrases_count = len(json.load(f))
            except Exception:
                phrases_count = "Custom"
                
        output_name = args.output if args.output else "video_language.mp4"
        origin_code = resolve_language_code(args.origin_lang, DEFAULT_ORIGIN_LANGUAGE)
        target_code = resolve_language_code(args.target_lang, DEFAULT_TARGET_LANGUAGE)
        origin_name = LANGUAGES[origin_code]["name"]
        target_name = LANGUAGES[target_code]["name"]
        reps = args.repetitions if args.repetitions is not None else (1 if args.repeat else 0)
        reps = max(0, min(reps, 5))
        settings = {"repeat_english": reps > 0, "repetitions": reps}

        if not args.plain:
            print_header()

        duration_str = f"{preset['duration']}s ({preset['duration']/60:.1f} min)" if preset['duration'] != -1 else "Auto (1 pass)"

        print(f"  Duration: {duration_str}")
        print(f"  Topic:    {topic}")
        print(f"  Level:    {level}")
        print(f"  Phrases:  {phrases_count}")
        print(f"  Output:   output/{output_name}")
        print(f"  Languages: {origin_name} ({origin_code}) → {target_name} ({target_code})")
        print(f"  Repetitions: {reps}")
        if args.background_image:
            print(f"  Background image: {args.background_image}")
        if args.background_music:
            print(f"  Background music: {args.background_music}")
        print()

        if not args.yes:
            ans = input("🚀 Generate? [Y/n]: ").strip().lower()
            if ans == "n":
                print("👋 Cancelled.")
                return

        topic_with_level = f"{topic} ({level})"
        print("\n⚡ Launching pipeline...\n")

        from pipeline import ContentPipeline
        pipeline = ContentPipeline(
            origin_language=origin_code,
            target_language=target_code,
            repetitions=reps if args.repetitions is not None else None,
            background_image=args.background_image,
            background_music=args.background_music,
        )
        pipeline.run(
            topic=topic_with_level,
            count=preset["count"],
            output_filename=output_name,
            duration=preset["duration"],
            repeat_english=settings["repeat_english"],
            repetitions=settings["repetitions"],
            custom_phrases_file=args.custom_phrases,
            origin_language=origin_code,
            target_language=target_code,
            background_image=args.background_image,
            background_music=args.background_music,
        )
    else:
        # ── Interactive mode ──────────────────────────────────────────────
        print_header()
        preset = select_preset()
        origin_code = select_language("🌍 Choose origin language (phrases are spoken in this language):", DEFAULT_ORIGIN_LANGUAGE)
        target_code = select_language("🌐 Choose translation language:", DEFAULT_TARGET_LANGUAGE)
        settings = select_settings()
        topic = select_topic()
        level = select_level()

        output_name = input("\n📁 Output filename (default: video_language.mp4): ").strip()
        if not output_name:
            output_name = "video_language.mp4"

        bg_image, bg_music = select_background()

        topic_with_level = f"{topic} ({level})"

        if not confirm(preset, topic, level, output_name, preset["count"], settings):
            print("\n👋 Cancelled.")
            return

        print("\n⚡ Launching pipeline...\n")

        from pipeline import ContentPipeline
        pipeline = ContentPipeline(
            origin_language=origin_code,
            target_language=target_code,
            repetitions=settings.get("repetitions"),
            background_image=bg_image,
            background_music=bg_music,
        )
        pipeline.run(
            topic=topic_with_level,
            count=preset["count"],
            output_filename=output_name,
            duration=preset["duration"],
            repeat_english=settings.get("repeat_english", False),
            repetitions=settings.get("repetitions"),
            custom_phrases_file=args.custom_phrases,
            origin_language=origin_code,
            target_language=target_code,
            background_image=bg_image,
            background_music=bg_music,
        )


if __name__ == "__main__":
    run()
