# Terrain sculpt & paint: quick test plan

PR #100, branch `claude/blender-terrain-paint`. About 45 minutes. Map: the Prologue, `zmap/bmap01`.
Tick each box; for a failure, note the step number and take a screenshot.

**Where each Blender step happens.** Every Blender step starts with one of these:

- **Tellius:** a button or field in Blender's sidebar. Press **N** over the 3D view, open the **Tellius** tab, then find the named panel (FE9 Terrain, Paint Layers, Auto Paint, Game Check, Light Overlay, Water, Atlas Pieces).
- **Select:** click the named object, in the **Outliner** (top right) or in the 3D view.
- **Blender:** Blender's own interface, not the add-on: the mode menu at the top left of the 3D view (Object Mode, Sculpt Mode), the brush settings in the tool header, the timeline, the 3D cursor (Shift + right-click).

## 0. Setup (5 min)

- [ ] Run the app from the PR's worktree, which already has the branch checked out:
      `cd C:\Users\Julien\Documents\TelliusModding-terrain\App` then `python -m fe_modding`
- [ ] Open a **disposable copy** of your project, or make a checkpoint first. The import rewrites `zmap/bmap01/map.cmp`.
- [ ] **Settings → Preferences → 3D tools**: Blender location shows "Found: G:\blender\blender.exe".
- [ ] Click **Install the Tellius Terrain add-on**.
      Expect: after a few seconds, "Installed and enabled in …".
- [ ] Open Blender. **Edit → Preferences → Add-ons**: "Tellius Terrain" is listed and enabled.

## 1. App, before Blender (5 min)

- [ ] **Assets → 3D Models**, search `zmap/bmap01`, select it.
      Expect: **Sculpt & paint kit…** and **Atlas swatches…** are enabled. On `zu/fig1` they are greyed out.
- [ ] **Atlas swatches…**
      Expect: the atlas with a blue box on the grass (top half), plus yellow boxes on the dirt (`0, 768`) and the rock (`256, 768`).
- [ ] Select `0, 768`, rename it `Road`, click **Apply**. Rename `256, 768` to `Rock`. Click **Add unused 128 cells**, then **Save**.
      Expect: the status reads "Saved in the project". Close.
- [ ] **Sculpt & paint kit…**: choose "current painting" and **2 units**, then **Continue**. Save as `bmap01_kit.blend` on the Desktop.
      Expect: done in under 30 s, with a "Wrote …" message.

## 2. Blender (15 min)

**Blender:** open `bmap01_kit.blend` (File → Open). Press **N** over the 3D view and open the **Tellius** tab.

- [ ] The map looks like the game: grass, dirt patches, rock ridges. The playable tile grid is drawn in the middle.
      **Tellius → Paint Layers**: the list shows Rock, Road, Base from top to bottom: one layer per swatch the map already uses.
      The list reads like an art app's layers: a layer covers the ones below it, and Base is always at the bottom.
- [ ] The cells you added are swatches, not layers. **Tellius → Paint Layers**: click **+**. They are in the swatch list. Pick one to add it as a layer; it appears at the top.
- [ ] **Sculpt**:
      **Select:** **FE9 Sculpt** in the Outliner.
      **Blender:** switch the mode menu (top left of the 3D view) to **Sculpt Mode**. Press **7** on the numpad for the top view and raise a clear hill (about 20 m) in the **top-left corner**, well outside the tile grid, with the Draw brush. Switch the mode menu back to **Object Mode**.
      Expect: the textures follow the hill without stretching on the gentle slopes.
- [ ] **Paint**:
      **Tellius → Paint Layers**: click the **Road** row, then **Paint Layer**. This selects FE9 Sculpt and switches Blender to Texture Paint mode for you.
      **Blender:** paint with the left mouse button: a path from the hill to the tile grid, plus one short stroke **inside** the grid. The brush size and strength are in the tool header at the top of the 3D view.
      Expect: the road texture appears live. **Tellius → Paint Layers → Erase** turns the brush into an eraser, and **Paint in** turns it back.
- [ ] **Layer order**: **Tellius → Paint Layers**, with Road selected, click the **▲** arrow beside the list. Road moves above Rock and covers it where they overlap. Click **▼** to put it back.
- [ ] **Conflict test**: a layer painted at full strength hides everything under it, so that's not a conflict.
      Red appears only where three textures show **at once**, partly blended.
      **Tellius → Paint Layers**: click **+** and pick a flower or crop cell, then **Paint Layer**.
      **Blender:** set the brush **Strength** to `0.4` in the tool header and paint across the road's edge, where grass still shows.
      **Tellius → Game Check**: click **Game Preview**.
      Expect: red along that soft band. The panel reports a conflict percentage above 0.0%.
      Then paint the flowers again at strength `1.0` over the same spot. Expect: the red goes away there, because only flowers show.
      **Tellius → Game Check**: click **X** beside Game Preview. **Tellius → Paint Layers**: select the flower layer and click **−**. Run **Game Preview** again. Expect: no red left.
