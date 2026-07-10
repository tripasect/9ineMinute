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

import os
import sys
import random
import concurrent.futures
from typing import List, Dict

# Add modules to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import VIDEO_SETTINGS, REVERSE_RATIO, OUTPUT_DIR, TEMP_DIR, OPENROUTER_API_KEY
from modules.translator import PhraseTranslator
from modules.reverse import ReverseTranslator
from modules.audio import AudioGenerator
from modules.video import VideoMuxer


class ContentPipeline:
    """Main orchestrator for the video generation pipeline."""
    
    def __init__(self):
        self.phrase_translator = PhraseTranslator(api_key=OPENROUTER_API_KEY)
        self.reverse_gen = ReverseTranslator()
        self.audio_gen = AudioGenerator(TEMP_DIR)
        self.video_muxer = VideoMuxer()
    
    def run(
        self,
        topic: str = "common English phrases",
        count: int = 30,
        output_filename: str = None,
        duration: int = None,
        repeat_english: bool = False,
        custom_phrases_file: str = None,
    ) -> str:
        """
        Run the complete pipeline from phrase generation to final video.
        
        Args:
            topic: Topic for phrase generation
            count: Number of phrases to generate
            output_filename: Custom output filename
            duration: Override target video duration in seconds
            repeat_english: When True, repeat the English phrase after the
                Persian translation with a shorter gap (English → Persian →
                English again). Applies only to normal (non-reverse) segments.
        
        Returns:
            Path to generated video file
        """
        print("=" * 60)
        print("          9-Minute English Content Pipeline")
        print("=" * 60)
        
        # Step 1: Generate English phrases + Persian translations in one LLM call
        if custom_phrases_file:
            print(f"\n[1/5] Loading custom phrases and translations from {custom_phrases_file}...")
            import json
            with open(custom_phrases_file, 'r', encoding='utf-8') as f:
                pairs = json.load(f)
                
            if not isinstance(pairs, list) or not all(isinstance(p, dict) and "english" in p and "persian" in p for p in pairs):
                print("  [Error] Custom phrases file must be a JSON array of objects with 'english' and 'persian' keys.")
                sys.exit(1)
                
            phrases = [p["english"] for p in pairs]
            persian_translations = [p["persian"] for p in pairs]
            print(f"  Loaded {len(phrases)} custom phrase+translation pairs (LLM bypassed).")
        else:
            print("\n[1/5] Generating phrases and translations (unified call)...")
            pairs = self.phrase_translator.generate_and_translate(topic=topic, count=count)
            if not pairs:
                print("  [Error] No phrase pairs generated.")
                sys.exit(1)
            phrases = [p["english"] for p in pairs]
            persian_translations = [p["persian"] for p in pairs]
            print(f"  Generated {len(phrases)} phrase+translation pairs.")

        # Step 2 is now merged into Step 1 — kept as a no-op label for clarity
        print("\n[2/5] Translations ready (included in unified call).")
        
        # Step 3: Create segments (Normal / Reverse 15%)
        print("\n[3/5] Creating translation segments...")
        segments = self.reverse_gen.generate_reverse_segments(
            phrases, persian_translations
        )
        reverse_count = sum(1 for s in segments if s["type"] == "reverse")
        print(f"  Total segments: {len(segments)}")
        print(f"  Reverse segments (15%): {reverse_count}")
        
        # Step 4: Generate unique TTS audio files and cache them
        print("\n[4/5] Generating unique TTS audio files in parallel...")
        unique_audio_cache = {}
        audio_tasks = []
        
        for i, segment in enumerate(segments):
            # Normal segment: slide 1 is English (en), slide 2 is Persian (fa)
            # Reverse segment: slide 1 is Persian (fa), slide 2 is English (en)
            normal_or_reverse = segment["type"]
            
            # Generate English audio
            en_text = segment["translation"] if normal_or_reverse == "reverse" else segment["content"]
            en_audio_path = os.path.join(TEMP_DIR, f"audio_en_{i}.mp3")
            if en_text not in unique_audio_cache:
                unique_audio_cache[en_text] = en_audio_path
                audio_tasks.append((en_text, "en", en_audio_path))
                
            # Generate Persian audio
            fa_text = segment["content"] if normal_or_reverse == "reverse" else segment["translation"]
            fa_audio_path = os.path.join(TEMP_DIR, f"audio_fa_{i}.mp3")
            if fa_text not in unique_audio_cache:
                unique_audio_cache[fa_text] = fa_audio_path
                audio_tasks.append((fa_text, "fa", fa_audio_path))
                
            segment["audio_en"] = unique_audio_cache[en_text]
            segment["audio_fa"] = unique_audio_cache[fa_text]

        if audio_tasks:
            print(f"  Launching {len(audio_tasks)} audio generation tasks...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = []
                for text, lang, path in audio_tasks:
                    futures.append(executor.submit(self.audio_gen.generate_audio, text, lang, path))
                
                # Wait for all to complete and check for exceptions
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        print(f"  [Error] Audio generation task failed: {e}")

        # Step 5: Build up clips to hit target duration
        if duration == -1:
            target_duration = float('inf')
            loop_once = True
        else:
            target_duration = duration if duration is not None else VIDEO_SETTINGS.get("duration_seconds", 540)
            loop_once = False
            
        print(f"\n[5/5] Building clips & looping to reach target of {'Auto (1 pass)' if loop_once else str(target_duration) + 's'}...")
        
        clip_paths = []
        current_duration = 0.0
        current_frame_global_offset = 0 # Track total frames processed
        fps = 25 # Frames per second for video generation
        
        # Estimate total frames for the entire video (used for consistent wave animation)
        # This needs to be a reasonable upper bound for accurate wave phase calculation
        if target_duration == float('inf'):
            estimated_total_frames_global = 3600 * fps  # 1 hour upper bound for Auto mode
        else:
            estimated_total_frames_global = int(target_duration * fps * 1.5) # 1.5x buffer

        pause_after_tts = VIDEO_SETTINGS.get("pause_duration", 2.5)
        repeat_pause = VIDEO_SETTINGS.get("repeat_pause_duration", 0.0)
        gap_dur = VIDEO_SETTINGS.get("phrase_gap_duration", 3.0)
        
        loop_count = 0
        while current_duration < target_duration:
            loop_count += 1
            print(f"  --- Running Loop #{loop_count} (Current total: {current_duration:.1f}s) ---")
            
            # Shuffle segments on subsequent loops to keep order dynamic
            current_loop_segments = list(segments)
            if loop_count > 1:
                random.shuffle(current_loop_segments)
                
            for i, segment in enumerate(current_loop_segments):
                if current_duration >= target_duration:
                    break
                
                print(f"    [Segment {i+1:02d}/{len(current_loop_segments)}] Generating clips (Current total: {current_duration:.1f}s)...", flush=True)
                    
                seg_id = f"loop{loop_count}_seg{i}"
                is_reverse = segment["type"] == "reverse"
                
                # Slide 1 and Slide 2 details
                if not is_reverse:
                    # Slide 1: English Only
                    txt_1, txt_2_1, lang_1, lang_2_1 = segment["content"], "", "en", "fa"
                    audio_1 = segment["audio_en"]
                    
                    # Slide 2: English + Persian
                    txt_2, txt_2_2, lang_2, lang_2_2 = segment["content"], segment["translation"], "en", "fa"
                    audio_2 = segment["audio_fa"]
                else:
                    # Slide 1: Persian Only
                    txt_1, txt_2_1, lang_1, lang_2_1 = segment["content"], "", "fa", "en"
                    audio_1 = segment["audio_fa"]
                    
                    # Slide 2: Persian + English
                    txt_2, txt_2_2, lang_2, lang_2_2 = segment["content"], segment["translation"], "fa", "en"
                    audio_2 = segment["audio_en"]
                
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
                    total_frames_global=estimated_total_frames_global
                )
                if success_1:
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
                    total_frames_global=estimated_total_frames_global
                )
                if success_2:
                    clip_paths.append(clip_path_2)
                    current_duration += dur_2
                    current_frame_global_offset += int(dur_2 * fps)

                # Optional Clip 3: repeat English phrase with short pause
                # Only applies to normal (non-reverse) segments.
                if repeat_english and not is_reverse:
                    clip_path_3 = os.path.join(TEMP_DIR, f"clip_{seg_id}_s3.mov")
                    dur_3 = self.video_muxer.get_audio_duration(audio_1) + repeat_pause
                    success_3 = self.video_muxer.create_video_clip(
                        primary_text=txt_1,
                        secondary_text=txt_2_2,   # keep Persian visible below
                        primary_lang=lang_1,
                        secondary_lang=lang_2_2,
                        audio_path=audio_1,
                        total_duration=dur_3,
                        output_path=clip_path_3,
                        current_frame_global_offset=current_frame_global_offset,
                        total_frames_global=estimated_total_frames_global,
                        keep_text_visible=True       # keep text on screen for the repeat
                    )
                    if success_3:
                        clip_paths.append(clip_path_3)
                        current_duration += dur_3
                        current_frame_global_offset += int(dur_3 * fps)

                    
                # Generate Phrase Gap Clip (silence pause between phrases)
                success_gap = self.video_muxer.create_silence_clip(
                    gap_dur, gap_clip_path,
                    current_frame_global_offset=current_frame_global_offset,
                    total_frames_global=estimated_total_frames_global
                )
                if success_gap:
                    clip_paths.append(gap_clip_path)
                    current_duration += gap_dur
                    current_frame_global_offset += int(gap_dur * fps)
            
            # Safeguard to prevent infinite loops if no clips are generated
            if not clip_paths and loop_count > 1:
                print("  [Error] No new video clips were successfully generated in this loop. Exiting to prevent infinite loop.")
                sys.exit(1)
                
            if loop_once:
                break

        # Assemble the final video
        print(f"\n[Assembly] Assembling final video from {len(clip_paths)} clips (Total: {current_duration:.1f}s)...")
        bg_audio = self._get_background_audio()
        
        if output_filename is None:
            output_filename = "9_minute_english_persian.mp4"
            
        final_video_path = self.video_muxer.assemble_final_video(
            clip_paths=clip_paths,
            ambient_audio=bg_audio,
            output_filename=output_filename
        )
        
        print(f"\n{'=' * 60}")
        print("🎉 Video generated successfully!")
        print(f"🎬 Location: {final_video_path}")
        print(f"⏱️  Duration: {current_duration:.1f}s ({current_duration/60:.1f} mins)")
        print(f"{'=' * 60}")
        
        return final_video_path
    
    def _get_background_audio(self) -> str:
        """Get background ambient audio file path if configured."""
        bg_audio = VIDEO_SETTINGS.get("background_audio", "background-music.mp3")
        if os.path.exists(bg_audio):
            return bg_audio
        # Support relative path to modules directory as well
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
        "--topic", "-t",
        type=str,
        default="pivotal English phrases",
        help="Topic for phrase generation"
    )
    parser.add_argument(
        "--count", "-c",
        type=int,
        default=30,
        help="Number of unique phrases to generate (cached and looped to hit 9 minutes)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Custom output filename"
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=None,
        help="Target video duration in seconds (defaults to 540 / 9 minutes)"
    )
    
    parser.add_argument(
        "--repeat", "-r",
        action="store_true",
        default=False,
        help="Repeat the English phrase after the Persian translation with a short gap"
    )
    
    parser.add_argument(
        "--custom-phrases",
        type=str,
        default=None,
        help="Path to a JSON file containing a list of custom English phrases"
    )
    
    args = parser.parse_args()
    
    pipeline = ContentPipeline()
    pipeline.run(
        topic=args.topic,
        count=args.count,
        output_filename=args.output,
        duration=args.duration,
        repeat_english=args.repeat,
        custom_phrases_file=args.custom_phrases,
    )


if __name__ == "__main__":
    main()
