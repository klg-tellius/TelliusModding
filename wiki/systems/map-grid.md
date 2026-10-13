---
id: "map-grid"
title: "Coordinate Systems & Grids"
description: "Scenery placement and unit movement use the same tile numbers, with different world formulas"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Structure"]
aliases: ["tellius_archive.html#/map-grid"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/map-grid.md"
---
# Coordinate Systems & Grids

*Scenery placement and unit movement use the same tile numbers, with different world formulas*

Scenery placement and the tactical grid number their tiles the same way — tile `(x, y)` of an object instance is tile `(x, y)` of the cursor, the deployment data and the map's per-tile height and terrain records — but they turn tile numbers into world positions with different formulas. In the Prologue, props placed at columns 4 and 6 appeared one and three tiles right of a unit standing at column 3. <span class="confidence confidence--confirmed">in game</span>

## How to choose the correct grid

  If the subject is a unit, cursor, movement range, or deployment coordinate, use the tactical grid. If it is terrain, a tree, water, an invisible marker, or another model instance, use the placement transform. Convert to world coordinates only at the rendering boundary.

## The placement grid (confirmed)

  Used to position 3D scenery — see [Map Objects & Placement](./map-objects.md) for the full formula. Its origin is wherever the map's own terrain instance places the terrain, not `(0, 0)`; every other object's coordinates are relative to that anchor. Each tile is 5.0 world units, and an object rotates around the center of its own tile cell rather than its raw corner.

## The tactical grid

  This is the grid used by the player's cursor and units in battle. Its native tile-to-world conversion uses the same confirmed `5.0`-unit tile constant as scenery placement but applies a simpler formula:

  world = 5.0 × tile_index × map_scale

  No pivot and no rotation are applied to tactical tiles. For rendering on the raw terrain mesh, tile `0,0` is anchored to the terrain placement origin: in checked maps, `mapextra`'s first two bytes equal the negation of the base terrain instance's `x/y` placement. For example, Prologue stores terrain instance `(-22, -20)` and `mapextra` bytes `(22, 20)`, so tactical tile `(0,0)` draws at placement coordinate `(0,0)`, not at the raw mesh's own top-left corner.

  The full tactical data grid is `[0, x_size] × [0, y_size]` from `mapcapacity`. Its inner usable range is inset by `mapextra.grid_buffer`, below.

## The inset margin

  A separate, fully confirmed byte in the map's own extra-data section defines a playable-area margin around the tactical grid's edge: usable tiles run from that margin value up to `size − margin` on each axis, not from `0` to `size` outright — a real border of unplayable tiles around every map.
