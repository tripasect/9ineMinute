# -*- mode: python ; coding: utf-8 -*-
import sys
import os

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

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=binaries,
    datas=[
        ('gui_settings.json', '.'),
        ('watermark.png', '.'),
        # Add other assets here if they are required at runtime
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
    name='9ineMinuteEnglish',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # Set to True for debugging if the app fails to launch
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='logo.png' if os.path.exists('logo.png') else None
)

# For macOS, create an .app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='9ineMinuteEnglish.app',
        icon='logo.png' if os.path.exists('logo.png') else None,
        bundle_identifier='com.tripasect.9ineminute',
    )