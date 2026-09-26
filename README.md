# Tellius Modding

A Windows Python desktop editor for **Fire Emblem: Path of Radiance** and
**Fire Emblem: Radiant Dawn**, with documentation of their file formats and systems.

## Download for Windows

Download **TelliusModding-Windows-x64.zip** from the
[latest release](https://github.com/klg-tellius/TelliusModding/releases/latest),
extract the whole ZIP, and open **TelliusModding.exe**. Python and all Python
libraries are included; no pip commands or administrator access are needed.

On first launch, choose **Download missing tools** to get WIT and optional FFmpeg
from their upstream sites. This step needs internet access (about 125 MB total).
Keep the `_internal` folder next to the EXE. See the
[Windows release guide](docs/app/windows-release.md) for updates and build instructions.

## Run from source

Install Python with Tkinter support. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r App/requirements.txt
.\.venv\Scripts\python.exe App/main.py
```

Use **Settings > Disc and media tools** to download WIT and optional FFmpeg.
The source build also recognizes tools installed manually under `App/tools/`.

Supply your own game disc and keep extracted data and mod projects outside this
repository. See [project setup](docs/app/project-lifecycle.md),
[workspace features](docs/app/workspace-and-features.md), and
[known limitations](docs/app/known-bugs.md).

## Documentation

- [Documentation index](docs/README.md)
- [Scripting tutorial](docs/app/script-tutorial.md)
- [Script function reference](docs/app/script-call-reference.md)
- [Application architecture](app.md)

The [interactive Tellius Archive](https://klg-tellius.github.io/TelliusModding/)
is published with GitHub Pages. Its source is `docs/tellius_archive.html`. Download and open
it in a browser, or enable GitHub Pages in **Settings > Pages > Deploy from a
branch**, selecting **main** and **/docs**. GitHub's ordinary file viewer shows
HTML source; Pages runs the interactive reference.

Public documentation links to the corresponding Tellius Archive topics. Raw
research workspaces and game-derived dumps are not included.

## Verify

```powershell
Set-Location App
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests that require an external game corpus may skip when it is absent.

## Attribution and licensing

See [credits and research resources](CREDITS.md), including the DspTool MIT
notice and external-tool licenses. No project-wide open-source license has
been selected yet; third-party components retain their own terms. Fire Emblem
names identify the supported games. This is an independent project.
