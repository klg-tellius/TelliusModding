from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all

# Tellius Patcher: one .exe a mod author ships with their .tpatch (see App/fe_modding/patcher.py).
root = Path(SPECPATH).parent
sys.path.insert(0, str(root / 'App'))
datas = [(str(root / 'App/licenses'), 'licenses')]
binaries = []
hiddenimports = []
data, binary, hidden = collect_all('sv_ttk')
datas += data
binaries += binary
hiddenimports += hidden
a = Analysis([str(root / 'App/patcher_main.py')], pathex=[str(root / 'App')],
             binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=['pytest', 'unittest', 'pip', 'setuptools', 'wgpu', 'rendercanvas'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='TelliusPatcher',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          runtime_tmpdir=None, console=False, disable_windowed_traceback=False)
