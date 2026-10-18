---
id: "modding-water"
title: "Import water and set its flow"
description: "A complete water workflow covering geometry, donor resources, materials, flags, scroll speeds, and terrain matching"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Maps", "Water", "glTF"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/26-water.md"
tutorial_kind: "task"
tutorial_track: "maps"
tutorial_stage: "draft"
prerequisites: ["modding-terrain-mesh", "modding-paint-terrain-and-blocking"]
verification: ["source-reviewed", "unknown"]
---
# Import water and set its flow

**Route:** Chapter → Build → Map settings → Import water GLB / Water flow

## What you will make

You will replace a small water surface, align it with painted water terrain, and isolate the direction contributed by each of its two scrolling textures. You will also learn the extra decisions required to add water to a map that originally had none.

Water is not one object or checkbox. A working result combines:

- visible water geometry;
- a `map_water` material and texture records;
- a `.ga` animation containing a four-value scroll table;
- the map's water callback flag;
- painted water terrain for tactical movement.

## Before you begin

Prefer a map that already has one water object. Record its object name, surface height, painted terrain underneath it, current flow values, and shoreline appearance. Save all Build edits and make a backup of `map.cmp`.

Export or otherwise preserve the current water reference before replacement. Model in the terrain's coordinate system at **5 units per tile**. Vanilla water commonly sits at model Y `-2`, but use the current map's exported surface as the authoritative reference rather than forcing every map to that value.

For a dry map, identify a donor map whose water animation and texture appearance you are allowed to reuse. The donor must actually contain a recognized water object, not merely blue-looking terrain.

## How the editor fits together

The app recognizes a water object when it is a base map object whose model contains a material named `map_water`. A map can contain more than one; the editor asks which one to edit when necessary.

Replacing existing water keeps its skeleton, scroll animation, material colors, texture-record behavior, flags, and name while rebuilding the surface from the imported GLB. Every imported material is converted to `map_water`. If the GLB supplies an image, its first material image can replace the first water texture while the existing water records continue to define the multi-pass behavior.

Adding water to a dry map copies a donor's `.g`, `.ga`, and two water texture images, creates a `<terrain>_water0` object with the vanilla water flags/effect type, places it at the terrain origin, and enables map flag `0x20` so the water material callback animates.

Painted terrain remains separate. The importer reports visible water over non-water terrain and water terrain with no visible surface.

## Guided walkthrough

### 1. Establish the existing water baseline

Open the map in Build and the 3D view. Turn on **Terrain** and **Grid**. Record the cells visually covered by water and the water terrain names beneath them—normally River, Sea, Waterway, Pond, or Moat identities.

Open **Water flow...** and record the four values in order:

```text
u1 v1 u2 v2
```

Cancel without changing them. If the app reports that the map has no water with a scroll table, this object cannot use the normal flow editor; choose another reference map for the first exercise.

### 2. Export or build a minimal replacement plane

Use the existing water as the coordinate reference. In your 3D editor, create or edit a plane covering only a small test pond. Keep it aligned with the terrain origin and expected Y height. Triangulate cleanly and provide one simple material/image.

Do not bake movement rules into the model. Geometry controls appearance; painted terrain controls the tactical classification beneath it.

### 3. Import into an existing wet map

Open the water import action and select the GLB. If several water objects exist, enter one of the names listed by the dialog exactly.

The importer rebuilds the named `.gs`, reuses its `.g` and `.ga`, converts every material to `map_water`, preserves the source water material's colors and texture parameters, and updates the object's bounds. Read the report before saving.

If the GLB has several materials, the report warns that each became `map_water` with the water textures. Simplify the source when those extra passes were not intentional.

### 4. Resolve terrain mismatches

The import report counts two distinct problems:

- **Tiles under water that are not water terrain:** the model covers the cell, but units use a non-water rule.
- **Water-terrain tiles with no water over them:** the rule says water, but no imported triangle covers the cell center.

Turn on the Terrain overlay and fix the intended side of each mismatch. Expand the surface when it is visually missing; repaint terrain when the geometry is right but the tactical identity is wrong. Do not automatically turn every reported cell into water—the correct choice depends on shoreline design and bridges.

### 5. Isolate the first texture's flow

Open **Water flow...**. Enter four numbers with only U1 nonzero, for example:

```text
0.05 0 0 0
```

Apply, save, and preview or run the map long enough to observe direction. Then reverse it:

```text
-0.05 0 0 0
```

Negative reverses that axis. Restore U1 to the desired value, then repeat with only V1, U2, and V2 nonzero. This isolates each channel rather than guessing from four simultaneous motions.

### 6. Build a layered final flow

Choose subtle values for both texture layers. One layer can move mainly along U while the second moves more slowly along V, creating intersecting ripples. Keep a written baseline and change one component per test.

The accepted range for each value is **-32.768 to 32.767**, stored at 0.001 precision. Values near the limits are diagnostically obvious but rarely visually appropriate.

### 7. Add water to a dry map

On a backed-up dry map, import the GLB. The app asks which map should donate water animation and textures. Choose a listed wet map with the desired appearance.

Read the report for confirmation that water flag `0x20` was set. Then resolve all terrain mismatches, open **Water flow...** to confirm the copied scroll table is readable, save, reopen, and run the map.

## Understand every control

### Water object selection

When one recognized water object exists, it is selected automatically. With several, the dialog lists valid names and requires an exact choice. Canceling leaves the map unchanged. An unknown name is rejected rather than creating an accidental replacement.

### Import water GLB

