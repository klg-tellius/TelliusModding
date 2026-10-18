---
id: "modding-battle-backgrounds"
title: "Assign battle scenery by map and terrain"
description: "A complete guide to BattleTerrData rows, terrain columns, default fallback, scenery browsing, and testing"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Battle scenes", "Terrain"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/28-battle-backgrounds.md"
tutorial_kind: "task"
tutorial_track: "maps"
tutorial_stage: "draft"
prerequisites: ["modding-map-settings", "modding-terrain-types"]
verification: ["source-reviewed", "unknown"]
---
# Assign battle scenery by map and terrain

**Route:** Chapter → Battle scenes

## What you will make

You will give one map its own battle-scenery row, assign different scenery to ordinary ground and forest, and deliberately leave a third terrain blank to test row-local fallback. You will then compare that behavior with the shared row-0 fallback used by maps that have no row of their own.

This distinguishes three common ideas:

- a map's own row;
- an empty terrain cell falling back to that row's first scene;
- an absent map row falling back to the entire first row.

## Before you begin

Choose a map containing at least two painted terrain types and working map battles. Record its exact `zmap` folder name, terrain types and tile counts, current effective scenery, and whether the editor says it owns a row or uses the shared default.

Open the candidate `zbg/<scene>` folders in the scenery browser and confirm they have readable model packs. A name can exist in FE8Data without a corresponding folder; the editor labels that case explicitly.

Make a restorable FE8Data copy. Row 0 affects every map without its own row, so never use it as a private scratch row.

## How the editor fits together

`BattleTerrData` contains one row per explicitly configured map. Each row has:

- a map-folder name such as `bmap05_2`;
- one scenery name for each of the 77 terrain-table positions.

At battle start, the game finds the row whose map name matches the current phase. If none exists, it uses row 0. Inside the selected row, a null/blank terrain entry uses that row's first terrain entry. Therefore fallback happens first by row, then by cell.

The first terrain column remains visible even when the map has none of its tiles because it is the row-local default. Terrain columns are positional: they follow the fixed 77-entry terrain table, not a dictionary keyed only by display text.

## Guided walkthrough

### 1. Read the map's effective state

Open the chapter phase's **Battle scenes** tab. Leave **Only terrain types on this map** enabled. The table shows terrain index, display/internal name, tile count, assigned scene, and fallback note.

Read the banner carefully:

- **This map has no scenery row** means it currently uses row 0.
- **This map is the shared first row** means edits affect every map without its own row.
- No fallback warning means the phase already owns a row.

Use **View...** or **Browse...** on several cells. The browser reports the `zbg` resource path and other rows using the selected scene.

### 2. Give the map an isolated row

If the map lacks a row, choose **Give `<map>` its own row**. The new row begins from the effective/default arrangement so appearance does not need to change immediately.

Do not choose **Edit shared default** for a map-specific design. That button intentionally edits row 0 and warns that other fallback maps will change.

### 3. Assign the first/default scene

On terrain index 0, browse and choose a general-purpose scene appropriate for the chapter. This cell is used whenever another terrain cell in the same row is blank.

Pick a resource that actually has a `zbg/<name>` folder. A table-only name may be preserved for research or cross-project compatibility, but it cannot preview and may fail to resolve in the built project.

### 4. Add explicit terrain variations

Find ordinary ground and forest using their index, display name, internal key, and tile counts. Assign a field/plain scene to ground and a wooded scene to forest.

For a third present terrain, clear its cell. The note should display `default: <first-scene>`. This is a deliberate test of row-local fallback, not a missing asset.

Toggle **Only terrain types on this map** off and inspect all 77 positions. This is useful before copying or repainting terrain because previously unused types may already contain inherited or explicit assignments.

### 5. Save and test resolution

Choose **Save FE8Data.bin**, leave the chapter, and reopen the same phase. Verify the banner still says the map owns its row and all three test cells resolve as planned.

In Battle Simulator or a launched chapter, keep fighters, weapons, distance, and camera conditions constant while changing only the map/terrain context. Test explicit ground, explicit forest, and blank/fallback terrain.

Then inspect a different map that still uses row 0. It should remain unchanged, proving the new row isolated your work.

### 6. Test row removal only on a copy

If the editor offers dropping the map's row, do so only in a disposable copy after recording every cell. The map immediately returns to row 0 behavior. Rows are structural FE8Data records; deleting one is not equivalent to clearing its individual terrain cells.

## Understand every control

### Save and discard

**Save FE8Data.bin** writes the shared data session. **Discard unsaved edits** returns the entire unsaved FE8Data session to its last saved state, not only the currently visible scenery cell. Review the change log first when other Game Data pages are open.

### Only terrain types on this map

