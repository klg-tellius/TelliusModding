from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).parent
sys.path.insert(0, str(root / 'App'))
datas = [(str(root / 'App/fe_modding/formats/cmb/externs_fe9.json'), 'fe_modding/formats/cmb'),
         (str(root / 'App/licenses'), 'licenses')]
binaries = []
hiddenimports = collect_submodules('fe_modding')
for package in ('sv_ttk', 'wgpu', 'rendercanvas'):
    data, binary, hidden = collect_all(package)
    datas += data
    binaries += binary
    hiddenimports += hidden
a = Analysis([str(root / 'App/main.py')], pathex=[str(root / 'App')],
             binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=['pytest', 'unittest', 'pip', 'setuptools'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='TelliusModding',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='TelliusModding')
