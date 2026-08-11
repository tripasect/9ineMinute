import math
import os
import subprocess
import sys
import textwrap
from typing import Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

# Windows-specific flag to suppress console windows
if sys.platform == "win32":
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    CREATE_NO_WINDOW = 0

from config import BASE_DIR, LANGUAGES, OUTPUT_DIR, TEMP_DIR, VIDEO_SETTINGS
from runtime import bundle_dir, resolve_binary


class VideoMuxer:
    """Handles high-performance video generation with animated wave backgrounds and smooth transitions using FFmpeg pipes."""

    def __init__(self, settings: dict = None):
        merged = dict(VIDEO_SETTINGS)
        if settings:
            merged.update(settings)
        self.settings = merged
        self.output_dir = merged.get("output_dir", OUTPUT_DIR)
        self.temp_dir = merged.get("temp_dir", TEMP_DIR)
        self.width = int(merged.get("width", 1920))
        self.height = int(merged.get("height", 1080))
        self.fps = int(merged.get("fps", 25))
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

        # Preload background image and watermark once (if configured)
        self._background_image = self._load_background_image(
            merged.get("background_image")
        )
        self._watermark = self._load_watermark(merged.get("watermark"))
        self._channel_handle = merged.get(
            "channel_handle", "YouTube.com/@9ineMinuteEnglish"
        )

    def update_settings(self, settings: dict):
        """Merge new settings at runtime and reload any affected assets."""
        self.settings.update(settings)
        if "width" in settings or "height" in settings:
            self.width = int(self.settings.get("width", 1920))
            self.height = int(self.settings.get("height", 1080))
        if "fps" in settings:
            self.fps = int(self.settings.get("fps", 25))
        if (
            "background_image" in settings
            or "width" in settings
            or "height" in settings
        ):
            self._background_image = self._load_background_image(
                self.settings.get("background_image")
            )
        if "watermark" in settings:
            self._watermark = self._load_watermark(self.settings.get("watermark"))
        if "channel_handle" in settings:
            self._channel_handle = self.settings.get("channel_handle")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_path(self, path) -> Optional[str]:
        if not path:
            return None
        if os.path.exists(path):
            return path
        abs_path = os.path.join(BASE_DIR, path)
        if os.path.exists(abs_path):
            return abs_path
        # Bundled default assets (watermark.png, background-music.mp3) live
        # in the read-only bundle directory in frozen builds, not BASE_DIR
        # (which is a writable per-user app-data directory there).
        bundled_path = os.path.join(bundle_dir(), os.path.basename(path))
        return bundled_path if os.path.exists(bundled_path) else None

    def _load_background_image(self, path) -> Optional[Image.Image]:
        resolved = self._resolve_path(path)
        if not resolved:
            return None
        try:
            img = Image.open(resolved).convert("RGB")
            return img.resize((self.width, self.height), Image.LANCZOS)
        except Exception as e:
            print(f"  [Warning] Failed to load background image {resolved}: {e}")
            return None

    def _load_watermark(self, path) -> Optional[Image.Image]:
        resolved = self._resolve_path(path)
        if not resolved:
            return None
        try:
            img = Image.open(resolved).convert("RGBA")
            img.thumbnail((125, 125))
            return img
        except Exception as e:
            print(f"  [Warning] Failed to load watermark {resolved}: {e}")
            return None

    def _resolve_font(self, lang_code: str, size: int):
        cfg = LANGUAGES.get(lang_code, {})
        candidates = [cfg.get("font")] if cfg.get("font") else []
        if sys.platform == "win32":
            # Tahoma ships with supported Windows releases and covers Arabic
            # and Persian. It is the primary cross-platform fallback when
            # the macOS-specific paths in LANGUAGES are unavailable.
            candidates += [
                r"C:\\Windows\\Fonts\\tahoma.ttf",
                r"C:\\Windows\\Fonts\\segoeui.ttf",
                r"C:\\Windows\\Fonts\\arial.ttf",
            ]
        elif sys.platform == "darwin":
            candidates += [
                "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            ]
        else:
            candidates += [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
            ]
        for path in candidates:
            if not path:
                continue
            # Configured bundled assets are extracted into bundle_dir() in
            # PyInstaller onefile builds; a relative filename is therefore
            # resolved there after direct/absolute candidates.
            resolved = path
            if not os.path.exists(resolved) and not os.path.isabs(path):
                bundled = os.path.join(bundle_dir(), path)
                if os.path.exists(bundled):
                    resolved = bundled
            if os.path.exists(resolved):
                try:
                    return ImageFont.truetype(resolved, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def get_audio_duration(self, file_path: str) -> float:
        """Get the duration of an audio file using ffprobe."""
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            return 3.0  # Fallback duration for missing/empty audio

        cmd = [
            resolve_binary("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, creationflags=CREATE_NO_WINDOW
            )
            return float(result.stdout.strip())
        except Exception as e:
            print(f"  [Warning] Failed to get duration for {file_path}: {e}")
            return 3.0

    def draw_calming_waves(
        self, draw: ImageDraw.Draw, current_frame_global: int, total_frames_global: int
    ):
        """Draws two overlapping, beautiful, and slowly moving waves at the bottom of the canvas."""
        wave_colors = self.settings.get("wave_colors", [(30, 40, 60), (36, 50, 75)])
        w, h = self.width, self.height
        safe_total = max(total_frames_global, 1)

        # Wave 1 (Deep Indigo-Blue, translucent)
        points1 = []
        wave_cycles_global = (
            12  # How many times the wave repeats its pattern over the entire video
        )
        phase1 = (current_frame_global / safe_total) * 2 * math.pi * wave_cycles_global

        for x in range(0, w + 1, 20):
            y = (h - 200) + 35 * math.sin(0.003 * (w / 1920) * x + phase1)
            points1.append((x, int(y)))
        points1.append((w, h))
        points1.append((0, h))

        # Wave 2 (Lighter Teal-Blue, translucent, moving in opposition)
        points2 = []
        wave_cycles_global_2 = 3.5  # Slightly different cycle for the second wave
        phase2 = (
            current_frame_global / safe_total
        ) * 2 * math.pi * wave_cycles_global_2 + 1.5  # Offset phase

        for x in range(0, w + 1, 20):
            y = (h - 170) + 25 * math.sin(0.004 * (w / 1920) * x + phase2)
            points2.append((x, int(y)))
        points2.append((w, h))
        points2.append((0, h))

        # Draw waves (order: back wave then front wave)
        draw.polygon(points1, fill=wave_colors[0])
        draw.polygon(points2, fill=wave_colors[1])

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
        keep_text_visible: bool = False,
    ) -> Image.Image:
        """Generates a single frame with text (fades in at clip edges) and moving waves or a background image."""
        bg_color = self.settings.get("background_color", (10, 11, 16))
        w, h = self.width, self.height
        img = Image.new("RGBA", (w, h), color=bg_color)
        draw = ImageDraw.Draw(img)

        # Background: either a preloaded image or animated calming waves
        if self._background_image is not None:
            img.paste(self._background_image, (0, 0))
            draw = ImageDraw.Draw(img)
        else:
            self.draw_calming_waves(draw, current_frame_global, total_frames_global)

        # Draw watermark in the southeast corner
        margin = 40
        if self._watermark is not None:
            img.paste(
                self._watermark,
                (
                    w - margin - self._watermark.width,
                    h - margin - self._watermark.height,
                ),
                self._watermark,
            )

        # Draw channel handle in the bottom-left corner
        try:
            handle_font = ImageFont.truetype(
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                max(16, int(22 * h / 1080)),
            )
        except Exception:
            handle_font = ImageFont.load_default()
        draw.text(
            (margin, h - margin),
            self._channel_handle,
            fill=(180, 180, 180, 120),
            font=handle_font,
            anchor="ld",
        )

        # Text fades in over the first `fade_duration` seconds
        fade_duration_frames = max(
            1, int(self.fps * self.settings.get("fade_duration", 0.5))
        )
        if frame_idx_in_clip < fade_duration_frames:
            alpha = int(255 * (frame_idx_in_clip / fade_duration_frames))
        else:
            alpha = 255

        scale = h / 1080.0

        def _font_size(lang: str, rtl_size: int, ltr_size: int) -> int:
            is_rtl = LANGUAGES.get(lang, {}).get("direction") == "rtl"
            return int((rtl_size if is_rtl else ltr_size) * scale)

        # Text wrap helper (wrapping BEFORE shaping preserves letter context)
        def prepare_text_lines(text: str, lang: str) -> List[str]:
            if not text:
                return []
            is_rtl = LANGUAGES.get(lang, {}).get("direction") == "rtl"
            wrap_width = 35 if is_rtl else 42
            return textwrap.wrap(text, width=wrap_width)

        font_primary = self._resolve_font(
            primary_lang, _font_size(primary_lang, 88, 68)
        )
        font_secondary = self._resolve_font(
            secondary_lang, _font_size(secondary_lang, 70, 53)
        )

        primary_lines = prepare_text_lines(primary_text, primary_lang)
        secondary_lines = prepare_text_lines(secondary_text, secondary_lang)

        # Colors (with alpha for fading)
        text_colors = self.settings.get("text_colors", {})
        color_primary = tuple(text_colors.get("primary", (245, 245, 247)))
        color_secondary = tuple(text_colors.get("secondary", (120, 180, 255)))
        fill_primary = color_primary[:3] + (alpha,)
        fill_secondary = color_secondary[:3] + (alpha,)

        # Calculate total text block height
        line_height_primary = int(85 * scale)
        line_height_secondary = int(65 * scale)
        gap = int(30 * scale)

        total_height = len(primary_lines) * line_height_primary
        if secondary_lines:
            total_height += gap + len(secondary_lines) * line_height_secondary

        start_y = (h - total_height) // 2

        # Draw primary text lines with Pillow's native RAQM renderer. RAQM
        # performs correct Arabic/Persian shaping, bidi ordering and kerning.
        y = start_y
        for line in primary_lines:
            dir_str = (
                "rtl"
                if LANGUAGES.get(primary_lang, {}).get("direction") == "rtl"
                else "ltr"
            )
            bbox = draw.textbbox((0, 0), line, font=font_primary, direction=dir_str)
            text_width = bbox[2] - bbox[0]
            x = (w - text_width) // 2
            draw.text(
                (x, y), line, fill=fill_primary, font=font_primary, direction=dir_str
            )
            y += line_height_primary

        # Draw secondary text lines
        if secondary_lines:
            y += gap
            for line in secondary_lines:
                dir_str = (
                    "rtl"
                    if LANGUAGES.get(secondary_lang, {}).get("direction") == "rtl"
                    else "ltr"
                )
                bbox = draw.textbbox(
                    (0, 0), line, font=font_secondary, direction=dir_str
                )
                text_width = bbox[2] - bbox[0]
                x = (w - text_width) // 2
                draw.text(
                    (x, y),
                    line,
                    fill=fill_secondary,
                    font=font_secondary,
                    direction=dir_str,
                )
                y += line_height_secondary

        return img.convert("RGB")  # FFmpeg expects RGB for rawvideo input

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
        keep_text_visible: bool = False,
    ) -> bool:
        """
        Creates a high-quality video clip using FFmpeg stdin pipe without deadlocks.
        Text remains on screen for the entire clip duration, fading in at the start
        and fading out at the end while the wave keeps looping.
        """
        fps = self.fps
        total_frames_in_clip = int(total_duration * fps)
        audio_dur = self.get_audio_duration(audio_path)
        audio_duration_frames = int(audio_dur * fps)

        use_silent_audio = not (
            os.path.exists(audio_path) and os.path.getsize(audio_path) > 0
        )

        if use_silent_audio:
            print(
                f"  [Warning] Audio file {audio_path} is missing or empty, using silent audio."
            )
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
            resolve_binary("ffmpeg"),
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{self.width}x{self.height}",
            "-r",
            str(fps),
            "-i",
            "-",
            *audio_source_cmd,
            *(["-filter_complex", filter_complex_str] if filter_complex_str else []),
            "-map",
            "0:v",
            *audio_map,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "44100",
            "-pix_fmt",
            "yuv420p",
            "-t",
            f"{total_duration:.2f}",  # Use -t for duration instead of -shortest
            output_path,
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )

            # Write frames directly to pipe
            for f_idx_in_clip in range(total_frames_in_clip):
                current_frame_global = current_frame_global_offset + f_idx_in_clip
                img = self.create_frame_image_in_memory(
                    primary_text,
                    secondary_text,
                    primary_lang,
                    secondary_lang,
                    f_idx_in_clip,
                    total_frames_in_clip,
                    audio_duration_frames,
                    current_frame_global,
                    total_frames_global,
                    keep_text_visible=keep_text_visible,
                )
                try:
                    process.stdin.write(img.tobytes())
                except BrokenPipeError:
                    print(
                        f"  [Warning] Broken pipe detected during frame write. FFmpeg process might have terminated early."
                    )
                    break  # Exit loop if pipe is broken

            process.stdin.close()
            process.wait()
            return process.returncode == 0
        except Exception as e:
            print(f"  [Error] Failed to pipe video clip: {e}")
            return False

    def create_silence_clip(
        self,
        duration: float,
        output_path: str,
        current_frame_global_offset: int,
        total_frames_global: int,
    ) -> bool:
        """
        Creates a smooth transitions/silence gap clip with slowly moving waves and absolute silence.
        No text or text fading is applied.
        """
        fps = self.fps
        total_frames_in_clip = int(duration * fps)

        cmd = [
            resolve_binary("ffmpeg"),
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{self.width}x{self.height}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "44100",
            "-pix_fmt",
            "yuv420p",
            "-t",
            f"{duration:.2f}",
            output_path,
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )

            # Write frames, passing global frame info for continuous wave animation
            for f_idx_in_clip in range(total_frames_in_clip):
                current_frame_global = current_frame_global_offset + f_idx_in_clip
                img = self.create_frame_image_in_memory(
                    "",
                    "",
                    "en",
                    "fa",
                    f_idx_in_clip,
                    total_frames_in_clip,
                    0,
                    current_frame_global,
                    total_frames_global,
                )
                process.stdin.write(img.tobytes())

            process.stdin.close()
            process.wait()
            return process.returncode == 0
        except Exception as e:
            print(f"  [Error] Failed to create silence clip: {e}")
            return False

    def _get_duration(self, file_path: str) -> float:
        cmd = [
            resolve_binary("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, creationflags=CREATE_NO_WINDOW
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def assemble_final_video(
        self,
        clip_paths: List[str],
        ambient_audio: str = None,
        output_filename: str = "final_video.mp4",
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
            resolve_binary("ffmpeg"),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list_path,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "44100",
            temp_merged_video,
        ]

        try:
            subprocess.run(
                concat_cmd, capture_output=True, text=True, check=True, creationflags=CREATE_NO_WINDOW
            )
        except subprocess.CalledProcessError as e:
            print(f"  [Error] FFmpeg concat failed: {e.stderr}")
            raise RuntimeError(f"FFmpeg concat failed: {e.stderr}")

        total_dur = self._get_duration(temp_merged_video)
        fade_dur = 1.0
        fade_out_start = max(total_dur - fade_dur, 0)

        has_ambient = ambient_audio and os.path.exists(ambient_audio)

        if has_ambient:
            bg_volume = self.settings.get("background_audio_volume", 0.3)
            print(f"  [Muxer] Mixing ambient audio: {ambient_audio}...")
            filter_complex = (
                f"[0:a]afade=t=in:st=0:d={fade_dur},"
                f"afade=t=out:st={fade_out_start:.2f}:d={fade_dur}[speech];"
                f"[1:a]volume={bg_volume}[bg];"
                f"[speech][bg]amix=inputs=2:duration=first:dropout_transition=0.5[outa]"
            )
            inputs = [
                "-i",
                temp_merged_video,
                "-stream_loop",
                "-1",
                "-i",
                ambient_audio,
            ]
        else:
            print(f"  [Muxer] Applying global audio fade-in/out...")
            filter_complex = (
                f"[0:a]afade=t=in:st=0:d={fade_dur},"
                f"afade=t=out:st={fade_out_start:.2f}:d={fade_dur}[outa]"
            )
            inputs = ["-i", temp_merged_video]

        mix_cmd = [
            resolve_binary("ffmpeg"),
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v",
            "-map",
            "[outa]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            final_output_path,
        ]
        try:
            subprocess.run(
                mix_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                creationflags=CREATE_NO_WINDOW,
            )
            print(f"  [Muxer] Completed final video with global fade-in/out.")
            return final_output_path
        except subprocess.CalledProcessError as e:
            print(f"  [Warning] Audio re-encode with fades failed: {e.stderr}")
            if os.path.exists(temp_merged_video):
                if os.path.exists(final_output_path):
                    os.remove(final_output_path)
                os.rename(temp_merged_video, final_output_path)
            return final_output_path
