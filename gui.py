#!/usr/bin/env python3
"""
9-Minute English Content Generator — Desktop GUI.

Native Tkinter front-end for the pipeline. Lets you edit provider/API
settings (.env), tune every content generation preference, and kick off
video generation with live logs — no terminal required.
"""

import json
import os
import queue
import subprocess
import sys
import threading

from runtime import app_data_dir, bundle_dir, ensure_seeded, resolve_binary

# When frozen (PyInstaller), sys.executable is this very app and there is no
# loose pipeline.py file on disk to shell out to — everything is bundled
# inside the single executable. To keep the "separate process + live log
# streaming" UX working in both dev and frozen builds, the frozen app can
# re-invoke *itself* with a hidden sentinel argument that skips the GUI and
# runs the pipeline's CLI directly in-process. See `pipeline_command()` and
# the dispatch below.
if len(sys.argv) > 1 and sys.argv[1] == "--run-pipeline":
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    import pipeline

    pipeline.main()
    sys.exit(0)

# CI invokes this hidden command against the frozen executable to ensure the
# runtime has Pillow's native RAQM support required for Persian/Arabic text.
if len(sys.argv) > 1 and sys.argv[1] == "--verify-raqm":
    from PIL import features

    if not features.check("raqm"):
        raise SystemExit("Pillow RAQM support is unavailable in this build.")
    raise SystemExit(0)

# BASE_DIR is a stable, writable directory: the project directory in dev
# mode, or a per-user Application Support directory when frozen (mirrors
# config.py's BASE_DIR so the GUI and the pipeline agree on where
# .env / gui_settings.json / output live).
BASE_DIR = app_data_dir()
ENV_PATH = os.path.join(BASE_DIR, ".env")
SETTINGS_PATH = ensure_seeded("gui_settings.json")
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "output")

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
except ImportError:
    sys.exit(
        "tkinter is not available. Install Python with Tk support (e.g. brew install python-tk)."
    )

try:
    from PIL import Image, ImageTk

    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# ── Fallback defaults (used only when config.py can't be imported) ──────────
FALLBACK_VIDEO_SETTINGS = {
    "duration_seconds": 540,
    "phrases_per_minute": 5,
    "pause_duration": 2,
    "translation_pause": 3,
    "phrase_gap_duration": 2,
    "repeat_pause_duration": 0.5,
    "background_audio": "background-music.mp3",
    "background_audio_volume": 0.3,
    "background_image": None,
    "repetitions": 0,
    "width": 1920,
    "height": 1080,
    "fps": 25,
    "watermark": "watermark.png",
    "channel_handle": "YouTube.com/@9ineMinuteEnglish",
    "fade_duration": 0.5,
}

FALLBACK_LANGUAGES = {
    "en": "English",
    "fa": "Persian (Farsi)",
    "ar": "Arabic",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "hi": "Hindi",
    "ja": "Japanese",
    "zh": "Chinese",
}

try:
    from config import (
        DEFAULT_ORIGIN_LANGUAGE,
        DEFAULT_TARGET_LANGUAGE,
        LANGUAGES,
        REVERSE_RATIO,
        VIDEO_SETTINGS,
    )
except Exception:
    VIDEO_SETTINGS = dict(FALLBACK_VIDEO_SETTINGS)
    LANGUAGES = {code: {"name": name} for code, name in FALLBACK_LANGUAGES.items()}
    REVERSE_RATIO = 0.15
    DEFAULT_ORIGIN_LANGUAGE = "en"
    DEFAULT_TARGET_LANGUAGE = "fa"


# ── Palette & presets ────────────────────────────────────────────────────────
BG = "#1e1e2e"
BG_ALT = "#27273a"
BG_INPUT = "#313244"
FG = "#cdd6f4"
MUTED = "#a6adc8"
ACCENT = "#89b4fa"
OK = "#a6e3a1"
WARN = "#f9e2af"
ERR = "#f38ba8"

PRESETS = [
    ("9 min (full)", 540, 40),
    ("6 min", 360, 30),
    ("3 min", 180, 20),
    ("1 min", 60, 10),
    ("30 s (test)", 30, 5),
    ("Custom", None, None),
]

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

LEVELS = ["any level", "A1", "A2", "B1", "B2", "C1"]

ENV_DEFAULTS = {
    "LLM_BASE_URL": "https://freellmapi.dragon-tail.ir/v1",
    "LLM_API_KEY": "",
    "LLM_MODEL": "auto",
    "OPENROUTER_API_KEY": "",
    "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
    "TTS_AUDIO_MODEL": "google/gemini-3.1-flash-tts-preview",
    "TTS_KOKORO_MODEL": "hexgrad/kokoro-82m",
}

ENV_LABELS = {
    "LLM_BASE_URL": "LLM base URL",
    "LLM_API_KEY": "LLM API key",
    "LLM_MODEL": "LLM model",
    "OPENROUTER_BASE_URL": "OpenRouter base URL",
    "OPENROUTER_API_KEY": "OpenRouter API key",
    "TTS_AUDIO_MODEL": "Origin TTS Model",
    "TTS_KOKORO_MODEL": "Translation TTS Model",
}

