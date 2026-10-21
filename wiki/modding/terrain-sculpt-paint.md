---
id: "modding-terrain-sculpt-paint"
title: "Sculpt and paint a terrain in Blender"
description: "Make a terrain kit, sculpt hills and valleys, paint the ground with the map's own atlas, and import the result with the game's texturing"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Maps", "Terrain mesh", "Blender"]
aliases: []
status: "draft"
last_reviewed: "2026-10-20"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/terrain-sculpt-paint.md"
tutorial_kind: "task"
tutorial_track: "maps"
tutorial_stage: "draft"
prerequisites: ["modding-terrain-mesh", "modding-blender-round-trip"]
verification: ["source-reviewed", "app-tested", "unknown"]
---
# Sculpt and paint a terrain in Blender

**Routes:** Assets → 3D Models → `zmap/<map>` → **Sculpt & paint kit…** / **Atlas swatches…** / **Import .blend/.glb…**; Settings → Preferences → 3D tools; Blender → 3D View sidebar → **Tellius** tab

## What you will make

You will raise one hill outside the Prologue's playable area (`zmap/bmap01`), paint a dirt path across it with the map's own road texture, check in Blender what the game will draw, and import the result. The import review shows the compiled terrain from above before anything is written.

The exercise teaches the one rule that shapes every painted terrain: the game shows at most **two** atlas textures at any point of the ground. You can paint as many layers as you like; the app compiles them into those two and shows where it could not.

## Before you begin

- Complete [Replace a terrain mesh safely](25-terrain-mesh.md) and [Round-trip a model through Blender safely](51-blender-round-trip.md).
- Install Blender 4.2 or newer and set its location under **Settings → Preferences → 3D tools → Blender location**. The workflow was checked with Blender 5.2.
- In the same section, click **Install the Tellius Terrain add-on**. It installs and enables the add-on in your Blender preferences; restart Blender if it is open. Click it again after each app update.
- Use a disposable project checkpoint. The import rewrites the map's `map.cmp`: its terrain model, `texpack.tpl` and `map.bin` heights.
- Record the Prologue's look around its north-west corner and one unit route through the playable area, so you can compare after the import.

## How the editor fits together

### What the game draws

The land terrain's `map_base` material samples one **atlas** image twice. Each corner of every triangle has two texture coordinates, UV0 and UV1. A greyscale **mask**, laid over the map from above, chooses between the two samples: black shows UV0, white shows UV1. A **light overlay**, also laid from above, darkens the result for shadows. See [Terrain Texture Rendering](../systems/terrain-texture-rendering.md).

On outdoor maps the atlas holds tileable **swatches**: one large ground image in its top half (grass on the Prologue) and smaller ones below it (dirt road, rocks, flowers). Vanilla terrains lay every swatch from above at 6.4 atlas pixels per unit, so a 128-pixel swatch repeats every 20 units and the 512-pixel ground every 80 units. One map tile is 5 units.

Three consequences follow, and the tools are built around them:

1. A triangle shows at most two swatches, one per UV set, so its texture choice has hard edges.
2. The mask gives soft transitions, but only 0.8 mask pixels per unit (four per tile).
3. A triangle cannot cross a swatch's repeat line, so the app cuts the terrain on those lines.

### Layers instead of UVs

You never edit UV0, UV1 or the mask by hand. You paint **layers**: each layer is one swatch plus a greyscale weight image covering the same 640 × 640 units as the mask, at twice its detail. The first layer is the **base**: it shows wherever the layers above leave room. Layers lower in the list are painted over the ones above them, like layers in an image editor.

Because layers are laid over the map from above, paint does not belong to the mesh. You can sculpt, reduce or replace the mesh after painting and the paint stays where it was.

When you import, the app compiles the layers: per triangle it draws the base through UV0 and the strongest other layer through UV1, and turns the layer weights into the mask. Where three layers overlap and the base is still visible, one of them is lost; that spot is a **conflict**.

### Files and objects

| Thing | Where | Role |
| --- | --- | --- |
| Terrain kit | the `.blend` you save | Sculpt mesh, layers, atlas, light overlay and map settings |
| **FE9 Sculpt** | kit, **FE9 Terrain Kit** collection | A grid seeded from the current ground; sculpt this |
| **FE9 Game Mesh** | same collection, hidden | The sculpt reduced to the triangle budget; the import converts this |
| **FE9 Reference** | collection | The original terrain (hidden), the playable tile grid and any context props; never exported back |
| Swatch table | `terrain_paint/<map>.json` in the project | Which atlas rectangles can be painted; saved by **Atlas swatches…** |
| Custom atlas | `terrain_paint/<map>_atlas.png` in the project | Made by the atlas builder; replaces the game's atlas on import |

