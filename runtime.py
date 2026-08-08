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