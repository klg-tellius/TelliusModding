---
id: "map-format"
title: "Map File Format"
description: "Terrain, placed 3D scenery, tile elevation, and lighting for one chapter"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Chapter data","Editable"]
aliases: ["tellius_archive.html#/map-format"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/map-format.md"
---
# Map File Format

*Terrain, placed 3D scenery, tile elevation, and lighting for one chapter*

A chapter map defines terrain, placed scenery, tile elevation, lighting, fog, and invisible objective markers. Decompressing `map.cmp` produces a [pack archive](./pack-archive.md) containing `map.bin` and the chapter's 3D scenery models, allowing object records to refer to companion models by filename.

## How the sections build a battlefield

`mapcapacity` establishes dimensions; object descriptions define reusable things; instance records place them; three panel layers describe tile-corner elevation; sparse link grids add per-tile blocking/status bits; and single-record lighting/fog/extra sections set presentation and runtime grid margins. Unit deployment is separate and uses the tactical grid.

## Example: one tree model, many trees

One `mapbuilddesc` can name the tree model and its footprint. Several `mapbuildinst` records can then place that same description at different positions and angles. Editing the description changes every instance; editing one instance moves only that placement.

<div class="table-wrap">
<table><thead><tr><th>Section</th><th>Size</th><th>Contents</th></tr></thead><tbody>
    <tr><td><code>mapcapacity</code></td><td class="num">12B, 1 rec.</td><td>Grid size; <code>scale_unit</code> is an <strong>f32</strong> confirmed always exactly <code>2000.0</code></td></tr>
    <tr><td><code>mapbuilddesc</code></td><td class="num">32B/object</td><td>The model's bounding box as its minimum and maximum corners in (x, y, z) order, three flag-bit bytes, a type byte, model filename</td></tr>
    <tr><td><code>mapbuildinst</code></td><td class="num">12B/inst.</td><td>Placed-instance x/y/angle (unsigned byte; 64 = 270&amp;deg; by the native formula), <code>mapbuilddesc</code> index, the rectangle of tiles the object covers after rotation, and a raw float32 height</td></tr>
    <tr><td><code>uniquepanel</code>/<code>Roof</code>/<code>Base</code></td><td class="num">12B/record</td><td>Four signed corner elevations, three layers (ground+object / ground alone / building); tiles share records through the <code>panelindex</code> grids, which hold 0-based record numbers. The ground layer sits at terrain height <code>&amp;minus;elevation / 400</code>. Each record also points to a terrain-type name (<a class="wl" href="../fe8data/">TerrainData</a>); the combined layer's name is the tile's terrain, the ground layer's the ground under objects <span class="badge confirmed">files + in game</span></td></tr>
    <tr><td><code>maplink</code>/<code>maplinkAt</code>/<code>maplinkAbs</code></td><td class="num">sparse grids</td><td>Count followed by <code>(x, y, value)</code> entries; together they form per-tile status/blocking bitfields</td></tr>
    <tr><td><code>maplight</code>/<code>mapfog</code>/<code>mapgrid</code>/<code>mapextra</code></td><td class="num">1 rec. each</td><td>Ambient+directional light color, fog density/color, grid overlay color, tactical-grid margins and map-mode flags</td></tr>
  </tbody></table>
</div>

## Runtime loading

  The native map loader copies the section payload image into RAM using the same offsets as `map.bin` after the first `0x20`-byte header. In live dumps, each chapter's `mapcapacity` bytes appear exactly once, and `mapextra` appears at `capacity_ram + (mapextra_file_offset - 0x20)`. This confirms that the loader preserves section layout while resolving named sections by pointer.

## mapextra

  The first eight bytes are eight independent bytes, not mixed 16-bit fields. Bytes 0 and 1 are the positive counterpart of the base terrain instance's negative placement coordinate in every checked chapter; bytes 2 and 3 are `ceil(x_size/2)` and `ceil(y_size/2)`; byte 5 is the confirmed tactical-grid buffer. The game uses that buffer to compute usable bounds as `min_x=min_y=buffer` and `max_x=x_size-buffer`, `max_y=y_size-buffer`. The trailing word is a set of map flags: its low bits switch on the terrain's texture overlay and the moving-water effect (bit `0x20`, set on every map with water and on none without), and two higher fields are map-mode values read at load. <span class="confidence confidence--confirmed">engine</span>

## Water

  A map's water is its own model, `<map>_water0` (up to three on one map), placed at the terrain's origin: on the Prologue a flat, half-transparent plane two units below the ground. Its material, `map_water`, has two textures that scroll; the water object's animation file moves no bones and holds only a four-number table, the two textures' scroll speeds (the Prologue's river: −0.124, 0.360, −0.231, −0.572, times the map's clock). <span class="confidence confidence--confirmed">engine + files</span> The surface covers exactly the tiles whose terrain type is river — the terrain types, not the model, decide where units can go. <span class="confidence confidence--strong">engine + files</span>

## Terrain texture stages

  Chapter terrain can use several material texture stages and a second UV channel. Three-stage base terrain materials are common across the game's maps: the first two texture-stage records share one metadata pattern, while the third has a distinct light/shadow-like pattern and uses the second UV channel. The Prologue's base terrain material, for example, references three textures: a tall macro/detail atlas, a road/cliff blend mask, and a light/shadow overlay. See [Terrain Texture Blending](../systems/terrain-texture-rendering.md) for how a material's textures actually combine at render time.

## Terrain mesh and tile heights

  The land terrain model's vertices are world positions starting at `(0, 0)`, five units per tile; tile 0 of the tactical grid starts at five times the `mapextra` panel offset. Units stand on the elevations stored in the panel layers, not on the mesh itself, so the two only agree because the map's authors kept them in step: on the Prologue and chapter 1, every playable tile corner of the ground layer is at exactly `&minus;elevation / 400` of the mesh height. <span class="confidence confidence--confirmed">files</span> On later maps some tiles stand on props instead — bridges, castle floors and walls: counting placed props too, 98.6% of chapter 6's and 98.8% of chapter 11's tile corners lie on a surface.

  The move and attack grid is drawn from the same corner heights: one flat panel per tile half, each tile split along its top-right to bottom-left diagonal. Vanilla terrain follows those panels exactly in the playable area — every triangle there has its corners on tile corners (on flat ground one triangle may span two tiles, level with both), and split tiles use the same diagonal — so the grid lies on the ground. Placed props sit at their tile's surface through their own height value. A reshaped playable area therefore needs the three to move together: in the Prologue, a hill added to the ground, its tile heights and prop heights raised to match, and the ground cut and flattened onto the tile panels, played correctly, while the same hill with an uncut mesh showed ground through the grid where it bulged inside a tile. <span class="confidence confidence--confirmed">in game</span>

  Tiles share panel records, so new heights need new records and the panel sections grow; everything after them in the file moves, together with every stored pointer and section address that refers to it.

## Link grids

  The three link sections are sparse because most tiles do not need an explicit value: every tile starts open in all four directions (`0x0F`), and the sections only list exceptions. <span class="confidence confidence--confirmed">engine</span> Native loading applies `maplink`, then `maplinkAt`, then `maplinkAbs`; the last one replaces the cell with an absolute low nibble plus that nibble's inverse in bits 4&ndash;7. Low bits 0&ndash;3 are confirmed directional passability openings: west, east, south, north. A later native pass clears those openings if either corner on the shared edge differs from the neighboring tile by 400 height units or more. The higher status bits still need gameplay verification.

!!! info "Placed-object flags, resolved"
    **Map-wide object** (bits 7&ndash;6): the object *is* the map's own base terrain/water-plane model, not merely large — every real object carrying it is literally named after its own map. <span class="confidence confidence--confirmed">confirmed</span>

        **Has a matching animation file** (bit 1 of a third flag byte): set exactly when a matching animation file exists across 873 objects. <span class="confidence confidence--confirmed">confirmed</span>

        **Battle-goal type** (a 3-bit field): a multi-value type recurring across chapters on invisible markers named for conditions such as “ascendancy,” “defense,” and “attainment.” <span class="confidence confidence--confirmed">confirmed</span>

  See [Chapters](../systems/chapters.md) for how this file's chapter-duplication story compares to [dispo's](./dispo-format.md).