The selected GLB supplies static surface geometry and imported images. The target or donor supplies the water-specific skeleton, animation, material colors, and texture records. All GLB materials are renamed `map_water` because the callback key is part of the rendering contract.

The object's **Origin offset** and **Size** bounds are recalculated from the imported geometry. On new water, vanilla water object flags and runtime effect type `154` are assigned.

### Donor map

The donor is needed only when the current map has no water. It contributes animation and texture resources, not geometry. Its water images are appended to the destination texture pack and references are remapped. Choose by desired texture/flow behavior, then test against the destination map's lighting.

### Water callback flag

Map flag `0x20` installs the `map_water` multi-pass animation callback. All observed vanilla maps with water set it and maps without water do not. Adding water sets the bit and reports the change. A plane and blue texture without this callback are not equivalent to the supported water system.

### Flow values

**U1** and **V1** scroll the first water texture along its two UV axes. **U2** and **V2** do the same for the second texture. The game multiplies them by the map clock. Sign controls direction; magnitude controls rate.

The values are stored as signed 16-bit integers scaled by 0.001. The editor requires exactly four numeric values and rejects out-of-range input. It preserves the normal one-channel/four-key water scroll-table layout.

If the animation lacks the required footer scroll slot, the editor reports that there is no scroll table. Although the engine has traced fallback values for a missing table, this editor intentionally does not fabricate one through the Water flow dialog.

### Painted terrain

The mismatch audit recognizes the internal terrain types for river, sea, waterway, pond, and moat. Those types determine costs and bonuses through the terrain table. The visual water plane neither changes them nor guarantees impassability.

## Interactions and precedence

When water looks or behaves incorrectly, trace:

1. A recognized base object with a `map_water` material exists.
2. Its model covers the intended cell centers.
3. Skeleton and `.ga` animation resolve.
4. The animation contains the expected scroll table.
5. Map flag `0x20` enables the callback.
6. Both texture records and images resolve in `texpack.tpl`.
7. Painted terrain matches the intended wet footprint.
8. Heights/exits/props define bridges, banks, and traversal exceptions.

Water geometry does not create splash effects or movement rules everywhere by itself. Battle foot effects and tactical terrain have their own consumers.

## Test matrix

| Case | Expected result |
| --- | --- |
| Existing baseline | Original geometry, terrain match, and four flow values recorded |
| Replacement | New surface uses existing water appearance and animation |
| U1 only | Only first layer moves along its U axis |
| Negative U1 | Same layer reverses direction |
| Second layer | U2/V2 affect the other texture independently |
| Wet/non-water cell | Audit reports visible water over dry terrain |
| Water/no-surface cell | Audit reports uncovered water terrain |
| Dry-map donor | Object/resources added and flag `0x20` reported |
| Runtime shoreline | Intended movement types and visuals agree after reload |

## Troubleshooting

**The app says the map has no water.** Recognition requires a base object with a `map_water` material. Select a valid donor when adding water to a dry map.

**The donor is rejected.** The selected map has no recognized water either. Choose one from the wet maps listed by the dialog.

**Water is visible but does not move.** Check for a readable `.ga` scroll table and water flag `0x20`. Confirm time actually advances in the preview/runtime used for observation.

**Flow moves diagonally or too quickly.** Zero three values and identify one channel at a time. Then combine small measured components.

**Units walk across deep-looking water.** Paint an appropriate terrain identity and inspect the active class's movement column. Visual depth is not a movement rule.

**A bridge cell is reported as mismatched.** Decide whether the cell center should tactically be bridge/ground while water passes visually below. The audit flags disagreement; it cannot infer your layered design.

**The shoreline shifted after import.** Compare geometry coordinates with the terrain origin and five-unit scale. Water and land share the terrain coordinate system, not an arbitrary object origin.

**Textures look wrong on the destination map.** A dry-map donor brings its water images/material settings, but destination lighting and surrounding terrain differ. Test the exact target map rather than relying on the donor preview.

## Save, build, and revert

Water imports, flow edits, map flags, and painted cells are Build-owned map changes written by **Save Chapter**. Reopen the phase and re-read flow values after saving.

For exact rollback, restore the pre-import `map.cmp`. Removing the visible water instance alone does not undo copied textures, animation files, object definitions, flag `0x20`, or terrain repainting. A whole-archive restore is the reliable inverse of adding water to a dry map.

## Limits and confidence

Recognition, donor behavior, material conversion, vanilla flags/effect type, map callback flag, scroll-table format/range, coordinate scale, and mismatch audit are source-reviewed. Exact native appearance across unusual materials, maps with several water objects, bridge layering, and regional/runtime rendering remains **unknown** until tested in the target game.

## Things to try next

- Create still-looking water with very small opposed layer motions.
- Make a river flow strongly along one UV axis while ripples drift across it.
- Compare Pond and Sea terrain costs under identical visible water.
- Add a bridge and document why its tactical center differs from the water audit.
- Use the same geometry with two donors to compare texture/animation style.

## Related tutorials and references

- [Paint terrain and control movement](22-paint-terrain-and-blocking.md)
- [Edit tile heights, slopes, and exits](23-tile-heights.md)
- [Replace a terrain mesh safely](25-terrain-mesh.md)
- [Weather](../systems/weather.md)
- [Map format](../formats/map-format.md)

---

[← Previous: Replace a terrain mesh safely](25-terrain-mesh.md) · [All tutorials](index.md) · [Next: Set fog, lighting, border, and objectives →](27-map-settings.md)