PROVIDER_SECTIONS = [
    ("Phrase Generation Provider", ["LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"]),
    (
        "TTS Generation Provider",
        [
            "OPENROUTER_BASE_URL",
            "OPENROUTER_API_KEY",
            "TTS_AUDIO_MODEL",
            "TTS_KOKORO_MODEL",
        ],
    ),
]


def read_env() -> dict:
    """Read key/value pairs from the .env file."""
    values = dict(ENV_DEFAULTS)
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    values[key.strip()] = val.strip().strip('"').strip("'")
        except OSError:
            pass
    return values


def write_env(values: dict) -> None:
    """Merge values into .env, preserving comments and unknown lines."""
    lines = []
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            lines = []
    updated, seen = [], set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in values:
                seen.add(key)
                updated.append(f'{key}="{values[key]}"')
                continue
        updated.append(line)
    for key, val in values.items():
        if key not in seen:
            updated.append(f'{key}="{val}"')
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(updated) + "\n")


def default_env_values() -> dict:
    values = read_env()
    # Mirror config.py's API-key defaults so a blank .env still works.
    if not values.get("OPENROUTER_API_KEY"):
        values["OPENROUTER_API_KEY"] = os.getenv("OPENROUTER_API_KEY", "")
    if not values.get("LLM_API_KEY"):
        values["LLM_API_KEY"] = os.getenv("LLM_API_KEY", "")
    return values


def load_gui_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, dict) and isinstance(data.get("content"), dict):
        return data["content"]
    return data


def save_gui_settings(data: dict) -> None:
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def project_python() -> str:
    venv = os.path.join(BASE_DIR, ".venv", "bin", "python")
    if os.path.exists(venv):
        return venv
    return sys.executable


