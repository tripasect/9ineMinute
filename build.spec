# -*- mode: python ; coding: utf-8 -*-
import os
import sys

block_cipher = None

# Binaries to include (ffmpeg suite)
# These should be in the root directory during build.
binaries = []
for tool in ["ffmpeg", "ffplay", "ffprobe"]:
    name = tool + (".exe" if sys.platform == "win32" else "")
    if os.path.exists(name):
        binaries.append((name, "."))
    else:
        print(f"Warning: {name} not found in root, build might lack bundled ffmpeg.")

# Pillow's native RTL `direction="rtl"` support requires libraqm and its
# FriBidi dependency. Include their exact unversioned runtime lookup names:
# Pillow probes `libfribidi.dylib`, while PyInstaller otherwise only collects
# the versioned `libfribidi.0.dylib` transitive dependency.
if sys.platform == "win32":
    # Pillow's Windows wheel loads this at runtime to enable its built-in
    # RAQM renderer. The GitHub workflow stages it from MSYS2.
    if os.path.exists("libfribidi-0.dll"):
        binaries.append(("libfribidi-0.dll", "."))
    else:
        print(
            "Warning: libfribidi-0.dll not found; Persian/Arabic text will not render correctly."
        )
elif sys.platform == "darwin":
    for path in ("/opt/homebrew/lib/libraqm.0.dylib", "/usr/local/lib/libraqm.0.dylib"):
        if os.path.exists(path):
            binaries.append((path, "."))
            break
    else:
        print(
            "Warning: libraqm not found; Persian/Arabic text will not render correctly."
        )
    if os.path.exists("libfribidi.dylib"):
        binaries.append(("libfribidi.dylib", "."))
    else:
        print(
            "Warning: libfribidi.dylib not found; Persian/Arabic text will not render correctly."
        )

a = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=binaries,
    datas=[
        ("gui_settings.json", "."),
        ("watermark.png", "."),
        ("background-music.mp3", "."),
        ("opensourcefont.ttf", "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="9ineMinuteEnglish",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True for debugging if the app fails to launch
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="logo.png" if os.path.exists("logo.png") else None,
)

# For macOS, create an .app bundle
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="9ineMinuteEnglish.app",
        icon="logo.png" if os.path.exists("logo.png") else None,
        bundle_identifier="com.tripasect.9ineminute",
    )