- [ ] **Auto Paint**: **Tellius → Paint Layers**: click the **Rock** row. **Tellius → Auto Paint**: choose **Slope** 30 → 45 and **Add to the layer**, then click **Auto Paint**.
      Expect: rock on the hill's steep sides.
- [ ] **Tellius → Game Check**: **Make Game Mesh** with the default budget.
      Expect: a message saying "about N triangles", with N close to the budget.
      **Game Preview**'s first line ("N triangles after cutting… (from M)") gives both numbers.
      On the Prologue with the default 9,000, M should be about 2,600. Before the 2026-10-21 fix it was about 1,700.
- [ ] **Tellius → Game Check**: **Show Tile Panels**.
      Expect: a wireframe of flat tile panels over the grid area only.
- [ ] **Tellius → Light Overlay**: **Bake Light Overlay** (defaults).
      Expect: the hill casts a shadow; the open ground stays bright.
- [ ] **Tellius → FE9 Terrain**: **Save Kit**. **Blender:** close Blender, reopen the file, and check that your paint and the hill are still there.

## 3. App import (5 min)

- [ ] `zmap/bmap01`, **Import .blend/.glb…**, choose the kit.
      Expect: the **Painted terrain import** dialog opens.
- [ ] Keep both checkboxes ticked and choose **The kit's light overlay**, then **Continue**.
      Expect: the review opens on the **Texturing** tab. "What the game draws" matches what you painted; Conflicts shows no red.
- [ ] Check the **Changes** tab: terrain triangles below about 21,000, and no red figures.
      Check the **Warnings** tab and note anything surprising.
- [ ] Click **Write files**.
      Expect: the 3D Models preview shows the hill and the road.
- [ ] Regression: on `zu/fig1`, **Export .blend…** then **Import .blend/.glb…** of the untouched file. Expect: the review opens with no changes beyond the usual. Cancel.

## 4. Dolphin (15 min)

**Chapters → Prologue → ▶ Play in Dolphin…** (Normal).

- [ ] The map loads, with no crash, hang or black screen.
- [ ] Scroll the camera to the corner with the hill. The hill is there, with rock on its sides.
- [ ] The road path is visible, with soft edges, and follows the shape you painted.
- [ ] No seams: no stripes or texture jumps along straight lines about 4 tiles apart, and no wrong-texture squares (atlas bleeding).
- [ ] The light overlay: the hill's shadow is visible. No dark leftovers of the old map's shadows where the ground changed.
- [ ] Inside the playable area: units stand on the ground (not floating or sunk), the move grid is flat and tidy, and the road stroke shows under the grid.
- [ ] Move one unit across the area you edited: it walks the same routes as before.
- [ ] Frame rate looks normal while scrolling over the hill.

## 5. Optional extras (10 min)

- [ ] **Custom atlas**: in **Atlas swatches…**, use **Build custom atlas…** with a seamless 512 px base image and one 128 px swatch, then **Save**.
      Make a kit with "base ground only", paint the swatch, import, and check in Dolphin.
- [ ] **Cliffs**: sculpt a sharp cliff (about 30 m), tick the Rock layer's **Cliffs** icon, import.
      Expect: rock on the cliff faces, not stretched grass.
- [ ] **Restore**: **Restore original…** on `zmap/bmap01` brings back the vanilla Prologue.

## 6. Water and shore waves (about 45 min)

Branch `claude/blender-water` (commit `a216727`), built on `claude/blender-terrain-paint`. Maps: the Prologue (`zmap/bmap01`, a river west of the playable area), `zmap/bmap13` (a sea with shore waves) and `zmap/bmap06` (no water). Skip `zmap/bmap02`: its kit needs the separate fix on `claude/fix-bmap02-terrain-kit`.

### 6.0 Setup (5 min)

- [ ] Check the branch out in its own worktree and run the app from it:
      `git worktree add ..\TelliusModding-water claude/blender-water`, then `cd ..\TelliusModding-water\App` and `python -m fe_modding`.
- [ ] Use a **disposable copy** of your project again: the imports rewrite `bmap01`, `bmap13` and `bmap06`.
- [ ] **Settings**: **Install the Tellius Terrain add-on** again. The note reads "…sculpt & paint and water panels…".
      Restart Blender. **Edit → Preferences → Add-ons**: Tellius Terrain shows version 1.1.0.

### 6.1 The kit shows the map's water (5 min)

- [ ] In the app: `zmap/bmap13`, **Sculpt & paint kit…** (2 units), saved as `bmap13_kit.blend`. **Blender:** open it, press **N**, open the **Tellius** tab.
      Expect: the sea is teal with a soft, lighter edge along the banks, and white foam strips line parts of the shore.
- [ ] **Blender:** the Outliner has **FE9 Water** with `FE9 Water - bmap13_water0`, and **FE9 Shore Waves** with the foam objects.
- [ ] **Blender:** press Play in the timeline (or Space over the 3D view). Expect: the water pattern drifts.
- [ ] **Tellius → Water**: **Water level** 3.00. **Flow** shows Layer 1 at 26.57° and Layer 2 at 63.43°, both at speed 1.12, and the stored row reads −1.00 −0.50 −0.50 −1.00.

