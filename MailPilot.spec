# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Work/projects/SestavaStrav/vyvoj/AutoReport_v12/AutoReport_qt.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Work/projects/SestavaStrav/vyvoj/AutoReport_v12/assets', 'assets'), ('C:/Work/projects/SestavaStrav/vyvoj/AutoReport_v12/config.example.json', '.'), ('C:/Work/projects/SestavaStrav/vyvoj/AutoReport_v12/.env.example', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['nicegui', 'webview', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MailPilot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Work/projects/SestavaStrav/vyvoj/AutoReport_v12/assets/app_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MailPilot',
)
