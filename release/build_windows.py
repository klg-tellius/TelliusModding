"""Build, smoke-test and zip a portable Windows app from a clean environment,
and Tellius Patcher, the one-file program players use to apply a mod's patch."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def clean_env():
    """No system Python or user-installed packages on PATH."""
    env = dict(os.environ)
    env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    env['PYTHONNOUSERSITE'] = '1'
    return env


def smoke_test(exe: Path, report: Path) -> None:
    with tempfile.TemporaryDirectory(prefix='tellius-smoke-') as cwd:  # an empty working directory
        subprocess.run([str(exe), '--self-test', str(report)], cwd=cwd, env=clean_env(), timeout=120, check=True)
    result = json.loads(report.read_text(encoding='utf-8'))
    if not result.get('ok'):
        raise SystemExit(f'Packaged smoke test failed: {report}')


def build_patcher() -> Path:
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
                    '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build/pyinstaller-patcher'),
                    str(ROOT / 'release/TelliusPatcher.spec')], cwd=ROOT, check=True)
    patcher = ROOT / 'dist/TelliusPatcher.exe'
    smoke_test(patcher, ROOT / 'build/patcher-smoke-test.json')
    digest = hashlib.sha256(patcher.read_bytes()).hexdigest()
    patcher.with_suffix('.exe.sha256').write_bytes(f'{digest}  {patcher.name}\n'.encode())
    return patcher


def main():
    if sys.platform != 'win32' or platform.architecture()[0] != '64bit':
        raise SystemExit('Build this release using 64-bit Python on Windows.')
    patcher = build_patcher()
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
                    '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build/pyinstaller'),
                    str(ROOT / 'release/TelliusModding.spec')], cwd=ROOT, check=True)
    app = ROOT / 'dist/TelliusModding'
    shutil.copyfile(patcher, app / patcher.name)  # mod authors hand it out with their patch
    licenses = app / 'licenses'
    licenses.mkdir(exist_ok=True)
    shutil.copytree(ROOT / 'App/licenses', licenses, dirs_exist_ok=True)
    # Preserve all installed dependency notices in the clean build environment.
    versions = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata['Name']
        versions[name] = dist.version
        for item in dist.files or []:
            parts = [part.lower() for part in item.parts]
            if any(part.startswith(('license', 'copying', 'copyright', 'notice')) for part in parts):
                source = Path(dist.locate_file(item))
                if source.is_file():
                    target = licenses / name / Path(*item.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    for name in ('LICENSE.txt', 'LICENSE'):
        license_path = Path(sys.base_prefix) / name
        if license_path.is_file():
            shutil.copyfile(license_path, licenses / 'Python-LICENSE.txt')
            break
    else:
        raise SystemExit('Python runtime license was not found; refusing to package.')
    for name in ('CREDITS.md',):
        shutil.copyfile(ROOT / name, app / name)
    shutil.copyfile(ROOT / 'release/START-HERE.txt', app / 'START-HERE.txt')
    (app / 'BUILD-INFO.json').write_bytes((json.dumps({
        'python': sys.version, 'platform': platform.platform(), 'packages': versions,
    }, indent=2) + '\n').encode('utf-8'))
    smoke_test(app / 'TelliusModding.exe', ROOT / 'build/packaged-smoke-test.json')
    output = ROOT / 'dist/TelliusModding-Windows-x64.zip'
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(app.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(app.parent))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_bytes(f'{digest}  {output.name}\n'.encode())
    print(f'Built and smoke-tested: {output} ({output.stat().st_size / 1024**2:.1f} MB) and '
          f'{patcher} ({patcher.stat().st_size / 1024**2:.1f} MB)')


if __name__ == '__main__':
    main()
