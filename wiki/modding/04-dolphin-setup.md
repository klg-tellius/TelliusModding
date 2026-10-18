---
id: "modding-dolphin-setup"
title: "Set up Dolphin and build the game"
description: "Configure repeatable builds, establish a clean boot baseline, and control emulator state"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tutorial_kind: "task"
tutorial_track: "start-safely"
tutorial_stage: "draft"
prerequisites: ["modding-saving-and-restoring"]
verification: ["source-reviewed", "unknown"]
tags: ["Guide", "Dolphin", "Build", "Modding app"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/04-dolphin-setup.md"
---
# Set up Dolphin and build the game

**Route:** Settings → Dolphin; Home → Disc & Patch → Build

## What you will make

You will build an unmodified extracted project, boot that exact image in Dolphin, and record a baseline launch profile. This separates installation, packing, emulator, save-state, and mod defects before real edits are introduced.

## Before you begin

Finish extraction and preserve a clean project checkpoint. Install a compatible Dolphin build from its official distribution. Decide where build outputs will live and remove ambiguity by using distinct filenames or archived timestamps. Keep enough space for the packed image.

## How the editor fits together

**Build disc** asks WIT to pack the current extracted tree into the project's build directory. **Build and play in Dolphin** performs the build and launches the configured executable. Neither action saves open editors first. Dolphin loads the image chosen at launch plus its own memory-card/save-state configuration.

The original GameCube image capacity is 1,459,978,240 bytes. A build warning about exceeding it matters for physical media/hardware constraints even if an emulator happens to boot it.

## Guided walkthrough

1. Open **Settings** and set the Dolphin executable to the actual `Dolphin.exe`, not its folder or a shortcut with uncertain arguments.
2. Return to **Disc & Patch**. Confirm the source card says extraction is complete and the build card shows the expected output directory.
3. With the clean project unchanged, select **Build disc**. Record start/end time, output filename, size, and any warning. Do not reuse a filename if you cannot distinguish it from an older image.
4. Launch the output manually in Dolphin once. Confirm region/title, reach the title screen, start a new game, and enter an early controllable scene. This is the clean boot baseline.
5. Close Dolphin fully. Select **Build and play in Dolphin** and confirm it launches the same newly built output.
6. Make one harmless visible edit from a later lesson only after the baseline exists. Save its owner, run **Check**, rebuild to a distinct output, and compare old/new images using the same Dolphin configuration.
7. For changes affected by progression, repeat from a fresh in-game save or a documented chapter-jump procedure. Do not use an arbitrary emulator save state as the sole proof.

## Understand every control

| Control/state | Function | Evidence to record |
| --- | --- | --- |
| Dolphin path | executable launched by Play | absolute executable path/version |
| Output folder | location of packed images | exact image name/time |
| Build disc | packs saved extracted files | completion log, size, warning |
| Build and play | builds then invokes Dolphin | image launched and emulator version |
| Memory card | persistent game save | slot and clean/continued state |
| Emulator save state | captures RAM and execution | never confuse with a fresh boot |
| Disc-size warning | reports output beyond original capacity | size and target environment |

## Interactions and precedence

Open editor memory is lower priority than the saved extracted file; the build cannot pack what was never saved. The newly built image is separate from every prior output. Dolphin save data may contain recruited units, flags, clear history, or cached progress that masks changed starting data. Emulator save states are even stronger snapshots and can bypass initialization entirely.

## Test matrix

| Build/run | Save state | Expected result |
| --- | --- | --- |
| clean baseline | new game | title and early scene boot |
| clean baseline | existing game save | existing progression loads |
| edited saved project, old image | same save | old image remains unchanged |
| edited saved project, new image | fresh save | edit appears if its initialization path runs |
| new image | emulator state made on old image | result is inconclusive; cold boot instead |

## Troubleshooting

If **Build** is disabled, extraction is incomplete or another task is running. If Play cannot find Dolphin, repair the executable setting. If the build succeeds but the launched content is old, compare the image path and modification time. If the new image boots but a data edit is absent, close/reopen its editor, confirm Save, and use a fresh game save.

If the image exceeds disc capacity, reduce large movies, streams, or textures and rebuild; emulator success does not establish hardware safety. Preserve build logs when WIT fails rather than re-extracting immediately.

## Save, build, and revert

The dependable order is Save owner → Run check → Build → verify exact output → cold launch. Keep the last clean image and last known-good edited image. Revert project resources before rebuilding; deleting a bad output alone does not revert source edits.

## Limits and confidence

Build controls, output location, Dolphin launch requirement, and capacity threshold are source-reviewed. Emulator compatibility varies by Dolphin version and settings. A Dolphin pass is not a physical-hardware certification, and a boot pass does not exercise later chapters or paths.

## Related tutorials and references

- [Save changes and restore originals](03-saving-and-restoring.md)
- [Check a project and fix problems](05-check-project.md)
- [Test a multi-chapter campaign](62-mini-campaign.md)
- [Disc Layout](../meta/disc-layout.md)

---

[← Previous: Save changes and restore originals](03-saving-and-restoring.md) · [All tutorials](index.md) · [Next: Check a project and fix problems →](05-check-project.md)