When enabled, the editor counts the map's painted terrain and shows only used columns plus index 0. If the map cannot be read, every type is shown. This filter changes visibility only; it never deletes hidden assignments.

### Give the map its own row

This creates an explicit row keyed by the current map folder. Use it whenever changes should not propagate through shared row 0. A different phase such as `bmap05_2` is a different key from `bmap05`.

### Edit shared default

This makes row 0 editable while viewing a map that falls back to it. **Stop editing shared default** returns to read-only effective-state viewing. Treat row-0 edits as global changes and test multiple fallback maps.

### Terrain cells

Each combobox accepts a scenery name. **Browse...** filters, previews, and chooses among scene names found in `zbg` plus names already referenced by the table. **Clear/use default** stores no scene in that cell, causing fallback to the same row's first scene.

The note `no zbg folder of that name` is a hard asset warning. The key exists in the table but this project lacks a previewable scenery pack with that name, even under case-insensitive matching.

### Scene browser

**Filter** searches names by words. Arrow keys step through results; Enter, double-click, or **Use this scene** selects one. The preview is delayed slightly and caches recent scenes so keyboard navigation does not decode every skipped asset.

The information panel shows the resolved pack path and every map/default row using the name. Use that dependency list before replacing or renaming scenery assets.

## Interactions and precedence

The complete scenery resolution is:

1. Current chapter phase selects its map-folder name.
2. Matching `BattleTerrData` row is used; if absent, row 0.
3. Painted tile terrain selects one of 77 positional columns.
4. If that cell is blank, the selected row's column 0 is used.
5. The resulting name resolves to `zbg/<name>/` assets.
6. Battle sky, camera, combat distance, participants, effects, and scenery parameters complete the rendered stage.

Changing terrain painting can therefore change battle scenery without editing FE8Data. Changing a terrain record's display name does not move its positional column. A map weather/battle sky change affects the sky behind the resolved scenery, not this table's ground scene.

## Test matrix

| Case | Expected result |
| --- | --- |
| Explicit ground | Ground cell resolves assigned field scene |
| Explicit forest | Forest cell resolves assigned wooded scene |
| Blank present terrain | Cell resolves current row's column 0 |
| Map without row | Every terrain resolves through row 0 and its cell fallback |
| Alternate phase | Uses its own map-folder row or row 0 independently |
| Missing folder | Editor warns; preview unavailable |
| Repainted tile | New terrain column selects its scene |
| Reload/runtime | Saved FE8Data and native battle use intended assets |

## Troubleshooting

**Every terrain shows the same scenery.** The nonzero cells are blank or all explicitly name the same scene. Inspect notes and column 0.

**Changing one map altered several chapters.** You edited row 0 or several chapters share the exact map folder. Give the intended phase its own row.

**A painted tile gets unexpected scenery.** Confirm its actual terrain identity/index in Build. Visual map art does not choose this table directly.

**The browser lists a scene but cannot preview it.** The name is referenced by FE8Data but has no matching `zbg` folder. Import/copy the asset or choose an existing resource.

**The scenery is right but the sky is wrong.** Battle sky is selected through the map's weather ID and `BattleSkyData`. Return to Map settings.

**An alternate phase still uses the old scene.** Each phase's `zmap` folder name needs its own row unless both intentionally use row 0.

**Changes vanished.** Save FE8Data.bin. Save Chapter does not write `BattleTerrData`.

## Save, build, and revert

All table edits use **Save FE8Data.bin**. Reopen the map phase and verify effective notes before building.

Revert individual cells by restoring their prior names/blanks. Revert row creation/removal from the FE8Data backup when exact ordering and references matter. Because row 0 is a shared dependency, restore it as a whole if its original cells were not fully recorded.

## Limits and confidence

The 77-column layout, map-row matching, two-stage fallback, UI filtering, folder resolution, and save boundary are source-reviewed. The 3D preview demonstrates asset readability, not exact native camera, lighting, combat effects, or every terrain transition. Those remain **unknown** until tested in the target battle.

## Things to try next

- Give indoor floor, outdoor ground, and forest distinct scenes on one map.
- Create separate rows for two phases sharing most but not all scenery.
- Use intentional blanks to keep a row maintainable.
- Audit every map dependent on row 0 before changing its default.
- Repaint one cell in Build and predict the scene before launching combat.

## Related tutorials and references

- [Configure map settings and chapter objectives](27-map-settings.md)
- [Edit terrain rules and movement costs](19-terrain-types.md)
- [Battle staging](../systems/battle-staging.md)
- [Terrain texture rendering](../systems/terrain-texture-rendering.md)
- [FE8Data format](../formats/fe8data.md)

---

[← Previous: Configure map settings and chapter objectives](27-map-settings.md) · [All tutorials](index.md) · [Next: Choose deployment sections →](29-deployment-sections.md)
