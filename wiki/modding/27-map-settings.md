---
id: "modding-map-settings"
title: "Configure map settings and chapter objectives"
description: "A field-by-field tutorial for borders, lighting, fog, weather, battle skies, chapter records, and objective text"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Maps", "Objectives", "Weather"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/27-map-settings.md"
tutorial_kind: "task"
tutorial_track: "maps"
tutorial_stage: "draft"
prerequisites: ["modding-map-build-basics", "modding-difficulty-and-armies"]
verification: ["source-reviewed", "unknown"]
---
# Configure map settings and chapter objectives

**Routes:** Chapter → Map settings; Chapter → Chapter data

## What you will make

You will give a test map a clearly visible fog/lighting variation, verify its playable border, choose a weather-linked battle sky, and create difficulty-aware objective text. You will then prove that changing the displayed objective does not change the script condition that wins the chapter.

This lesson connects two separately saved records:

- map-wide presentation and tactical-border data inside `map.cmp`;
- chapter metadata, objective keys, enemy bonuses, and scene references inside `FE8Data.bin`.

## Before you begin

Use a known-working chapter and record its map phase, map size, playable border, lighting colors/angles, distance fog, weather, fog-of-war mode, battle sky, and objective text on each available difficulty. Trigger the chapter's existing victory condition once so you know it works before editing labels.

Save or discard any open Build work before switching between direct data editors. Keep a restorable copy of both `map.cmp` and `FE8Data.bin`.

Do not enlarge a map through these settings. **Map size** is read-only because changing the grid dimensions requires rebuilding multiple grid-shaped sections consistently.

## How the editor fits together

The Map settings page edits the open phase's map records through Build's shared Undo/Redo history. **Apply** stages those map changes; **Save Chapter** writes them.

The Chapter data page edits the selected `ChapterData` record in the shared FE8Data session. **Save FE8Data.bin** writes those changes. The weather-linked **Battle sky** shown on Map settings is also FE8Data, so it follows the FE8Data save boundary even though it appears beside map controls.

Objective text keys are presentation. The chapter script owns victory, defeat, seize, escape, boss-defeat, turn-limit, and other event logic. The UI can say “Defeat boss” while the script still completes on routing every enemy.

## Guided walkthrough

### 1. Verify the grid and border

Open **Map settings**. Record **Map size** and **Border**. The border is an inset on every edge: a `2`-tile border removes two rows/columns from each side, so the playable width and height each shrink by four.

Turn on Build's Grid overlay and compare the reported playable dimensions with unit-accessible cells. Make no border change yet. A smaller number expands tactical access into cells that may lack intentional terrain, heights, exits, scenery, or events.

### 2. Make a controlled lighting change

Under **Lighting**, change only **Light colour** to a visibly warmer or cooler RGB value. Leave **Model colour**, **Direction**, and **Height** unchanged. Choose **Apply**, inspect the 2D/3D preview, undo, then redo.

This isolates directional light color from the base color multiplied onto all map models. Once the result is understood, make a modest direction or vertical-angle adjustment and compare shadow/highlight orientation.

### 3. Configure distance fog

Enable **Fog on**, choose a distinctive fog color, and set **Starts at** below **Full at**. Both are camera distances expressed in tile-like units; the engine scales them by five times map scale.

Use a broad interval for the first test so geometry fades progressively. If start and end are reversed or nearly equal, the transition can appear abrupt or unintuitive. Keep **Fog type** at its vanilla value unless the field is already nonzero and you have a specific researched case.

Distance fog is not fog of war. It changes distant rendering, not unit visibility.

### 4. Choose weather and battle sky

Select one of the named **Weather** IDs, such as Rain, Snow, Sandstorm, Night, or Sunset. Each numeric ID invokes a specific map effect; some IDs are unused or only weakly identified, so use a known retail example first.

The **Battle sky** row maps that same weather ID to a scenery sky name in FE8Data. Every map using the weather ID shares that sky-table entry. Use **Browse in 3D...** before assigning it, then remember to save FE8Data separately.

Select **Fog of war** only for a deliberate difficulty test. In US/PAL behavior it is retained on Hard only; the Japanese release uses it above Normal. This selector is distinct from distance fog.

### 5. Inspect advanced values without casual edits

Record **Texture projection**, **Panel offset X/Y**, **Objects already sorted**, and **Other map flags**. Keep panel offsets unchanged because their full visual effect is not decoded.

`Other map flags` is a combined hexadecimal bit field. Known examples include `0x20` for water callbacks, `0x04`/`0x10` for texture effects, and `0x10000000` for roof/object-footprint tests. Preserve unrelated bits when changing a known feature through its dedicated workflow.

### 6. Edit chapter presentation

Open **Chapter data** for the same chapter record. Confirm **Chapter ID**, **Map**, **Script**, and **Message file** before changing anything. These are links between major resources, not cosmetic labels.

Change the **Map music** or a background only if the referenced asset exists. For the tutorial, focus on **Objectives (text keys)**:

- Goal
- Goal second line
- Defeat condition
- Defeat second line

Create or select valid `MW_...` keys for goal lines and `ML_...` keys for defeat lines. Give Hard or Maniac an override only when it should differ. An empty override inherits the Normal value.

Hard/Maniac store overrides for Normal slots 0, 1, and 3. There is no independent override corresponding to every one of the four Normal slots, so read the labels rather than assuming a rectangular four-by-three table.

### 7. Prove text and logic are separate

Save FE8Data and the chapter map, reopen both pages, and launch each affected difficulty. Confirm the displayed objective and defeat lines. Then trigger the original victory condition.