def pipeline_command(args: list) -> list:
    """Build the subprocess argv to run the pipeline CLI with `args`.

    - Dev mode: `<project venv python> pipeline.py <args>` (unchanged).
    - Frozen mode: `<this app's executable> --run-pipeline <args>`, which is
      caught by the sentinel check at import time and dispatched straight to
      pipeline.main() in-process, since there's no standalone pipeline.py
      file or separate Python interpreter to shell out to once bundled.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-pipeline"] + list(args)
    return [project_python(), os.path.join(BASE_DIR, "pipeline.py")] + list(args)


# ── The app ──────────────────────────────────────────────────────────────────
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.env = default_env_values()
        self.gui = load_gui_settings()
        self.running = False
        self._preview_output = None
        self.log_queue = queue.Queue()
        # Maps tk.StringVar → row frame (for enabling preview buttons)
        self.file_rows: dict = {}
        self.provider_vars: dict = {}

        root.title("9-Minute English · Content Generator")
        root.geometry("1400x800")
        root.minsize(1300, 720)
        root.configure(bg=BG)

        self._build_style()
        self._build_menu()
        self._build_ui()
        self._enable_default_previews()
        self._poll_logs()

    # ---------------------------------------------------------------- style
    def _build_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=BG, foreground=FG, font=("Helvetica", 11))
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=BG_ALT,
            foreground=MUTED,
            padding=(14, 8),
            borderwidth=0,
            font=("Helvetica", 11, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG_INPUT)],
            foreground=[("selected", ACCENT)],
        )
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=BG_ALT)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Card.TLabel", background=BG_ALT, foreground=FG)
        style.configure(
            "Title.TLabel", background=BG, foreground=FG, font=("Helvetica", 14, "bold")
        )
        style.configure(
            "Section.TLabel",
            background=BG_ALT,
            foreground=ACCENT,
            font=("Helvetica", 11, "bold"),
        )
        style.configure(
            "TEntry",
            fieldbackground=BG_INPUT,
            foreground=FG,
            insertcolor=FG,
            bordercolor=BG_INPUT,
            lightcolor=BG_INPUT,
            darkcolor=BG_INPUT,
            padding=4,
        )
        style.configure(
            "TCombobox",
            fieldbackground=BG_INPUT,
            background=BG_INPUT,
            foreground=FG,
            arrowcolor=MUTED,
            bordercolor=BG_INPUT,
            lightcolor=BG_INPUT,
            darkcolor=BG_INPUT,
            padding=4,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", BG_INPUT)],
            foreground=[("readonly", FG)],
        )
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#11111b",
            bordercolor=ACCENT,
            padding=(16, 8),
            font=("Helvetica", 11, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#a6bdf6")],
            foreground=[("disabled", "#6c7086")],
        )
        style.configure(
            "TButton",
            background=BG_INPUT,
            foreground=FG,
            bordercolor=BG_INPUT,
            padding=(12, 6),
        )
        style.map("TButton", background=[("active", "#3b3b52")])
        # Settings button — visually distinct, sits to the right of the tab bar
        style.configure(
            "Settings.TButton",
            background=BG_ALT,
            foreground=ACCENT,
            bordercolor=ACCENT,
            padding=(16, 10),
            font=("Helvetica", 10, "bold"),
        )
        style.map("Settings.TButton", background=[("active", BG_INPUT)])
        style.configure("TCheckbutton", background=BG, foreground=FG, focuscolor=BG)
        style.configure("Horizontal.TScale", background=BG)

    # ------------------------------------------------------------------ menu
    def _build_menu(self):
        menubar = tk.Menu(
            self.root,
            bg=BG_ALT,
            fg=FG,
            activebackground=ACCENT,
            activeforeground="#11111b",
        )
        file_menu = tk.Menu(
            menubar,
            tearoff=0,
            bg=BG_ALT,
            fg=FG,
            activebackground=ACCENT,
            activeforeground="#11111b",
        )
        file_menu.add_command(
            label="Save provider settings", command=self.save_providers
        )
        file_menu.add_command(label="Save all settings", command=self.save_all)
        file_menu.add_separator()
        file_menu.add_command(
            label="Open output folder", command=self.open_output_folder
        )
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)
        help_menu = tk.Menu(
            menubar,
            tearoff=0,
            bg=BG_ALT,
            fg=FG,
            activebackground=ACCENT,
            activeforeground="#11111b",
        )
        help_menu.add_command(
            label="README", command=lambda: self._open_path("README.md")
        )
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

    # ------------------------------------------------------------ build UI
    def _build_ui(self):
        # Container: notebook on the left, settings button on the right —
        # provider settings are rarely touched, so keep them out of the tab bar.
        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True, padx=10, pady=(10, 6))

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(side="left", fill="both", expand=True)

        side = ttk.Frame(container)
        side.pack(side="left", fill="y", padx=(10, 0))
        self.settings_btn = ttk.Button(
            side,
            text="⚙  Settings",
            style="Settings.TButton",
            command=self._open_settings,
        )
        self.settings_btn.pack(anchor="n")

        self.tab_content = ttk.Frame(self.notebook)
        self.tab_run = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_content, text=" Content ")
        self.notebook.add(self.tab_run, text=" Generate ")

        self._build_content_tab()
        self._build_run_tab()
        self._build_statusbar()

    # ------------------------------------------------------ providers dialog
    def _open_settings(self):
        """Open provider/API key settings in a separate dialog."""
        if getattr(self, "_settings_win", None) is not None:
            try:
                if self._settings_win.winfo_exists():
                    self._settings_win.lift()
                    self._settings_win.focus_force()
                    return
            except tk.TclError:
                pass

        win = tk.Toplevel(self.root)
        win.title("Settings — Providers & API keys")
        win.geometry("640x480")
        win.minsize(600, 420)
        win.configure(bg=BG)
        win.transient(self.root)
        self._settings_win = win

        header = ttk.Label(win, text="Providers & API keys", style="Title.TLabel")
        header.pack(anchor="w", padx=14, pady=(14, 2))
        sub = ttk.Label(
            win,
            text="Saved straight into .env — used by the next run.",
            style="Muted.TLabel",
        )
        sub.pack(anchor="w", padx=14, pady=(0, 10))

        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        body.columnconfigure(0, weight=1)

        self.provider_vars = {}
        for idx, (title, keys) in enumerate(PROVIDER_SECTIONS):
            card = ttk.Frame(body, style="Card.TFrame")
            card.grid(row=idx, column=0, sticky="ew", padx=4, pady=(0, 12))
            ttk.Label(card, text=title, style="Section.TLabel").pack(
                anchor="w", padx=12, pady=(10, 6)
            )
            for key in keys:
                row = ttk.Frame(card, style="Card.TFrame")
                row.pack(fill="x", padx=12, pady=3)
                ttk.Label(
                    row, text=ENV_LABELS[key], width=26, style="Card.TLabel"
                ).pack(side="left", anchor="w")
                var = tk.StringVar(value=self.env.get(key, ""))
                entry = ttk.Entry(row, textvariable=var)
                entry.pack(side="left", fill="x", expand=True, ipady=2)
                self.provider_vars[key] = var

        btn_row = ttk.Frame(win)
        btn_row.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Button(
            btn_row,
            text="💾  Save",
            style="Accent.TButton",
            command=lambda: self.save_providers(show=True, parent=win),
        ).pack(side="left")
        win.provider_status = ttk.Label(btn_row, text="", style="Muted.TLabel")
        win.provider_status.pack(side="left", padx=12)

        win.bind("<Escape>", lambda _e: win.destroy())

    # ------------------------------------------------------- content tab
    def _build_content_tab(self):
        tab = self.tab_content
        header = ttk.Label(
            tab, text="Content generation preferences", style="Title.TLabel"
        )
        header.pack(anchor="w", padx=14, pady=(12, 10))

        cols = ttk.Frame(tab)
        cols.pack(fill="both", expand=True, padx=8)
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=1)

        left = ttk.Frame(cols, style="Card.TFrame")
        right = ttk.Frame(cols, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=6, pady=4)
        right.grid(row=0, column=1, sticky="nsew", padx=6, pady=4)

        self.var = {}
        g = self.gui

        # ── Left column ──────────────────────────────────────────────
        ttk.Label(left, text="Video & content", style="Section.TLabel").pack(
            anchor="w", padx=12, pady=(10, 6)
        )

        self.preset_var = tk.StringVar(value=g.get("preset", PRESETS[0][0]))
        preset_row = self._labeled_row(left, "Length preset")
        preset_cb = ttk.Combobox(
            preset_row,
            textvariable=self.preset_var,
            values=[p[0] for p in PRESETS],
            state="readonly",
            width=18,
        )
        preset_cb.pack(side="left", fill="x", expand=True)
        preset_cb.bind("<<ComboboxSelected>>", self._on_preset)

        self.duration_var = tk.IntVar(
            value=g.get("duration", VIDEO_SETTINGS.get("duration_seconds", 540))
        )
        self._labeled_row(left, "Duration (seconds)", self.duration_var, 0, 9999)

        self.count_var = tk.IntVar(value=g.get("count", 40))
        self._labeled_row(left, "Phrase count", self.count_var, 1, 200)

        self.topic_var = tk.StringVar(value=g.get("topic", TOPICS[0]))
        self._labeled_row(left, "Topic", self.topic_var, choices=TOPICS)

        self.level_var = tk.StringVar(value=g.get("level", "any level"))
        self._labeled_row(left, "CEFR level", self.level_var, choices=LEVELS)

        self.origin_var = tk.StringVar(
            value=g.get("origin_lang", DEFAULT_ORIGIN_LANGUAGE)
        )
        self._labeled_row(
            left,
            "Origin language",
            self.origin_var,
            choices=list(LANGUAGES.keys()),
            readonly=True,
        )

        self.target_var = tk.StringVar(
            value=g.get("target_lang", DEFAULT_TARGET_LANGUAGE)
        )
        self._labeled_row(
            left,
            "Target language",
            self.target_var,
            choices=list(LANGUAGES.keys()),
            readonly=True,
        )

        self.reps_var = tk.IntVar(
            value=g.get("repetitions", VIDEO_SETTINGS.get("repetitions", 0))
        )
        self._labeled_row(left, "Repetitions (0–5)", self.reps_var, 0, 5)

        self.reverse_var = tk.DoubleVar(value=g.get("reverse_ratio", REVERSE_RATIO))
        rev_row = self._labeled_row(left, "Reverse ratio")
        rev_scale = ttk.Scale(
            rev_row,
            from_=0.0,
            to=1.0,
            variable=self.reverse_var,
            orient="horizontal",
            command=self._on_reverse_slide,
        )
        rev_scale.pack(side="left", fill="x", expand=True)
        self.reverse_label = ttk.Label(
            rev_row, text=f"{self.reverse_var.get():.0%}", style="Card.TLabel", width=5
        )
        self.reverse_label.pack(side="left")

        self.output_var = tk.StringVar(value=g.get("output", "video_language.mp4"))
        self._labeled_row(left, "Output filename", self.output_var)

        self.custom_phrases_var = tk.StringVar(value=g.get("custom_phrases", ""))
        self._file_row(
            left, "Custom phrases (JSON)", self.custom_phrases_var, preview_type="json"
        )

        # ── Right column ─────────────────────────────────────────────
        ttk.Label(
            right, text="Background & video settings", style="Section.TLabel"
        ).pack(anchor="w", padx=12, pady=(10, 6))

        # Pre-fill background image from saved settings or config default
        _bg_image_default = (
            g.get("background_image", VIDEO_SETTINGS.get("background_image") or "")
            or ""
        )
        self.bg_image_var = tk.StringVar(value=_bg_image_default)
        self._file_row(
            right,
            "Background image",
            self.bg_image_var,
            preview_type="image",
            hint="(optional)",
        )

        # Pre-fill background music from saved settings or config default
        _bg_music_default = (
            g.get("background_music", VIDEO_SETTINGS.get("background_audio") or "")
            or ""
        )
        self.bg_music_var = tk.StringVar(value=_bg_music_default)
        self._file_row(
            right, "Background music", self.bg_music_var, preview_type="audio"
        )

        self.watermark_var = tk.StringVar(
            value=g.get("watermark", VIDEO_SETTINGS.get("watermark") or "")
        )
        self._file_row(
            right, "Watermark image", self.watermark_var, preview_type="image"
        )

        self.width_var = tk.IntVar(
            value=g.get("width", VIDEO_SETTINGS.get("width", 1920))
        )
        self._labeled_row(right, "Width (px)", self.width_var, 320, 7680)

        self.height_var = tk.IntVar(
            value=g.get("height", VIDEO_SETTINGS.get("height", 1080))
        )
        self._labeled_row(right, "Height (px)", self.height_var, 240, 4320)

        self.fps_var = tk.IntVar(value=g.get("fps", VIDEO_SETTINGS.get("fps", 25)))
        self._labeled_row(right, "FPS", self.fps_var, 5, 120)

        self.pause_var = tk.DoubleVar(
            value=g.get("pause_duration", VIDEO_SETTINGS.get("pause_duration", 2))
        )
        self._labeled_row(right, "Pause after TTS (s)", self.pause_var, 0.0, 30.0, 0.1)

        self.gap_var = tk.DoubleVar(
            value=g.get(
                "phrase_gap_duration", VIDEO_SETTINGS.get("phrase_gap_duration", 2)
            )
        )
        self._labeled_row(
            right, "Gap between phrases (s)", self.gap_var, 0.0, 30.0, 0.1
        )

        self.rep_pause_var = tk.DoubleVar(
            value=g.get(
                "repeat_pause_duration",
                VIDEO_SETTINGS.get("repeat_pause_duration", 0.5),
            )
        )
        self._labeled_row(right, "Repeat pause (s)", self.rep_pause_var, 0.0, 30.0, 0.1)

        self.bg_vol_var = tk.DoubleVar(
            value=g.get(
                "background_audio_volume",
                VIDEO_SETTINGS.get("background_audio_volume", 0.3),
            )
        )
        self._labeled_row(right, "Music volume (0–1)", self.bg_vol_var, 0.0, 1.0, 0.05)

        self.fade_var = tk.DoubleVar(
            value=g.get("fade_duration", VIDEO_SETTINGS.get("fade_duration", 0.5))
        )
        self._labeled_row(right, "Text fade (s)", self.fade_var, 0.0, 5.0, 0.1)

        self.handle_var = tk.StringVar(
            value=g.get(
                "channel_handle",
                VIDEO_SETTINGS.get("channel_handle", "YouTube.com/@9ineMinuteEnglish"),
            )
        )
        self._labeled_row(right, "Channel handle", self.handle_var)

    def _labeled_row(
        self,
        parent,
        label,
        var=None,
        lo=0,
        hi=999,
        step=1,
        choices=None,
        readonly=False,
    ):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", padx=12, pady=3)
        lbl = ttk.Label(row, text=label, width=24, style="Card.TLabel")
        lbl.pack(side="left", anchor="w")
        if var is not None:
            if choices is not None:
                cb = ttk.Combobox(
                    row,
                    textvariable=var,
                    values=choices,
                    state="readonly" if readonly else "normal",
                    width=20,
                )
                cb.pack(side="left", fill="x", expand=True)
            elif isinstance(var, (tk.IntVar, tk.DoubleVar)):
                sp = tk.Spinbox(
                    row,
                    from_=lo,
                    to=hi,
                    increment=step,
                    textvariable=var,
                    width=20,
                    bg=BG_INPUT,
                    fg=FG,
                    insertbackground=FG,
                    buttonbackground=BG_ALT,
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=BG_INPUT,
                    highlightcolor=ACCENT,
                )
                sp.pack(side="left", fill="x", expand=True)
            else:
                entry = ttk.Entry(row, textvariable=var)
                entry.pack(side="left", fill="x", expand=True, ipady=2)
        return row

    def _file_row(self, parent, label, var, preview_type=None, hint=None):
        """Create a file-picker row with Browse and (where useful) preview buttons."""
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", padx=12, pady=3)

        ttk.Label(row, text=label, width=24, style="Card.TLabel").pack(
            side="left", anchor="w"
        )

        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side="left", fill="x", expand=True, ipady=2)
        if hint:
            ttk.Label(row, text=hint, style="Muted.TLabel").pack(
                side="left", padx=(4, 0)
            )

        row.preview_type = preview_type
        row.preview_btn = None

        if preview_type == "audio":
            # Audio rows get a single play/stop toggle — no eye/preview button.
            play_btn = ttk.Button(
                row,
                text="▶",
                width=5,
                state="disabled",
                command=lambda v=var, r=row: self._toggle_audio_preview(v, r),
            )
            play_btn.pack(side="left", padx=(6, 0))
            row.play_btn = play_btn
        else:
            preview_btn = ttk.Button(
                row,
                text="👁️",
                width=4,
                state="disabled",
                command=lambda v=var, l=label, t=preview_type: self._preview(v, l, t),
            )
            preview_btn.pack(side="left", padx=(6, 0))
            row.preview_btn = preview_btn

        ttk.Button(
            row, text="📂", width=4, command=lambda v=var, l=label: self._browse(v, l)
        ).pack(side="left", padx=(6, 0))

        # Store row reference for later lookup (keyed by id since StringVar is unhashable)
        self.file_rows[id(var)] = (var, row)

        return row

    def _enable_default_previews(self):
        """Enable preview buttons for any file fields that already have a value."""
        for _var, row in self.file_rows.values():
            path = _var.get()
            if not path:
                continue
            full = path if os.path.isabs(path) else os.path.join(BASE_DIR, path)
            if os.path.exists(full):
                if row.preview_btn is not None:
                    row.preview_btn.config(state="normal")
                if getattr(row, "play_btn", None):
                    row.play_btn.config(state="normal")

    def _browse(self, var, label):
        if "image" in label.lower():
            kinds = [
                ("Images", "*.png *.jpg *.jpeg *.bmp *.webp"),
                ("All files", "*.*"),
            ]
        elif "music" in label.lower() or "audio" in label.lower():
            kinds = [("Audio", "*.mp3 *.wav *.m4a *.aac"), ("All files", "*.*")]
        elif "phrases" in label.lower():
            kinds = [("JSON", "*.json"), ("All files", "*.*")]
        else:
            kinds = [
                ("Images", "*.png *.jpg *.jpeg *.bmp *.webp"),
                ("All files", "*.*"),
            ]

        path = filedialog.askopenfilename(
            parent=self.root,
            title=f"Choose {label}",
            filetypes=kinds,
            initialdir=BASE_DIR,
        )
        if path:
            rel = os.path.relpath(path, BASE_DIR) if path.startswith(BASE_DIR) else path
            var.set(rel)
            # Enable this row's preview buttons
            row = self.file_rows.get(id(var))
            if row:
                if row.preview_btn is not None:
                    row.preview_btn.config(state="normal")
                if getattr(row, "play_btn", None):
                    row.play_btn.config(state="normal")

    def _preview(self, var, label, preview_type):
        """Show a preview of the selected file (image window or JSON dump)."""
        path = var.get()
        if not path:
            return
        if not os.path.isabs(path):
            path = os.path.join(BASE_DIR, path)
        if not os.path.exists(path):
            messagebox.showwarning(
                "File not found", f"File not found:\n{path}", parent=self.root
            )
            return

        if preview_type == "image":
            if not _PIL_AVAILABLE:
                messagebox.showwarning(
                    "PIL not installed",
                    "Install Pillow to preview images:\n  pip install Pillow",
                    parent=self.root,
                )
                return
            try:
                img = Image.open(path)
                img.thumbnail((640, 480))
                photo = ImageTk.PhotoImage(img)

                win = tk.Toplevel(self.root)
                win.title(f"Preview — {label}")
                win.resizable(False, False)
                win.configure(bg=BG)

                lbl = tk.Label(win, image=photo, bg=BG)
                lbl.image = photo  # keep reference
                lbl.pack(padx=10, pady=10)

                tk.Button(
                    win,
                    text="✕  Close",
                    command=win.destroy,
                    bg=BG_INPUT,
                    fg=FG,
                    relief="flat",
                    padx=12,
                ).pack(pady=(0, 10))
            except Exception as exc:
                messagebox.showerror("Preview failed", str(exc), parent=self.root)

        elif preview_type == "json":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pretty = json.dumps(data, indent=2, ensure_ascii=False)

                win = tk.Toplevel(self.root)
                win.title(f"Preview — {label}")
                win.geometry("600x500")
                win.configure(bg=BG)

                txt = scrolledtext.ScrolledText(
                    win, bg="#15151f", fg=FG, font=("Menlo", 10), wrap="word"
                )
                txt.insert("1.0", pretty)
                txt.config(state="disabled")
                txt.pack(fill="both", expand=True, padx=10, pady=10)

                tk.Button(
                    win,
                    text="Close",
                    command=win.destroy,
                    bg=BG_INPUT,
                    fg=FG,
                    relief="flat",
                    padx=12,
                ).pack(pady=(0, 10))
            except Exception as exc:
                messagebox.showerror("Preview failed", str(exc), parent=self.root)

    def _toggle_audio_preview(self, var, row):
        """Play/stop toggle for the audio file on this row."""
        btn = row.play_btn
        proc = getattr(row, "audio_proc", None)

        # Stop any playing audio on this row.
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            row.audio_proc = None
            btn.config(text="▶")
            return

        path = var.get()
        if not path:
            return

        # Resolve path: check direct, then bundle, then BASE_DIR
        resolved = None
        if os.path.isabs(path) and os.path.exists(path):
            resolved = path
        elif os.path.exists(os.path.join(bundle_dir(), os.path.basename(path))):
            resolved = os.path.join(bundle_dir(), os.path.basename(path))
        elif os.path.exists(os.path.join(BASE_DIR, path)):
            resolved = os.path.join(BASE_DIR, path)

        if not resolved:
            messagebox.showwarning(
                "File not found", f"File not found:\n{path}", parent=self.root
            )
            return

        path = resolved

        try:
            if sys.platform == "darwin":
                proc = subprocess.Popen(["afplay", path])
            else:
                proc = subprocess.Popen(
                    [
                        resolve_binary("ffplay"),
                        "-nodisp",
                        "-autoexit",
                        "-loglevel",
                        "quiet",
                        path,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception as exc:
            messagebox.showerror("Playback failed", str(exc), parent=self.root)
            return

        row.audio_proc = proc
        btn.config(text="■ Stop")

        def _watch():
            proc.wait()
            self.root.after(0, lambda: self._audio_playback_done(row, proc))

        threading.Thread(target=_watch, daemon=True).start()

    def _audio_playback_done(self, row, proc):
        """Reset the play button when a playback process ends on its own."""
        if getattr(row, "audio_proc", None) is proc:
            row.audio_proc = None
            if getattr(row, "play_btn", None):
                row.play_btn.config(text="▶")

    def _on_preset(self, _event=None):
        name = self.preset_var.get()
        for pname, dur, count in PRESETS:
            if pname == name and dur is not None:
                self.duration_var.set(dur)
                self.count_var.set(count)
                break

    def _on_reverse_slide(self, _value=None):
        self.reverse_label.config(text=f"{self.reverse_var.get():.0%}")

    # ------------------------------------------------------------ run tab
    def _build_run_tab(self):
        tab = self.tab_run
        top = ttk.Frame(tab)
        top.pack(fill="x", padx=12, pady=(12, 8))
        self.summary_label = ttk.Label(
            top, text="", style="Muted.TLabel", wraplength=1200
        )
        self.summary_label.pack(fill="x")

        # Output directory (with browse)
        out_row = ttk.Frame(tab)
        out_row.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(out_row, text="Output directory", width=18).pack(
            side="left", anchor="w"
        )
        self.output_dir_var = tk.StringVar(
            value=self.gui.get("output_dir", DEFAULT_OUTPUT_DIR)
        )
        out_entry = ttk.Entry(out_row, textvariable=self.output_dir_var)
        out_entry.pack(side="left", fill="x", expand=True, ipady=2)
        ttk.Button(out_row, text="📂", width=4, command=self._browse_output_dir).pack(
            side="left", padx=(6, 0)
        )

        self.log_text = scrolledtext.ScrolledText(
            tab,
            height=20,
            bg="#15151f",
            fg=FG,
            insertbackground=FG,
            relief="flat",
            borderwidth=8,
            font=("Menlo", 11),
            state="disabled",
            wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        ctrl = ttk.Frame(tab)
        ctrl.pack(fill="x", padx=12, pady=(0, 10))
        self.run_btn = ttk.Button(
            ctrl, text="▶  Generate", style="Accent.TButton", command=self.generate
        )
        self.run_btn.pack(side="left")
        self.preview_btn = ttk.Button(
            ctrl, text="⚡  Preview", command=self.preview_generate
        )
        self.preview_btn.pack(side="left", padx=8)
        self.stop_btn = ttk.Button(ctrl, text="🗑  Clear", command=self.clear_log)
        self.stop_btn.pack(side="left", padx=8)
        ttk.Button(ctrl, text="📁  Output", command=self.open_output_folder).pack(
            side="right"
        )
        hint = ttk.Label(
            tab,
            text="Preview generation builds a ~15s video from a hard-coded "
            "phrase with real TTS audio — no LLM API call.",
            style="Muted.TLabel",
        )
        hint.pack(anchor="w", padx=12, pady=(0, 8))

    def _browse_output_dir(self):
        path = filedialog.askdirectory(
            parent=self.root,
            title="Choose output directory",
            initialdir=self.output_dir_var.get() or DEFAULT_OUTPUT_DIR,
        )
        if path:
            self.output_dir_var.set(path)

    def _build_statusbar(self):
        self.status_var = tk.StringVar(value="Ready")
        bar = tk.Label(
            self.root,
            textvariable=self.status_var,
            bg=BG_ALT,
            fg=MUTED,
            anchor="w",
            padx=12,
            pady=3,
            font=("Helvetica", 10),
        )
        bar.pack(fill="x", side="bottom")

    # ------------------------------------------------------------- actions
    def save_providers(self, show=True, parent=None):
        if self.provider_vars:
            values = {k: v.get().strip() for k, v in self.provider_vars.items()}
        else:
            values = dict(self.env)
        try:
            write_env(values)
        except OSError as e:
            messagebox.showerror("Save failed", str(e), parent=parent or self.root)
            return False
        self.env.update(values)
        if show:
            win = parent or self.root
            status_lbl = getattr(win, "provider_status", None)
            if status_lbl is not None:
                status_lbl.config(text="Saved to .env ✓", foreground=OK)
                win.after(2500, lambda: status_lbl.config(text="", foreground=MUTED))
        return True

    def collect_content(self) -> dict:
        """Gather content preferences into a plain dict."""
        return {
            "preset": self.preset_var.get(),
            "duration": int(self.duration_var.get()),
            "count": int(self.count_var.get()),
            "topic": self.topic_var.get().strip(),
            "level": self.level_var.get(),
            "origin_lang": self.origin_var.get(),
            "target_lang": self.target_var.get(),
            "repetitions": int(self.reps_var.get()),
            "reverse_ratio": round(float(self.reverse_var.get()), 3),
            "output": self.output_var.get().strip() or "video_language.mp4",
            "custom_phrases": self.custom_phrases_var.get().strip(),
            "background_image": self.bg_image_var.get().strip(),
            "background_music": self.bg_music_var.get().strip(),
            "watermark": self.watermark_var.get().strip(),
            "width": int(self.width_var.get()),
            "height": int(self.height_var.get()),
            "fps": int(self.fps_var.get()),
            "pause_duration": float(self.pause_var.get()),
            "phrase_gap_duration": float(self.gap_var.get()),
            "repeat_pause_duration": float(self.rep_pause_var.get()),
            "background_audio_volume": float(self.bg_vol_var.get()),
            "fade_duration": float(self.fade_var.get()),
            "channel_handle": self.handle_var.get().strip(),
            "output_dir": self.output_dir_var.get().strip() or DEFAULT_OUTPUT_DIR,
        }

    def save_all(self):
        self.save_providers(show=False)
        data = self.collect_content()
        save_gui_settings(data)
        self.gui.update(data)
        self.status_var.set("All settings saved.")
        return True

    def _video_settings_dict(self) -> dict:
        g = self.collect_content()
        vs = {}
        for key in (
            "width",
            "height",
            "fps",
            "pause_duration",
            "phrase_gap_duration",
            "repeat_pause_duration",
            "background_audio_volume",
            "fade_duration",
            "channel_handle",
        ):
            vs[key] = g[key]
        if g["watermark"]:
            vs["watermark"] = g["watermark"]
        if g["background_image"]:
            vs["background_image"] = g["background_image"]
        vs["output_dir"] = g["output_dir"]
        return vs

    def generate(self):
        if self.running:
            return
        if not self.save_all():
            return

        g = self.collect_content()
        origin = g["origin_lang"]
        target = g["target_lang"]
        for code, label in (("origin", origin), ("target", target)):
            if code == "origin" and label not in LANGUAGES:
                messagebox.showerror(
                    "Unknown language",
                    f"Unknown origin language: {label}",
                    parent=self.root,
                )
                return
            if code == "target" and label not in LANGUAGES:
                messagebox.showerror(
                    "Unknown language",
                    f"Unknown target language: {label}",
                    parent=self.root,
                )
                return

        if (
            g["custom_phrases"]
            and not os.path.exists(os.path.join(BASE_DIR, g["custom_phrases"]))
            and not os.path.exists(g["custom_phrases"])
        ):
            messagebox.showerror(
                "Missing file",
                f"Custom phrases file not found:\n{g['custom_phrases']}",
                parent=self.root,
            )
            return

        topic = g["topic"] or TOPICS[0]
        if g["level"] and g["level"] != "any level":
            topic = f"{topic} ({g['level']})"

        # Persist UI prefs + run-scoped settings for the subprocess to read.
        save_gui_settings(
            {
                "content": g,
                "video_settings": self._video_settings_dict(),
                "reverse_ratio": g["reverse_ratio"],
            }
        )

        args = [
            "--topic",
            topic,
            "--count",
            str(g["count"]),
            "--duration",
            str(g["duration"]),
            "--origin-lang",
            origin,
            "--target-lang",
            target,
            "--repetitions",
            str(g["repetitions"]),
            "--output",
            g["output"],
            "--settings",
            SETTINGS_PATH,
        ]
        if g["background_image"]:
            args += ["--background-image", g["background_image"]]
        if g["background_music"]:
            args += ["--background-music", g["background_music"]]
        if g["custom_phrases"]:
            args += ["--custom-phrases", g["custom_phrases"]]

        self._preview_output = None
        self._launch(pipeline_command(args), "Generating")

    def preview_generate(self):
        """Short real sample: hard-coded phrase, real TTS, no LLM call."""
        if self.running:
            return
        if not self.save_all():
            return

        g = self.collect_content()
        origin = g["origin_lang"]
        target = g["target_lang"]
        for code, label in (("origin", origin), ("target", target)):
            if label not in LANGUAGES:
                messagebox.showerror(
                    "Unknown language",
                    f"Unknown {'origin' if code == 'origin' else 'target'} language: {label}",
                    parent=self.root,
                )
                return

        # Persist UI prefs + run-scoped settings for the subprocess to read.
        save_gui_settings(
            {
                "content": g,
                "video_settings": self._video_settings_dict(),
                "reverse_ratio": g["reverse_ratio"],
            }
        )

        args = [
            "--preview",
            "--origin-lang",
            origin,
            "--target-lang",
            target,
            "--repetitions",
            str(g["repetitions"]),
            "--output",
            "preview.mp4",
            "--settings",
            SETTINGS_PATH,
        ]
        if g["background_image"]:
            args += ["--background-image", g["background_image"]]
        if g["background_music"]:
            args += ["--background-music", g["background_music"]]

        self._preview_output = os.path.join(g["output_dir"], "preview.mp4")
        self._launch(pipeline_command(args), "Preview generation")

    def _launch(self, cmd, label):
        self._append_log("─" * 60)
        self._append_log(f"{label}: " + " ".join(cmd))
        self._append_log("─" * 60)

        self.running = True
        self.run_btn.config(state="disabled")
        self.preview_btn.config(state="disabled")
        self.status_var.set("Generating…")

        def worker():
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=BASE_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    encoding="utf-8",
                    errors="replace",
                )
                for line in proc.stdout:
                    self.log_queue.put(line.rstrip())
                proc.wait()
                self.log_queue.put(None)
                self.log_queue.put(("done", proc.returncode))
            except Exception as e:
                self.log_queue.put(None)
                self.log_queue.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_logs(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item is None:
                    continue
                if isinstance(item, tuple) and item[0] in ("done", "error"):
                    self._finish_run(item)
                    break
                self._append_log(str(item))
        except queue.Empty:
            pass
        self.root.after(80, self._poll_logs)

    def _finish_run(self, item):
        self.running = False
        self.run_btn.config(state="normal")
        self.preview_btn.config(state="normal")
        if item[0] == "error":
            self._append_log(f"[GUI] Failed to launch pipeline: {item[1]}", ERR)
            self.status_var.set("Launch failed")
        elif item[1] == 0:
            self._append_log("")
            self._append_log("✔ Generation finished successfully.", OK)
            self.status_var.set("Done — check the output folder")
            # Auto-open the preview video immediately after a successful preview run.
            if self._preview_output and os.path.exists(self._preview_output):
                self._append_log(f"Opening preview: {self._preview_output}", ACCENT)
                self._open_path(self._preview_output)
            self._preview_output = None
        else:
            self._append_log(f"✘ Pipeline exited with code {item[1]}.", ERR)
            self.status_var.set("Generation failed")
            self._preview_output = None
        self.notebook.select(self.tab_run)

    def _append_log(self, text, color=None):
        self.log_text.config(state="normal")
        self.log_text.insert("end", text + "\n")
        if color:
            self.log_text.tag_add("color", "end-2l", "end-1l")
            self.log_text.tag_config("color", foreground=color)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def open_output_folder(self):
        output_dir = self.output_dir_var.get().strip() or DEFAULT_OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.Popen(["open", output_dir])
        elif os.name == "nt":
            os.startfile(output_dir)
        else:
            subprocess.Popen(["xdg-open", output_dir])

    def _open_path(self, rel):
        path = os.path.join(BASE_DIR, rel)
        if not os.path.exists(path):
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif os.name == "nt":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])


def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.1)
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
