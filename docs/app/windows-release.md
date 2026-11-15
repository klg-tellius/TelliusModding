# Windows portable release

## For users

1. Open [GitHub Releases](https://github.com/klg-tellius/TelliusModding/releases/latest).
2. Download **TelliusModding-Windows-x64.zip** and extract the entire ZIP.
3. Double-click **TelliusModding.exe**. Keep its `_internal` folder alongside it.
4. Use **Download missing tools** to install WIT and optional FFmpeg.

Python, Tkinter, Pillow, NumPy, fontTools, the Sun Valley theme, and wgpu are
included. You do not need Python, pip, or administrator access.

WIT handles disc extraction/building. FFmpeg is used for general audio/video
imports. The first-run screen downloads pinned, SHA-256-verified packages from
wit.wiimm.de and gyan.dev. These are separate downloads, about 125 MB combined.
The app remains usable for existing projects while offline; disc/media features
need their respective tools installed first. You can return to setup through
**Settings > Disc and media tools**.

Downloaded tools live in `%LOCALAPPDATA%\TelliusModding\tools`. Preferences and
recent projects remain in `%USERPROFILE%\.tellius_modding`. Keep mod projects
outside the application folder. To update, extract the new release into a new
folder; your settings, downloaded tools, and projects stay separate.

The initial release is unsigned. Use the project's Releases page as the download
source and follow your organization's Windows security policy. The ZIP's SHA-256
checksum is included as a separate release asset.

## For maintainers

Build on Windows x64 with CPython 3.14. Use a clean virtual environment:

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r release/requirements-build.txt
.\.venv-build\Scripts\python.exe -m unittest discover -s App/tests -q
.\.venv-build\Scripts\python.exe release/build_windows.py
```

Outputs are `dist/TelliusModding-Windows-x64.zip` and its `.sha256` file.
The build collects application resources explicitly, copies dependency notices,
and runs the frozen EXE's `--self-test` in an empty working directory with no
Python on PATH. It verifies module loading, Tk/the theme, the script catalog,
NumPy/Pillow, fontTools, and the wgpu native library. It does not require a game
dump or a working GPU adapter; actual rendering still depends on the machine's
graphics drivers.

### Publishing a release

The **Windows portable release** GitHub Actions workflow
([windows-release.yml](../../.github/workflows/windows-release.yml)) runs the tests,
builds the ZIP and `TelliusPatcher.exe`, smoke-tests both, and uploads them as
workflow artifacts. It publishes a GitHub Release only when asked to.

To publish a release from `main`:

1. On a branch, set the new version in `App/fe_modding/__init__.py`
   (`__version__ = "0.3.0"`) and rewrite `release/RELEASE-NOTES.md`. Its first
   line must name the tag (`# Tellius Modding v0.3.0`). Update dependency pins
   if needed. Merge the pull request into `main`.
2. Open **Actions > Windows portable release > Run workflow**, keep the branch
   on `main`, tick **Publish**, and run it. Tick **Pre-release** for a test build.
3. When the run is green, the release `v0.3.0` exists with
   `TelliusModding-Windows-x64.zip`, `TelliusPatcher.exe` and their `.sha256`
   files, and the README's *latest release* link points to it.

The same can be started from a terminal:

```powershell
gh workflow run windows-release.yml --ref main -f publish=true
```

Pushing a tag `v<version>` also publishes, with that tag. Either way the run stops
before building when the tag does not match `__version__`, when the release
already exists, or when the release notes name another version. Releases are
never replaced: publish a new version instead. Without **Publish**, a run only
produces downloadable workflow artifacts, which is how to try a build first.

Tool URLs, versions, size bounds, and SHA-256 pins live in
`App/fe_modding/runtime_tools.py`. Validate new upstream archives and licenses
before updating them. The downloader stages installation and verifies the full
archive before installing; a failed download never creates a completed install.
Native executables and game files are not checked into the source repository.
