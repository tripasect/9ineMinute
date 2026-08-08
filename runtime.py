"""
Runtime helpers for both dev and bundled (PyInstaller) execution.

When the app is frozen by PyInstaller, sys.executable points inside a
temporary extract directory. For the dad-friendly build we also bundle
ffmpeg and ffplay next to the executable so they don't need to be on
PATH or installed separately.
"""

import os
import sys
from shutil import which


def bundle_dir() -> str:
    """Return the directory where the frozen executable's bundled files live."""
    if getattr(sys, "frozen", False):
        # PyInstaller: --onefile extracts to a temp dir; --onedir lives next to the exe.
        # sys._MEIPASS is the temp dir for onefile; for onedir it's the same as the exe dir.
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def app_data_dir() -> str:
    """Return a stable, writable directory for user config, cache, and output.

    In dev mode this is just the project directory (unchanged behavior).
    When frozen, `sys.executable`'s directory (and, for a --onefile build,
    `sys._MEIPASS`) are both ephemeral/read-only-ish, so persisted state
    (.env, gui_settings.json, output/, temp/, cache/) instead lives in a
    per-user application-support directory that survives across runs.
    """
    if not getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(__file__))

    app_name = "9ineMinuteEnglish"
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, app_name)
    os.makedirs(path, exist_ok=True)
    return path


def ensure_seeded(filename: str) -> str:
    """Return the app-data path for `filename`, copying the bundled default
    into place on first run if it doesn't exist there yet (frozen builds only).
    """
    dest = os.path.join(app_data_dir(), filename)
    if getattr(sys, "frozen", False) and not os.path.exists(dest):
        src = os.path.join(bundle_dir(), filename)
        if os.path.exists(src):
            import shutil

            try:
                shutil.copy2(src, dest)
            except OSError:
                pass
    return dest


def binary_name(base: str) -> str:
    """Return `base` with the platform's executable suffix."""
    if sys.platform == "win32":
        return base + ".exe"
    return base


def resolve_binary(base: str) -> str:
    """Locate `base` (e.g. 'ffmpeg', 'ffplay') using:
    1. The bundled copy next to the executable (PyInstaller --add-binary target).
    2. The same name on PATH (developer / system install).
    Returns the absolute path or just the name to fall back to subprocess PATH lookup.
    """
    name = binary_name(base)
    bundled = os.path.join(bundle_dir(), name)
    if os.path.exists(bundled):
        return bundled
    on_path = which(name)
    if on_path:
        return on_path
    return name  # last-resort: let subprocess try PATH
