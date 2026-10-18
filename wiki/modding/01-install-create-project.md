---
id: "modding-install-create-project"
title: "Install the app and create a project"
description: "Install the complete app, separate source and workspace, and verify a clean extraction"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "start-safely"
tutorial_stage: "draft"
prerequisites: []
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/01-install-create-project.md"
---
# Install the app and create a project

**Route:** Launcher → New project; Home → Disc & Patch

## What you will make

You will create one disposable Path of Radiance practice project, connect it to your legally obtained source image, extract the game, and confirm that the workspace exposes its chapter and data editors. The source image, editable project, and later build output will live at three distinct paths.

## Before you begin

Prepare a supported Path of Radiance disc image (`.iso`, `.gcm`, `.ciso`, `.wdf`, or `.wia`), enough free space for both extraction and later builds, and a short local project path you can back up. Do not place the project inside the app installation or inside the source-disc folder.

Download the current Windows x64 archive from the project's [release page](https://github.com/klg-tellius/TelliusModding/releases/latest). Extract the entire ZIP. `TelliusModding.exe` depends on the adjacent `_internal` directory; moving only the executable creates an incomplete installation.

## How the editor fits together

The installation contains the app and helpers. The project directory contains metadata, an `extracted` working tree, original-file snapshots made during supported writes, and a build-output directory. The source image remains an immutable input. WIT performs disc extraction and packing; optional FFmpeg support is for media workflows.

Extraction unlocks the editor because pages are built from files in the extracted tree. A project record alone cannot supply Chapters, Characters, or Game Data. Re-extraction is a reset from the source image, not a refresh of the UI.

## Guided walkthrough

1. Launch `TelliusModding.exe`. If setup offers **Download missing tools**, install WIT; install FFmpeg as well if you plan audio or video work.
2. Select **New project**. Choose **Path of Radiance**. Enter a descriptive **Project name**, such as `Tutorial Clean Baseline`.
3. Set **Create in** to the parent folder that will hold projects. Read **Project folder** before continuing: the app sanitizes the name into this final child-folder path. Ensure it is neither the source-image location nor an existing mod folder.
4. Select **Create Project**. On **Disc & Patch**, choose **Choose disc image…** and select your owned image. Confirm the displayed path is the intended region/revision.
5. Select **Extract** and let the operation finish. Do not close the app or move the source/project during this operation.
6. Confirm that the sidebar now includes **Chapters**, **Characters**, **Game Data**, **Assets**, and **Tools**, not only Home and Disc & Patch.
7. Open one chapter and one character without changing them. Run **Tools → Check → Run check** and record the baseline results. Keep this project or a full copy as the clean comparison for later tutorials.

## Understand every control

| Control | Meaning | Decision rule |
| --- | --- | --- |
| Game | selects the data profile and supported surfaces | choose the game matching the image; it is not a display label |
| Project name | human-readable name and basis for folder name | use a unique, recognizable baseline name |
| Create in | parent directory | choose a backed-up, writable local location |
| Project folder | computed final path | inspect it for collisions before creation |
| Choose disc image… | stores the source-image path | keep the image after extraction; patch creation needs it |
| Extract | expands the source into the working tree | use once for initial setup |
| Re-extract | overwrites extracted files from the source | use only when intentionally discarding current extracted edits |

## Interactions and precedence

The chosen game determines how extracted files are interpreted; changing filenames cannot convert a disc between games. The source image is not edited. Editors write into the extracted tree, and builds later read that tree. A copied project that still points to a moved source may edit normally but cannot create a comparison patch until the source path is repaired.

## Test matrix

| Check | Expected result |
| --- | --- |
| Launch beside `_internal` | app opens without missing-runtime errors |
| Create a uniquely named project | preview matches the new directory |
| Extract supported image | full workspace navigation appears |
| Open chapter and character | records load without writing |
| Run project check | baseline is recorded for later comparison |
| Verify paths | source, project, and future build locations are distinct |

## Troubleshooting

If the executable fails after being moved, restore it beside the complete `_internal` directory. If **Extract** is disabled, choose a source image first. If extraction fails, preserve the exact message, confirm free space and file readability, and verify the image matches the selected game. If only Home and Disc & Patch appear afterward, extraction did not produce the required tree.

Never use **Re-extract** as a first response to one broken resource: it overwrites edited extracted files and can destroy the evidence needed to diagnose the failure.

## Save, build, and revert

No game edits are required here. Close and reopen the project to confirm its identity persists. Make a full baseline copy after extraction, or commit the appropriate project artifacts to version control. Reverting installation files does not revert the project; reverting the project does not restore the app.

## Limits and confidence

Project creation, folder sanitization, extraction gating, and re-extraction behavior are source-reviewed. Exact disc compatibility still depends on the image and installed WIT build. This lesson does not establish redistribution rights: share patches, not game images or extracted copyrighted files.

## Related tutorials and references

- [Tour the workspace](02-workspace-tour.md)
- [Save changes and restore originals](03-saving-and-restoring.md)
- [Set up Dolphin and build the game](04-dolphin-setup.md)
- [Disc Layout](../meta/disc-layout.md)

---

[All tutorials](index.md) · [Next: Tour the workspace →](02-workspace-tour.md)