### 6.2 Edit the water in Blender (15 min)

Use `zmap/bmap01` for this: make `bmap01_kit.blend` as in step 1 and open it.

In every step below, the water body being edited is the one selected in the list at the top of **Tellius → Water**, not the object selected in the 3D view.

- [ ] **Blender:** put the 3D cursor on the river, west of the tile grid (Shift + right-click). **Tellius → Water**: **Water level** +1 (−2 → −1).
      Expect: the surface moves up while you drag.
- [ ] **Tellius → Water**: **Cut Shoreline from Terrain** (Under the banks 5, Only the water at the 3D cursor ticked).
      Expect: an "N triangles" message, and the river's outline follows the banks a little higher up.
- [ ] **Blender:** put the cursor past the terrain's edge. **Tellius → Water**: cut again **without** Open sea.
      Expect: an error telling you to tick Open sea. Put the cursor back on the river.
- [ ] **Tellius → Water**: **Make Shoreline Fade** (By depth).
      Expect: no hard edge where the water meets the banks; shallows look lighter.
- [ ] **Tellius → Water**: **Paint** (switches to Texture Paint on the fade), then **Shallow**. **Blender:** stroke across the middle of the river. Expect: a lighter, see-through band.
      **Clear** paints it back. Leave one small shallow patch.
- [ ] **Tellius → Water → Flow**: Layer 1 direction 90, speed 2.
      Expect: the stored row starts 0.00 −2.00. When played, the first layer drifts south (down in the top view).
- [ ] **Blender:** put the cursor on the river bank. **Tellius → Water → Shore Waves**: **Around the cursor** 40, then **Place Waves Along Shore**.
      Expect: an "N waves placed" message, with foam strips in one line along the bank, each facing it.
- [ ] **Select:** one wave object. **Blender:** move it off its tile (G) and turn it (R). **Tellius → Water → Shore Waves**: **Snap to Tiles**: it jumps to a tile centre. **Face the Shore**: it turns back toward the bank.
- [ ] **Tellius → Water**: **Check Water Tiles**.
      Expect: "0 water tiles without a surface (red)". Yellow land tiles, if any, sit along the banks.
- [ ] **Tellius → Water**: add a body with **+** beside the list, level −2. Expect: a small square at the cursor. Remove it again with **−**.
- [ ] **Tellius → FE9 Terrain**: **Save Kit**.

### 6.3 Import (10 min)

- [ ] `zmap/bmap01`, **Import .blend/.glb…**, choose the kit. Continue through the paint options.
      Expect: the **Water import** dialog (no donor line on this map). Leave **Repaint the tiles** off, **Continue**.
- [ ] Review **Water** tab: the river with the new outline, the waves as white strokes, the fade, and notes reading "1 of 1 water surfaces rebuilt", "flow set to 0, -2, …", "Shoreline fade replaced", "Shore props: … added".
      Write files.
- [ ] Untouched kit: make a new `bmap13` kit, save it unchanged, and import it.
      Expect: "0 of 1 water surfaces rebuilt, 0 removed" and "Shore props: 0 moved or turned, 0 removed, 0 added". Cancel.
- [ ] Dry map: make a `zmap/bmap06` kit and add a pond. Put the cursor in a hollow, **+** with a level above the hollow's floor, **Cut Shoreline from Terrain**, **Make Shoreline Fade**, then place a few waves. Save and import.
      Expect: the dialog asks for a map to copy water and `wave_99` from; pick `bmap02`. Tick **Repaint the tiles**, River / Plain.
      Review: no warning about the donor's fade, and a "Tiles repainted: N to water…" note. Write files.

### 6.4 Dolphin (15 min)

- [ ] **Prologue**: the river sits one unit higher with soft banks and no hard line. The shallow patch you painted looks lighter. The water drifts south faster than before. The new foam strips animate (stretch and fade) and face the bank.
- [ ] **Light-grey fade** (open item): where the fade is light grey, the bank under the water shows no blue tint at all.
- [ ] **bmap13's chapter**, after the untouched import: the sea, its foam and the ship wakes look exactly as in vanilla.
- [ ] **bmap06's chapter**: the pond shows and animates, with the donor's look. Its foam strips animate.
      The repainted tiles behave as River: move costs change, and units cannot stand where non-flying units shouldn't.
- [ ] **Clock speed** (open item): on any map, time how long the water pattern takes to cross one repeat (6.4 tiles) at a known flow speed. Note the seconds, so the Blender preview speed can be set to match.

## What to send back

- The number of every failed box, with a screenshot (Blender, app review, or Dolphin).
- For Dolphin issues, also a screenshot of the app's **Texturing** tab for the same spot.
- For water issues, a screenshot of the review's **Water** tab, and the timing from the clock-speed box.