Nothing changes in the project until **Write files** in the import review.

## Guided walkthrough

### 1. Check the swatches

In **Assets → 3D Models**, search for `zmap/bmap01` and select it. Click **Atlas swatches…**.

The dialog shows the atlas with every swatch outlined: blue for the base, yellow for the others, red for the selected one. For the Prologue, detection finds the grass base (`0, 0`, 512 × 512) and three bottom-half swatches, including the dirt road at `0, 768` and the rock at `256, 768`.

Select the swatch at `0, 768`, type `Road` in **Name**, and click **Apply**. Rename the one at `256, 768` to `Rock`. Click **Add unused 128 cells** to make the atlas's other textures paintable too. Click **Save**, then **Close**.

*Observe:* the status line reads "Saved in the project." The names you chose appear in the Blender layer list from now on.

### 2. Make the kit

With `zmap/bmap01` still selected, click **Sculpt & paint kit…**. Choose **Start from the map's current painting**, set **Sculpt grid spacing** to **2 units**, leave the context object list unselected, and click **Continue**. Save as `bmap01_terrain_kit.blend` outside the project folder.

*Observe:* after a few seconds the app confirms the file. Open it in Blender. The viewport shows **FE9 Sculpt** textured like the game map, with the playable tiles outlined. The sidebar (press **N**) has a **Tellius** tab whose **FE9 Terrain** panel names the map.

### 3. Sculpt a hill

Select **FE9 Sculpt**, switch to Sculpt Mode, and use the **Draw** or **Inflate** brush to raise a hill about 20 units high near the map's north-west corner (low X, high Y in Blender's top view), outside the tile grid. Return to Object Mode.

Inside the playable area the import flattens the ground onto one flat panel per half tile, because units stand on those panels. To see them, click **Show Tile Panels** in the **Game Check** panel: a wireframe of the panels appears over the sculpt. Keep tactical changes deliberate; see [Edit tile heights and slopes](23-tile-heights.md).

*Observe:* the painted textures follow the new shape, because they are laid from above.

### 4. Paint a path

In **Paint Layers**, select the `Road` layer and click **Paint Layer**. Blender switches to Texture Paint with that layer's weights as the canvas and a white brush.

Paint a path about 8 units wide across the hill. **Paint in** sets the brush to white (more road), **Erase** to black (less road). Brush size and strength are Blender's own.

*Observe:* the road texture appears where you paint. With **Show light overlay** ticked, the map's shadows stay on top.

If a layer is missing, click **+** and choose its swatch. The swatch button beside **Paint Layer** changes the selected layer's swatch. The eye icon hides a layer; the slope icon (**Cliffs**) makes the layer cover steep faces on its own.

### 5. Check what the game will draw

Click **Game Preview**. The add-on compiles the layers as the import will and shows the result on a separate **FE9 Game Preview** object. The panel lists the triangle count after the swatch cuts, the swatches used, and the share of the map in conflict. With **Show conflicts in red**, conflict spots are tinted red.

If the path crosses the rock with grass still showing, you will see red where all three meet. Fix it by painting the base between them (erase one of the two layers there), or let one layer cover the other fully. Click the **X** beside **Game Preview** to go back to painting; **Paint Layer** also removes the preview.

### 6. Fit the budget and save

