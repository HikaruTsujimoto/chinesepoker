# -*- mode: python ; coding: utf-8 -*-


from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / 'packaging' / 'launcher.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / 'assets'), 'assets'),
           (str(ROOT / 'chinesepoker' / 'ai' / 'session_value.json'), 'chinesepoker/ai'),
           (str(ROOT / 'chinesepoker' / 'ai' / 'action_advantage.json'), 'chinesepoker/ai')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ChinesePoker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
