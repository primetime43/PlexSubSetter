# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for PlexSubSetter
This file provides fine-grained control over the build process
"""

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# Collect all files from packages that need special handling
customtkinter_datas, customtkinter_binaries, customtkinter_hiddenimports = collect_all('customtkinter')
babelfish_datas, babelfish_binaries, babelfish_hiddenimports = collect_all('babelfish')
subliminal_datas, subliminal_binaries, subliminal_hiddenimports = collect_all('subliminal')
plexapi_datas, plexapi_binaries, plexapi_hiddenimports = collect_all('plexapi')

# Combine all collected data
all_datas = customtkinter_datas + babelfish_datas + subliminal_datas + plexapi_datas
all_binaries = customtkinter_binaries + babelfish_binaries + subliminal_binaries + plexapi_binaries
all_hiddenimports = (customtkinter_hiddenimports + babelfish_hiddenimports +
                     subliminal_hiddenimports + plexapi_hiddenimports)

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=all_binaries,
    datas=[
        ('ui', 'ui'),
        ('utils', 'utils'),
    ] + all_datas,
    hiddenimports=[
        'ui.login_frame',
        'ui.server_selection_frame',
        'ui.main_app_frame',
        'utils.constants',
        'utils.logging_config',
        'error_handling',
    ] + all_hiddenimports,
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
    name='PlexSubSetter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windowed mode (no console)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add your .ico file path here if you have one
)
