# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for PlexSubSetter
This file provides fine-grained control over the build process
"""

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('ui', 'ui'),
        ('utils', 'utils'),
        ('config.ini', '.'),
    ],
    hiddenimports=[
        'ui.login_frame',
        'ui.server_selection_frame',
        'ui.main_app_frame',
        'utils.constants',
        'utils.logging_config',
        'error_handling',
        'customtkinter',
        'plexapi',
        'subliminal',
        'babelfish',
    ],
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