Leave **Triangle budget** at its default (the map's own terrain triangle count, at least 9,000) and click **Make Game Mesh**. The add-on reduces a hidden copy of the sculpt until, once cut on the swatch repeat lines, it has about that many triangles.

Optional: in **Light Overlay**, set **Sun direction** `225`, **Sun height** `40`, **Shadow darkness** `0.35`, and click **Bake Light Overlay** to shade the new hill. This replaces the map's old shadows, including those of props, which the bake does not see.

Click **Save Kit** in **FE9 Terrain**. It packs the painted images into the file and saves it; **File → Save** also packs them.

### 7. Import and review

Back in the app, select `zmap/bmap01`, click **Import .blend/.glb…**, and choose the kit. Blender runs in the background, then **Painted terrain import** opens. Keep both height options ticked. Under **Light overlay**, choose **The kit's light overlay** if you baked one, else **The map's current light overlay**. Click **Continue**.

The **Import Review** opens on its **Texturing** tab: **What the game draws**, **The layers as painted**, **Conflicts (red)** and **Compiled mask**, all seen from above, with the compile report. Read the **Changes** and **Warnings** tabs as in the terrain-mesh lesson, then click **Write files**.

*Observe:* the 3D Models preview reloads with the hill and the path. Build an image and look at the hill in Dolphin.

## Understand every control

### In the app

| Control | Meaning | How to choose | Confidence |
| --- | --- | --- | --- |
| **Install the Tellius Terrain add-on** (Settings) | Installs and enables the add-on in your Blender preferences | Once, and after each app update | app-tested |
| **Atlas swatches…** | Edits the map's swatch table: **Name**, **x**, **y**, **w**, **h**, **Apply**, **Add swatch**, **Remove**, **Set as base** | Keep sizes that divide each other (64, 128, 256, 512): the cut lines follow the smallest common repeat, so odd sizes add triangles | source-reviewed |
| **Detect again** | Rebuilds the table from the map's own UVs | After experimenting; it reads the game's terrain, not a custom atlas | app-tested |
| **Add unused 128 cells** | Adds a swatch for each 128-pixel atlas square no swatch touches | To paint textures the vanilla map never used | source-reviewed |
| **Build custom atlas…** | Composes a new 512 × 1024 atlas: a base image (made 512 × 512) and swatch images (each made square at 64, 128 or 256), packed below it | For new ground textures; images should tile seamlessly | source-reviewed; untested in game |
| **Use the game's atlas** | Drops the custom atlas and detects the game's swatches | To return to vanilla textures | source-reviewed |
| **Save** / **Close** | Writes the table (and custom atlas) to the project / closes without saving | Save before making a kit | app-tested |
| **Sculpt & paint kit…** | Writes a kit `.blend` | Start from the current painting to keep the map's look; from the base only for a new design | app-tested |
| **Sculpt grid spacing** | Units between sculpt vertices | **2 units**; **1 unit** for fine detail on small maps (slower in Blender); **4 units** for broad shapes | app-tested |
| Context objects | Props shown in the kit for reference | Pick the ones near your edit; they are never exported back | source-reviewed |
| **Import .blend/.glb…** | Recognises a kit and compiles its paint | Choose the saved kit | app-tested |
| **Move tile heights and props with the new ground** | Updates `map.bin` heights and prop heights from the new surface | Keep on unless you only change looks outside the playable area | source-reviewed |
| **Fit the playable area to the tile grid** | Flattens the playable ground onto the half-tile panels | Keep on: units and the move grid use those panels | source-reviewed |
| **Light overlay** choices | The kit's overlay, the map's current one, or none (white) | The kit's after a bake; the current one when the ground shape barely changed | source-reviewed |
| **Texturing** tab | Top-down views and the compile report | Compare **What the game draws** with **The layers as painted**; any red in **Conflicts** is lost paint | app-tested |

### In Blender (Tellius tab)

| Control | Meaning | How to choose | Confidence |
| --- | --- | --- | --- |
| **Save Kit** | Packs painted images and saves | Before importing | app-tested |
| Layer list | Name, swatch, **Cliffs** and visibility per layer; the first row is the base | Few layers: each extra one is another chance of conflicts | app-tested |
| **+** / **−** / arrows | Add a layer for a swatch, remove one, reorder | Rare details (flowers, road) belong below common ones (rock, sand) so they are painted over them | app-tested |
| **Paint Layer** | Texture-paints the selected layer on **FE9 Sculpt** | Select a layer above the base | app-tested |
| Swatch button | Changes the selected layer's swatch | To try another texture without repainting | source-reviewed |
| **Paint in** / **Erase** | Brush colour white / black | White adds the layer, black removes it | source-reviewed |
| **Show light overlay** | Multiplies the light overlay in the preview | Turn off to judge colours alone | app-tested |
| **Refresh Material** | Rebuilds the preview material | After renaming images or if the viewport looks stale | source-reviewed |
| **Auto Paint**: **Slope** / **Height**, **From**, **To**, combine | Fills the selected layer from the terrain: slope in degrees, or height in game units (below **From** full, above **To** none) | Rock: Slope from 30 to 45, **Add to the layer**; sand: Height from 0 to 3 | app-tested |
| **Game Preview** / **X** | Compiles as the import will onto a preview object / removes it | Before every save | app-tested |
| **Show conflicts in red** | Tints conflict spots in the preview | Keep on | app-tested |
| **Triangle budget** | Triangles after the swatch cuts | Vanilla terrains have 6,000 to 21,000; stay near the map's own count | app-tested |
| **Make Game Mesh** | Reduces a hidden copy of the sculpt to the budget | After sculpting; the import makes one itself if the sculpt changed since | app-tested |
| **Show Tile Panels** | Shows the flat panels units will stand on | Inspect after sculpting inside the playable area | app-tested |
| **Sun direction**, **Sun height**, **Shadow darkness**, **Bake Light Overlay** | Bakes sun shading and terrain shadows into the light overlay | Vanilla's darkest shadows are about 0.3; keep **Shadow darkness** near 0.35 | app-tested |
| **Atlas Pieces**: **Side projection above (degrees)**, **Apply Swatch to Faces** | For a plain map `.blend` (Export .blend…): lays one swatch on the selected faces through both UV sets | Indoor floors and walls; select faces smaller than one swatch repeat | source-reviewed |

## Things to try next

1. **Cliff rock:** add a `Rock` layer, tick its **Cliffs** icon, and auto-paint it by slope from 30 to 45. Faces steeper than 50° then show rock from the side instead of a stretched top-down texture.
2. **Base only:** make a kit with **Start from the base ground only** and paint a new road network on a blank map.
3. **Custom textures:** build an atlas from your own seamless images in **Atlas swatches…**, save, make a kit, and paint with them.
4. **Indoor floors:** export a plain `.blend` of an indoor map and use **Atlas Pieces** on a few floor faces.

## Interactions and precedence

- A kit replaces the **whole** terrain model with the sculpted mesh and one `map_base` material. Terrains with a separate `map_wall` material lose those walls; use the plain [Blender round trip](51-blender-round-trip.md) and **Atlas Pieces** for them.
- The base layer is drawn through UV0 wherever it is visible. Two detail layers can share a triangle only where the base no longer shows.
- The import cuts every triangle on the swatch repeat lines, then fits the playable area to the tiles. The budget covers the first step only, so a large playable area adds triangles the add-on does not count.
- **Move tile heights** reads the compiled surface. Painting never moves heights; sculpting does.
- The swatch table is per project and per map. A kit carries a copy of it, so editing the table later does not change kits you already made.
- The light overlay covers the area its map projection defines, which can be smaller than the terrain; the bake fills what that projection covers.

## Test matrix

| Case | Setup | Expected observation |
| --- | --- | --- |
| Baseline | Kit from the current painting, no edits, import with the current light overlay | **What the game draws** matches the map's look; the report shows no conflicts |
| Intended | Hill and road path from the walkthrough | Hill and path appear in the preview and in the game |
| Boundary | Raise a 30-unit cliff and give it a **Cliffs** layer | Steep faces use one swatch from the side; triangles stay within budget |
| Failure | Paint road and flowers fully over the same patch of grass | Conflicts are reported in red; only two of the textures show there |

## Troubleshooting

| Symptom | Inspect | Correction |
| --- | --- | --- |
| No **Tellius** tab in Blender | Edit → Preferences → Add-ons | Click **Install the Tellius Terrain add-on** again and restart Blender |
| "This file is not a terrain kit" | The file was made by **Export .blend…** | Make a kit with **Sculpt & paint kit…** |
| Painting does nothing | Selected layer | The base cannot be painted; select a layer below it |
| Red areas in the preview | Overlapping layers | Erase one layer there, or paint the base between them |
| Too many triangles | **Game Preview** report, **Changes** tab | Lower **Triangle budget** or use larger swatches |
| Units stand above or below the ground | Tile panels, **Warnings** | Re-import with **Move tile heights** ticked; check [tile heights](23-tile-heights.md) |
| Shadows from the old map remain | Light overlay choice | Bake a new overlay or choose none |

## Save, build, and revert

Painting and saving in Blender write only the kit file. **Write files** in the import review writes `map.cmp` and keeps the extracted original in the project's originals folder. **Restore original…** in 3D Models puts it back. Build a new image to see the result in Dolphin; the app preview does not change an existing image.

## Limits and confidence

- **App-tested** (Blender 5.2, Prologue): kit export, painting with a real brush stroke, game preview, game mesh, light bake, conversion, and import review.
- **Source-reviewed**: the compile rules (two swatches per triangle, mask from layer weights, swatch cuts) follow the decoded `map_base` blend. Recompiling the Prologue's own layers reproduces its look closely in the app's renderer.
- **Unknown**: none of this has been checked in Dolphin yet: painted textures, custom atlases, baked light overlays, triangle counts above the map's own, and sculpted ground with moved heights.
- The bake shades terrain only; props cast no shadows into it.

## Related tutorials and references

- Prerequisites: [Replace a terrain mesh safely](25-terrain-mesh.md), [Round-trip a model through Blender safely](51-blender-round-trip.md)
- Continue with: [Edit tile heights and slopes](23-tile-heights.md), [Place, copy, and import props](24-map-props.md)
- References: [Terrain Texture Rendering](../systems/terrain-texture-rendering.md), [Map Format](../formats/map-format.md)

---

[All curriculum tracks](index.md)
