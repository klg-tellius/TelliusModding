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
Keep the `_internal` folder next to the EXE. The ZIP also contains
`TelliusPatcher.exe`, which players use to apply a `.tpatch` mod to their own disc.

- [Release notes](release/RELEASE-NOTES.md)
- [Start-here notes shipped in the ZIP](release/START-HERE.txt)
- [Windows release guide](docs/app/windows-release.md): installing, updating, and
  how a release is built and published

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
repository.

## Tellius Archive (wiki)

The **Tellius Archive** is the project's wiki: modding tutorials, game systems and
file formats for both games.

- Read it online: <https://klg-tellius.github.io/TelliusModding/>
- Or browse its sources in this repository, starting from [wiki/index.md](wiki/index.md):
  - [Your first mod](wiki/guides/first-mod.md) and the other [learning paths](wiki/guides/learning-paths.md)
  - [Modding tutorials](wiki/modding/index.md): 80 step-by-step lessons
  - Game systems, such as [combat](wiki/systems/combat-mechanics.md),
    [events and scripting](wiki/systems/events-scripting.md) and
    [saves](wiki/systems/save-system.md)
  - File formats, such as [FE8Data.bin](wiki/formats/fe8data.md),
    [event scripts](wiki/formats/event-script.md) and [maps](wiki/formats/map-format.md)
  - [Radiant Dawn coverage](wiki/meta/radiant-dawn.md) and the
    [glossary](wiki/meta/glossary.md)

Spotted something wrong in an article? Use the
[Archive correction](https://github.com/klg-tellius/TelliusModding/issues/new?template=archive-correction.yml)
issue form, or see [Contributing](wiki/meta/contributing.md).

### Building the wiki

`mkdocs.yml` builds `wiki/` with Material for MkDocs. The **Tellius Archive**
GitHub Actions workflow ([wiki.yml](.github/workflows/wiki.yml)) validates every
pull request and deploys `main` to GitHub Pages. The repository's
**Settings > Pages > Source** must be set to **GitHub Actions**. To preview it
locally:

```powershell
python -m pip install -r requirements-wiki.txt
python App/tools/validate_wiki.py
mkdocs serve
```

Each article links to the browser editor. Trusted GitHub collaborators may
publish, while other GitHub users can propose a reviewed pull request through
Decap Open Authoring. OAuth deployment instructions are in
[infrastructure/oauth-worker/README.md](infrastructure/oauth-worker/README.md).

Raw research workspaces and game-derived dumps are not included in this repository.

## App documentation

- [Application architecture](app.md)
- [Workspace and features](docs/app/workspace-and-features.md)
- Feature notes (hub chapters, promotions, extended flags, item restrictions, particle
  and dialogue editors, 3D pipeline status) are in [App/docs](App/docs/)

## Feature requests, bugs and questions

Is there a feature you would like, a bug you hit, or something you want to ask?

- **Ideas and questions:** start a thread in
  [Discussions](https://github.com/klg-tellius/TelliusModding/discussions).
- **Bugs and concrete feature requests:** open an
  [issue](https://github.com/klg-tellius/TelliusModding/issues/new/choose).

Please say which game and region you use (for example Path of Radiance US or Radiant
Dawn PAL) and which release you run (for example v1.0.0.0, or the commit when running
from source). Do not attach game files.

## Verify

```powershell
Set-Location App
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests that require an external game corpus may skip when it is absent.

## Attribution and licensing

See [credits and research resources](CREDITS.md), including the DspTool MIT
notice and external-tool licenses. Original wiki text and diagrams are licensed
CC BY-SA 4.0 as described in [CONTENT-LICENSE.md](CONTENT-LICENSE.md). The code
is released under the [MIT License](LICENSE); third-party components retain their
own terms. Neither license covers Nintendo or Intelligent Systems game data,
trademarks or other game-derived material: supply your own disc. Fire Emblem names
identify the supported games. This is an independent project.
