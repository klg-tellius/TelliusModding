# Project lifecycle

Read this file only for work involving project creation, loading, disc extraction, disc building, or per-game configuration.

## Project layout

A mod project is a directory. New projects use the input/output layout (layout 2):

- `project.json` — project name, game, description, creation time, the absolute path of the source disc image (it is not copied) and the key of the vanilla store the project reads.
- `output/` — only the files the mod replaced or added, at their disc paths (`output/files/...`). Every editor writes here.
- `overlay.json` — the disc files the mod removed, and the vanilla file each replaced file was made from.
- `build/` — rebuilt disc images and patches, and `build/stage`, the merged tree (vanilla files linked, `output/` laid over them) that a build and Dolphin read.

The vanilla files are extracted once per disc into a shared, read-only store (`fe_modding/vanilla_store.py`, folder set in **Settings › Vanilla files**), or registered from a folder the user already extracted. Every project made from that disc reads it.

Older projects use layout 1: the whole disc unpacked in the project's `extracted/` and edited in place, with `originals/` holding the first copy of each file a model import overwrote. Both layouts open; `ModProject.is_overlay` tells them apart.

`fe_modding/project.py` owns this lifecycle. Project directory names are derived from the user-provided project name and sanitized for the filesystem.

## Supported games and discs

`fe_modding/games.py` is the source of truth for game-specific settings. Other modules should not duplicate platform or disc-format decisions.

- Path of Radiance accepts ISO, GCM, CISO, WDF, WIA and RVZ sources and builds CISO.
- Radiant Dawn accepts ISO, WBFS, CISO, WDF, WIA and RVZ sources and builds WBFS. WIT cannot read RVZ, so the app first converts it to a temporary ISO with DolphinTool (next to the configured Dolphin.exe). A Wii disc is extracted from its DATA partition, and the extraction is checked for `sys/`, `files/`, `disc/`, `ticket.bin`, `tmd.bin` and `cert.bin`. Per-game file names, chapter ids and supported features live in a `GameProfile` (`fe_modding/game_profile.py`, `project.profile`); `project.read_logical` / `write_logical` handle Radiant Dawn's LZ10-compressed `.cms` files. Choosing or extracting a disc of the other game (disc ID `GFE*` vs `RFE*` in `sys/boot.bin`) shows a warning.
- RVZ is not supported by the bundled WIT version, on either game: the app converts it with DolphinTool first.

## Workflow

1. Create or open a project.
2. Select a supported source disc image. The project records its path; the image is not copied.
3. Extract the disc into the shared vanilla store (or into `extracted/` on layout 1). A disc already in the store is not extracted again.
4. Modify files through the workspace: changed files are written to `output/`.
5. Build the vanilla files with `output/` laid over them into `build/`, or make a patch to share the mod.

Extraction uses WIT. Radiant Dawn builds use WIT too, but Path of Radiance builds use the app's own GameCube composer (`fe_modding/formats/gcdisc.py`), because WIT composes every extracted folder as a Wii disc, and Dolphin crashes on boot with those images. Before composing, a Path of Radiance build copies any edited loose file that `system.cmp` also bundles (`FE8Data.bin`, `FE8Anim.bin`, `mess/common.m`...) into `system.cmp` (`ModProject.sync_system_archive`), because the game reads the bundled copies. A build whose data is larger than a GameCube disc (1,459,978,240 bytes) is still written and runs in Dolphin, but the app warns that it won't fit real hardware. Both run without blocking the Tkinter interface. Recent-project information is managed by `fe_modding/config.py`.

## Patches

`fe_modding/patch.py` makes and applies `.tpatch` files so a mod can be shared without the game. A patch is a zip holding every file of `extracted/` that differs from the retail disc (replaced or added, stored whole under `files/<path>`) and a `manifest.json`: the game, the base disc's ID and revision (`sys/boot.bin`, e.g. `GFEE01 rev 1`), the SHA-1 of each patched file, and the SHA-1 of each retail file it replaces or removes.

- **Create** (`create_project_patch`): syncs `system.cmp` as a Path of Radiance build does, extracts the project's source disc again into a temporary folder inside the project, and compares the two trees file by file. The source disc image must still be at the path the project recorded.
- **Apply** (`apply_patch_to_disc`): extracts the player's disc into a temporary folder next to the output, refuses a different disc ID or any replaced/removed file whose hash differs (before writing anything), writes the patch's files, checks their hashes, and builds with the same code as a project build (`project.build_image`). The result is byte-identical to building the project. Also runnable as `python -m fe_modding.patch apply PATCH DISC OUTPUT` from `App/`.

The patch is file-level rather than a byte-level diff (xdelta, BPS) because a build re-lays out the disc: one resized file moves every file after it. Applying therefore needs this app (or its `fe_modding` package); a patch only carries the mod's changed files, so its size is that of those files, compressed.
