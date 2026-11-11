# Portable PyInstaller specification for DataShip 2, including PDF preview.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).resolve().parents[1]
pdfium_datas, pdfium_binaries, pdfium_hidden = collect_all('pypdfium2')
raw_datas, raw_binaries, raw_hidden = collect_all('pypdfium2_raw')
a = Analysis(
    [str(Path(SPECPATH) / 'engine.py')],
    pathex=[str(root), str(Path(SPECPATH))],
    binaries=pdfium_binaries + raw_binaries,
    datas=[(str(root / 'assets'), 'assets')] + pdfium_datas + raw_datas,
    hiddenimports=collect_submodules('psycopg') + pdfium_hidden + raw_hidden,
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['nicegui', 'PySide6'], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='dataship-v2-engine',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
          upx_exclude=[], runtime_tmpdir=None, console=True,
          disable_windowed_traceback=False, argv_emulation=False,
          target_arch=None, codesign_identity=None, entitlements_file=None)
