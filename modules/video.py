import os
import math
import subprocess
import textwrap
from typing import List, Dict
from PIL import Image, ImageDraw, ImageFont


class VideoMuxer:
    """Handles high-performance video generation with animated wave backgrounds and smooth transitions using FFmpeg pipes."""
    
    def __init__(self):
        self.output_dir = "/Users/tripasect/Development/9-minute-english/output"
        self.temp_dir = "/Users/tripasect/Development/9-minute-english/temp"
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        
    def get_audio_duration(self, file_path: str) -> float:
        """Get the duration of an audio file using ffprobe."""
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            return 3.0  # Fallback duration for missing/empty audio
            
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", file_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"  [Warning] Failed to get duration for {file_path}: {e}")
            return 3.0

    def draw_calming_waves(self, draw: ImageDraw.Draw, current_frame_global: int, total_frames_global: int):
        """Draws two overlapping, beautiful, and slowly moving waves at the bottom of the canvas."""
        # Wave 1 (Deep Indigo-Blue, translucent)
        points1 = []
        # Use total_frames_global to ensure phase smoothly transitions across clips
        # We want the wave to complete a cycle (e.g., 4 full cycles) over the entire video duration
        wave_cycles_global = 4 # How many times the wave repeats its pattern over the entire video
        phase1 = (current_frame_global / total_frames_global) * 2 * math.pi * wave_cycles_global

        for x in range(0, 1921, 20):
            y = 880 + 35 * math.sin(0.003 * x + phase1)
            points1.append((x, int(y)))
        points1.append((1920, 1080))
        points1.append((0, 1080))
        
        # Wave 2 (Lighter Teal-Blue, translucent, moving in opposition)
        points2 = []
        wave_cycles_global_2 = 3.5 # Slightly different cycle for the second wave
        phase2 = (current_frame_global / total_frames_global) * 2 * math.pi * wave_cycles_global_2 + 1.5 # Offset phase

        for x in range(0, 1921, 20):
            y = 910 + 25 * math.sin(0.004 * x + phase2)
            points2.append((x, int(y)))
        points2.append((1920, 1080))
        points2.append((0, 1080))

        # Draw waves (order: back wave then front wave)
        draw.polygon(points1, fill=(30, 40, 60))
        draw.polygon(points2, fill=(36, 50, 75))

    def create_frame_image_in_memory(
        self,
        primary_text: str,
        secondary_text: str,
        primary_lang: str,
        secondary_lang: str,
        frame_idx_in_clip: int,
        total_frames_in_clip: int,
        audio_duration_frames: int,
        current_frame_global: int,
        total_frames_global: int,
        keep_text_visible: bool = False
    ) -> Image.Image:
        """Generates a single frame with text (fades in/out at clip edges) and moving waves background."""
        bg_color = (10, 11, 16)
        img = Image.new("RGBA", (1920, 1080), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        # Draw the dynamic soothing waves first (full opacity) using global frame info
        self.draw_calming_waves(draw, current_frame_global, total_frames_global)
        
        # Draw watermark (avatar PNG) in southeast corner, 3x bigger.
        margin = 40
        avatar_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "watermark.png")
        if os.path.exists(avatar_path):
            try:
                avatar = Image.open(avatar_path).convert("RGBA")
                avatar.thumbnail((125, 125))
                img.paste(avatar, (1920 - margin - avatar.width, 1080 - margin - avatar.height), avatar)
            except Exception:
                pass
        
        # Draw channel handle in bottom-left corner
        try:
            handle_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 22)
        except Exception:
            handle_font = ImageFont.load_default()
        draw.text((margin, 1080 - margin), "YouTube.com/@9ineMinuteEnglish", fill=(180, 180, 180, 120), font=handle_font, anchor="ld")
        
        # Text fades in over the first 0.5s, then stays fully visible for the entire clip.
        fade_duration_frames = 12  # ~0.5 second fade-in
        
        if frame_idx_in_clip < fade_duration_frames:
            alpha = int(255 * (frame_idx_in_clip / fade_duration_frames))
        else:
            alpha = 255
            
        # Load premium system fonts
        font_name_en = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        font_name_fa = "/System/Library/Fonts/SFArabic.ttf"
        
        try:
            font_title_en = ImageFont.truetype(font_name_en, 68)   # 54 * 1.25 ≈ 68
            font_sub_en = ImageFont.truetype(font_name_en, 53)     # 42 * 1.25 ≈ 53
        except Exception:
            font_title_en = ImageFont.load_default()
            font_sub_en = ImageFont.load_default()

        try:
            font_title_fa = ImageFont.truetype(font_name_fa, 88)   # 50 * 1.75 ≈ 88
            font_sub_fa = ImageFont.truetype(font_name_fa, 70)     # 40 * 1.75 ≈ 70
        except Exception:
            font_title_fa = ImageFont.load_default()
            font_sub_fa = ImageFont.load_default()

        # Text wrap and RTL shape helper (wrapping BEFORE shaping to preserve letter context)
        def prepare_text_lines(text: str, lang: str) -> List[str]:
            if not text:
                return []
            # Width should be adjusted for font size and character density
            wrap_width = 35 if lang == "fa" else 42
            return textwrap.wrap(text, width=wrap_width)

        # Map to correct fonts and wrap lines
        font_primary = font_title_fa if primary_lang == "fa" else font_title_en
        font_secondary = font_sub_fa if secondary_lang == "fa" else font_sub_en
        
        primary_lines = prepare_text_lines(primary_text, primary_lang)
        secondary_lines = prepare_text_lines(secondary_text, secondary_lang)

        # Colors with alpha for fading
        color_white = (245, 245, 247, alpha)
        color_gold = (120, 180, 255, alpha)  # Light blue for Persian
        
        # Calculate total text block height
        line_height_primary = 85
        line_height_secondary = 65
        gap = 30
        
        total_height = len(primary_lines) * line_height_primary
        if secondary_lines:
            total_height += gap + len(secondary_lines) * line_height_secondary
            
        start_y = (1000 - total_height) // 2

        # Draw primary text lines with perfect centering and native RTL support
        y = start_y
        for line in primary_lines:
            dir_str = "rtl" if primary_lang == "fa" else "ltr"
            bbox = draw.textbbox((0, 0), line, font=font_primary, direction=dir_str)
            text_width = bbox[2] - bbox[0]
            x = (1920 - text_width) // 2
            draw.text(
                (x, y), line, fill=color_white, font=font_primary,
                direction=dir_str
            )
            y += line_height_primary

        # Draw secondary text lines
        if secondary_lines:
            y += gap
            for line in secondary_lines:
                dir_str = "rtl" if secondary_lang == "fa" else "ltr"
                bbox = draw.textbbox((0, 0), line, font=font_secondary, direction=dir_str)
                text_width = bbox[2] - bbox[0]
                x = (1920 - text_width) // 2
                draw.text(
                    (x, y), line, fill=color_gold, font=font_secondary,
                    direction=dir_str
                )
                y += line_height_secondary

        return img.convert("RGB") # FFmpeg expects RGB for rawvideo input

    def create_video_clip(
        self,
        primary_text: str,
        secondary_text: str,
        primary_lang: str,
        secondary_lang: str,
        audio_path: str,
        total_duration: float,
        output_path: str,
        current_frame_global_offset: int,
        total_frames_global: int,
        keep_text_visible: bool = False
    ) -> bool:
        """
        Creates a high-quality video clip using FFmpeg stdin pipe without deadlocks.
        Text remains on screen for the entire clip duration, fading in at the start
        and fading out at the end while the wave keeps looping.
        """
        fps = 25
        total_frames_in_clip = int(total_duration * fps)
        audio_dur = self.get_audio_duration(audio_path)
        audio_duration_frames = int(audio_dur * fps)

        use_silent_audio = not (os.path.exists(audio_path) and os.path.getsize(audio_path) > 0)
        
        if use_silent_audio:
            print(f"  [Warning] Audio file {audio_path} is missing or empty, using silent audio.")
            audio_source_cmd = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono"]
            audio_map = "-map", "1:a"
            filter_complex_str = ""
        else:
            audio_source_cmd = ["-i", audio_path]
            audio_map = "-map", "[outa]"
            fade_dur = 0.05
            fade_out_start = max(0.0, total_duration - fade_dur)
            filter_complex_str = f"[1:a]apad,aresample=44100,afade=t=in:st=0:d={fade_dur},afade=t=out:st={fade_out_start:.3f}:d={fade_dur}[outa]"

        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", "25",
            "-i", "-",
            *audio_source_cmd,
            *([ "-filter_complex", filter_complex_str ] if filter_complex_str else []),
            "-map", "0:v", *audio_map,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "pcm_s16le", "-ar", "44100",
            "-pix_fmt", "yuv420p",
            "-t", f"{total_duration:.2f}", # Use -t for duration instead of -shortest
            output_path
        ]
        
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Write frames directly to pipe
            for f_idx_in_clip in range(total_frames_in_clip):
                current_frame_global = current_frame_global_offset + f_idx_in_clip
                img = self.create_frame_image_in_memory(
                    primary_text, secondary_text, primary_lang, secondary_lang,
                    f_idx_in_clip, total_frames_in_clip, audio_duration_frames,
                    current_frame_global, total_frames_global,
                    keep_text_visible=keep_text_visible
                )
                try:
                    process.stdin.write(img.tobytes())
                except BrokenPipeError:
                    print(f"  [Warning] Broken pipe detected during frame write. FFmpeg process might have terminated early.")
                    break # Exit loop if pipe is broken
                
            process.stdin.close()
            process.wait()
            return process.returncode == 0
        except Exception as e:
            print(f"  [Error] Failed to pipe video clip: {e}")
            return False

    def create_silence_clip(self, duration: float, output_path: str,
                            current_frame_global_offset: int, total_frames_global: int) -> bool:
        """
        Creates a smooth transitions/silence gap clip with slowly moving waves and absolute silence.
        No text or text fading is applied.
        """
        fps = 25
        total_frames_in_clip = int(duration * fps)
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", "25",
            "-i", "-",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "pcm_s16le", "-ar", "44100",
            "-pix_fmt", "yuv420p",
            "-t", f"{duration:.2f}",
            output_path
        ]
        
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Write frames, passing global frame info for continuous wave animation
            for f_idx_in_clip in range(total_frames_in_clip):
                current_frame_global = current_frame_global_offset + f_idx_in_clip
                img = self.create_frame_image_in_memory("", "", "en", "fa",
                                                        f_idx_in_clip, total_frames_in_clip, 0,
                                                        current_frame_global, total_frames_global)
                process.stdin.write(img.tobytes())
                
            process.stdin.close()
            process.wait()
            return process.returncode == 0
        except Exception as e:
            print(f"  [Error] Failed to create silence clip: {e}")
            return False

    def _get_duration(self, file_path: str) -> float:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", file_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def assemble_final_video(
        self,
        clip_paths: List[str],
        ambient_audio: str = None,
        output_filename: str = "final_video.mp4"
    ) -> str:
        """
        Concatenates all clip files using the ultra-fast copy demuxer,
        then re-encodes audio to apply global fade-in/out.
        """
        # When concatenating MP3/AAC via concat demuxer, audio pops can happen.
        # It's better to re-encode the audio streams together without 'copy' demuxing them, 
        # but since we already rendered them as AAC into the final clips, we can apply an 
        # aresample filter or crossfade to fix the glitches. But the simplest way is 
        # to ensure the individual clip generation properly padded the audio and encoded it perfectly.
        # Actually, let's just make sure the audio in create_clip is padded by 0.05 on the afade.
        concat_list_path = os.path.join(self.temp_dir, "concat_list.txt")
        temp_merged_video = os.path.join(self.temp_dir, "merged_temp.mp4")
        final_output_path = os.path.join(self.output_dir, output_filename)

        with open(concat_list_path, "w") as f:
            for path in clip_paths:
                escaped_path = path.replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")

        print(f"  [Muxer] Concatenating {len(clip_paths)} clips...")
        
        # We re-encode audio here instead of copy, to prevent STT pops between clips.
        # The copy demuxer is fine for video since we used same codec/params.
        # Actually since we set -ar 44100 on all clips uniformly, maybe concat works better?
        # A safer option to eliminate pop is re-encoding audio with a tiny crossfade or simply re-encoding.
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list_path,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            temp_merged_video
        ]
        
        try:
            subprocess.run(concat_cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"  [Error] FFmpeg concat failed: {e.stderr}")
            raise RuntimeError(f"FFmpeg concat failed: {e.stderr}")

        total_dur = self._get_duration(temp_merged_video)
        fade_dur = 1.0
        fade_out_start = max(total_dur - fade_dur, 0)

        has_ambient = ambient_audio and os.path.exists(ambient_audio)

        if has_ambient:
            print(f"  [Muxer] Mixing ambient audio: {ambient_audio}...")
            filter_complex = (
                f"[0:a]afade=t=in:st=0:d={fade_dur},"
                f"afade=t=out:st={fade_out_start:.2f}:d={fade_dur}[speech];"
                f"[1:a]volume=0.3[bg];"
                f"[speech][bg]amix=inputs=2:duration=first:dropout_transition=0.5[outa]"
            )
            inputs = ["-i", temp_merged_video, "-stream_loop", "-1", "-i", ambient_audio]
        else:
            print(f"  [Muxer] Applying global audio fade-in/out...")
            filter_complex = (
                f"[0:a]afade=t=in:st=0:d={fade_dur},"
                f"afade=t=out:st={fade_out_start:.2f}:d={fade_dur}[outa]"
            )
            inputs = ["-i", temp_merged_video]

        mix_cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[outa]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            final_output_path
        ]
        try:
            subprocess.run(mix_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            print(f"  [Muxer] Completed final video with global fade-in/out.")
            return final_output_path
        except subprocess.CalledProcessError as e:
            print(f"  [Warning] Audio re-encode with fades failed: {e.stderr}")
            if os.path.exists(temp_merged_video):
                if os.path.exists(final_output_path):
                    os.remove(final_output_path)
                os.rename(temp_merged_video, final_output_path)
            return final_output_path
