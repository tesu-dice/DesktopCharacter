# -*- mode: python ; coding: utf-8 -*-
# PyInstaller specファイル
# ビルド: pyinstaller main.spec

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# ai_toolsのモジュールを動的インポートで使っているため明示的に指定
hidden_imports = collect_submodules('ai_tools')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # ai_tools の .py ファイルをdatasとして含める
        # → フリーズ時に sys._MEIPASS/ai_tools/ に展開され、_discover_tools()がスキャンできる
        ('ai_tools/*.py', 'ai_tools'),
    ],
    hiddenimports=hidden_imports,
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

# --onefile 相当
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DesktopCharacter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # --noconsole 相当
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
