# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification for Argus PII Guard v1.0.0.

Bundles Python backend modules, dependencies, and frontend static assets
into a standalone executable application.
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Base directory of the repository (SPECPATH is provided by PyInstaller)
BASE_DIR = os.path.abspath(SPECPATH)

# Data files: bundle frontend static assets and any icon resources
datas = [
    (os.path.join(BASE_DIR, 'frontend'), 'frontend'),
]

# Hidden imports to ensure pywebview, PIL plugins, and backend dependencies freeze cleanly
hidden_imports = [
    'webview',
    'bottle',
    'pillow_heif',
    'PIL',
    'PIL.Image',
    'urllib.request',
    'ollama',
    'backend.state',
    'backend.scanner',
    'backend.hardware_info',
    'backend.local_llm',
    'backend.model_downloader',
    'backend.create_icon',
]

# Add optional llama_cpp if installed
try:
    import llama_cpp
    hidden_imports.append('llama_cpp')
    datas.extend(collect_data_files('llama_cpp'))
except ImportError:
    pass

# Choose icon based on platform
icon_path = os.path.join(BASE_DIR, 'frontend', 'assets', 'argus-icon.ico')
if sys.platform == 'darwin':
    icns_candidate = os.path.join(BASE_DIR, 'frontend', 'assets', 'argus-icon.icns')
    if os.path.exists(icns_candidate):
        icon_path = icns_candidate
elif sys.platform.startswith('linux'):
    icon_path = os.path.join(BASE_DIR, 'frontend', 'assets', 'argus-icon.png')

a = Analysis(
    [os.path.join(BASE_DIR, 'backend', 'main.py')],
    pathex=[BASE_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Argus PII Guard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI application, no terminal window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.exists(icon_path) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Argus PII Guard',
)
