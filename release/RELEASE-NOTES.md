# Tellius Modding v0.2.0

This release substantially expands the editor beyond the initial v0.1.0 build.

## Highlights

- Adds foundational Radiant Dawn support for game data, messages, conversations,
  portraits, event scripts, and disc/project detection.
- Adds campaign-building tools including chapter creation and flow, hubs, chapter
  parts and phases, deployment, AI, shops, flags, supports, and validation.
- Adds battle simulation, chapter playtesting through Dolphin, save editing, and
  many configurable game-code patches for Path of Radiance.
- Adds editors and previews for dialogue, maps, terrain and tilesets, models,
  animations, particles, music, sound effects, videos, DBX layouts, Rect resources,
  tutorials, staff credits, and Sound Room data.
- Adds Excel import/export, a standalone patch installer, and the expanded Tellius
  Archive with guided modding tutorials and technical documentation.
- Improves tileset swatch editing with inline fields, atlas overlays, zoom controls,
  swatch import, and safer save/discard handling.

## Install

Download **TelliusModding-Windows-x64.zip**, extract it completely, and open
**TelliusModding.exe**. Python and the app's Python dependencies are included; no
pip commands or administrator access are needed.

On first launch, choose **Download missing tools** to install WIT and optional
FFmpeg directly from their upstream sites. Downloads are checksum-verified.
Internet access is needed for this setup step. Game data is not included.

Keep the `_internal` folder next to the executable. The build is unsigned.
The accompanying `.sha256` file provides the ZIP checksum.

Documentation: https://klg-tellius.github.io/TelliusModding/
