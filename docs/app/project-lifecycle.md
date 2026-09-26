# Project lifecycle

Read this file only for work involving project creation, loading, disc extraction, disc building, or per-game configuration.

## Project layout

A mod project is a directory containing:

- `project.json` — project name, game, description, creation time, and source-disc filename.
- `source/` — a copied source disc image.
- `extracted/` — unpacked game files edited by the application.
- `build/` — rebuilt disc images.
- `originals/` — created by the first model import: each file an import overwrote, as it was extracted, at the same relative path. The 3D Models panel restores from it.

`fe_modding/project.py` owns this lifecycle. Project directory names are derived from the user-provided project name and sanitized for the filesystem.

## Supported games and discs

`fe_modding/games.py` is the source of truth for game-specific settings. Other modules should not duplicate platform or disc-format decisions.

- Path of Radiance accepts ISO, GCM, CISO, WDF, and WIA sources and builds CISO.
- Radiant Dawn accepts ISO, WBFS, CISO, WDF, and WIA sources and builds WBFS.
- RVZ is not supported by the bundled WIT version.

## Workflow

1. Create or open a project.
2. Select a supported source disc image. The app copies it into `source/`.
3. Extract the disc into `extracted/`.
4. Modify extracted files through the workspace.
5. Build the current `extracted/` contents into `build/`, or make a patch to share the mod.

Extraction uses WIT. Radiant Dawn builds use WIT too, but Path of Radiance builds use the app's own GameCube composer (`fe_modding/formats/gcdisc.py`), because WIT composes every extracted folder as a Wii disc, and Dolphin crashes on boot with those images. Before composing, a Path of Radiance build copies any edited loose file that `system.cmp` also bundles (`FE8Data.bin`, `FE8Anim.bin`, `mess/common.m`...) into `system.cmp` (`ModProject.sync_system_archive`), because the game reads the bundled copies. A build whose data is larger than a GameCube disc (1,459,978,240 bytes) is still written and runs in Dolphin, but the app warns that it won't fit real hardware. Both run without blocking the Tkinter interface. Recent-project information is managed by `fe_modding/config.py`.

## Patches

`fe_modding/patch.py` makes and applies `.tpatch` files so a mod can be shared without the game. A patch is a zip holding every file of `extracted/` that differs from the retail disc (replaced or added, stored whole under `files/<path>`) and a `manifest.json`: the game, the base disc's ID and revision (`sys/boot.bin`, e.g. `GFEE01 rev 1`), the SHA-1 of each patched file, and the SHA-1 of each retail file it replaces or removes.

- **Create** (`create_project_patch`): syncs `system.cmp` as a Path of Radiance build does, extracts the project's source disc again into a temporary folder inside the project, and compares the two trees file by file. The source disc must still be in `source/`.
- **Apply** (`apply_patch_to_disc`): extracts the player's disc into a temporary folder next to the output, refuses a different disc ID or any replaced/removed file whose hash differs (before writing anything), writes the patch's files, checks their hashes, and builds with the same code as a project build (`project.build_image`). The result is byte-identical to building the project. Also runnable as `python -m fe_modding.patch apply PATCH DISC OUTPUT` from `App/`.

The patch is file-level rather than a byte-level diff (xdelta, BPS) because a build re-lays out the disc: one resized file moves every file after it. Applying therefore needs this app (or its `fe_modding` package); a patch only carries the mod's changed files, so its size is that of those files, compressed.
