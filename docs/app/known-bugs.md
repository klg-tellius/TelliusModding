# Known bugs

Open defects in the app that are confirmed but not yet fixed. Remove an entry once it is fixed.

## Oversized Path of Radiance builds are only warned about

- **Where:** `fe_modding/project.py`, `ModProject.build()`, and `fe_modding/formats/gcdisc.py`.
- **What:** if the extracted data is larger than a GameCube disc (1,459,978,240 bytes), the build is still written and the app shows a warning.
- **Impact:** such images run in Dolphin, but not on real hardware or in loaders that enforce the disc size. Large replacement videos are the usual cause.

## Map terrain .glb round trip changes how the ground looks

- **Where:** `fe_modding/gui/model_viewer.py`, `export_map_terrain_glb()` then `replace_map_terrain_with_glb()` (3D Models › Export .glb / Import .glb on a map).
- **Observed in game** (in-game checks B2/B2r, 2026-11-18): exporting chapter 1's (`bmap02`) terrain and importing the same file back turns the smooth grass/rock blending into blocky, patchy texturing (5.4% of the screen differs from retail). On RD's Prologue (`bmap0101`) the wall faces come out flatter and darker (1.1%).
- **Cause (from the import warnings):** the import renames `map_base` to `map_base_mesh` so the map loader doesn't project textures onto it, and bakes the textures into `texpack.tpl` instead (PoR: 3.1 MB, twice any retail map). The retail look comes from the projected, blended map texturing, which the round trip doesn't keep.
- **Impact:** an unchanged round trip is not invisible; edited terrain also loses the retail blending. Map *unit* models (B1/B1r) round-trip without a visible change.

## Radiant Dawn chapter weather shows no change

- **Where:** ChapterData `weather` (+0x9C), Chapter data page.
- **Observed in game** (W1r, 2026-11-18, and the parity run of 2026-10-28): the Prologue set from cloudy (`曇り`) to snow (`雪`) looks exactly like retail at the first player phase. What the field drives still needs a trace.