If you want new objective logic, edit and test the chapter script in a later lesson. Do not call a text-only result “a new objective.”

## Understand every control

### Grid

**Map size** reports the complete grid including border and cannot be edited here. **Border** sets an impassable cursor/unit inset on each edge. **Line colour** stores RGB for the tactical grid; scripts control its displayed strength with `SetGrid`.

### Lighting

**Direction** is the horizontal light angle in degrees. **Height** is its vertical angle. **Model colour** is the base multiplier on map models; **Light colour** colors the directional contribution. Each RGB channel is `0–255`, editable numerically or with **Pick...**.

### Distance fog

**Fog on** enables camera-distance fog. **Starts at** and **Full at** set the fade interval. **Colour** is the final fog color. **Fog type** is stored as runtime type minus one and is `0` on every vanilla map; the editor hides it when zero to discourage speculative changes.

### Weather

**Weather** selects IDs `0–17`. The names identify known effects or their vanilla examples; labels containing “unused” are not promises of a complete new weather feature.

**Battle sky** selects `BattleSkyData[weather_id]`. Because the index is the weather ID, changing it affects all maps using that ID. It is saved in FE8Data, not `map.cmp`.

**Fog of war** selects the stored sight code and its runtime mode. It hides units outside allied vision on the difficulties where that regional executable retains the setting.

### Advanced

**Texture projection** stores twice the size used by the projected ground-texture path. **Panel offsets** feed a 2D panel draw whose complete effect is not decoded. **Objects already sorted** matches all vanilla maps; when clear, the game sorts placed objects during load and sets it.

**Other map flags** preserves bits not separated into Weather, Fog of war, or object-order controls. Entering a replacement value can remove water, roof, or material behavior, so edit only from a recorded baseline.

### Chapter identity and assets

**Chapter ID** is the numeric record identity. **Map** selects `zmap/<name>`, **Script** selects `Scripts/<name>.cmb`, and **Message file** selects the chapter message resource. **Map music**, **Base background**, **Conversation background**, **Class-change scene map**, and **Class-change scene sky** name their respective assets.

### Enemy levels and trial grades

**Enemy levels +** adds per-difficulty levels to auto-levelled enemies, capped at 20. Trial **Turns**, **Units lost**, and **Kills** thresholds grade trial maps; they are not ordinary chapter objectives.

## Interactions and precedence

For visual presentation, trace map lighting, distance fog, weather effect, battle-sky table entry, and any script calls such as `SetFog` that override state during the chapter.

For playable area, trace map size, border inset, painted terrain, heights/links, props, and event restrictions. Border edits do not create missing grid data or scenery.

For objectives, trace Normal text keys, difficulty overrides, resolved message text, and independently the script condition that ends or fails the map.

## Test matrix

| Case | Expected result |
| --- | --- |
| Lighting baseline/change | Only selected light component differs |
| Distance fog | Geometry fades between start and full distances |
| Fog-of-war difficulty | Visibility changes only on applicable mode/build |
| Weather | Intended map effect appears |
| Battle scene | Weather-linked sky resolves in combat |
| Normal objective | Four Normal lines resolve as intended |
| Hard/Maniac override | Populated override differs; blank one inherits |
| Victory logic | Original script condition remains authoritative |
| Reload | Map and FE8Data values survive their separate saves |

## Troubleshooting

**Fog does not hide enemy units.** You edited distance fog, not fog of war. Use the sight-code control and test the applicable difficulty.

**The battle sky reverted.** Save FE8Data; Save Chapter only writes the map settings.

**Changing weather changed other maps' battle sky.** The sky table is indexed by shared weather ID. Reuse intentionally or create a design using an available distinct ID after testing its map effect.

**Units can enter unfinished edge cells.** Increasing playable area through Border exposes existing grid cells; it does not author their terrain, panels, links, props, or scripts.

**Objective wording changed but victory did not.** Edit the owning script condition. Text keys are presentation.

**One difficulty shows an old line.** Inspect its explicit override and inheritance. Remember there is no one-to-one override for all four Normal slots.

**Water or roofs stopped working.** Restore the original Other map flags and use dedicated water/prop workflows that preserve unrelated bits.

## Save, build, and revert

Choose **Apply** for map fields, then **Save Chapter**. Choose **Save FE8Data.bin** for chapter records and battle skies. Reopen both surfaces before runtime testing.

Record all original numeric values and keys. Restore map settings through Build and save, and restore FE8Data fields separately. For an unknown flags mistake, use the pre-edit archive rather than reconstructing bits from appearance.

## Limits and confidence

The exposed map fields, save ownership, weather/sight selectors, regional fog-of-war rule, battle-sky indexing, chapter record layout, and objective inheritance are source-reviewed. Several advanced flag/panel behaviors and exact rendering interactions remain **unknown** outside tested retail patterns. Runtime scripts can supersede initial settings, so preview alone is insufficient.

## Things to try next

- Create sunset lighting while preserving neutral model color.
- Compare distance fog and fog of war side by side.
- Give Hard a different goal line while inheriting the Normal defeat condition.
- Audit every map using one weather ID before changing its battle sky.
- Expand a border by one tile only after authoring every newly playable layer.

## Related tutorials and references

- [Import water and set its flow](26-water.md)
- [Assign battle backgrounds by terrain](28-battle-backgrounds.md)
- [Edit chapter scripts](33-script-editor.md)
- [Objectives](../systems/objectives.md)
- [Weather](../systems/weather.md)
- [Map format](../formats/map-format.md)

---

[← Previous: Import water and set its flow](26-water.md) · [All tutorials](index.md) · [Next: Assign battle backgrounds by terrain →](28-battle-backgrounds.md)
