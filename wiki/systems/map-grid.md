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
system_entries: ["FE9-SYS-056", "FE9-SYS-059", "FE9-SYS-067"]
system_reviewed: ["FE9-SYS-056", "FE9-SYS-059", "FE9-SYS-067"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-13"
system_known_gaps: []
system_gap_work: []
---
# Coordinate Systems & Grids

*Scenery placement and unit movement use the same tile numbers, with different world formulas*

Scenery placement and the tactical grid number their tiles the same way — tile `(x, y)` of an object instance is tile `(x, y)` of the cursor, the deployment data and the map's per-tile height and terrain records — but they turn tile numbers into world positions with different formulas. In the Prologue, props placed at columns 4 and 6 appeared one and three tiles right of a unit standing at column 3. <span class="confidence confidence--confirmed">in game</span>

## FE9-SYS-056 — Tile coordinate system

<span id="fe9-sys-056"></span>

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

## Worked example: one tile across three consumers

Suppose deployment places a unit at `(8, 5)`. The occupancy, cursor, event-zone, terrain, and movement systems all address grid cell `(8, 5)`. Rendering converts its center through the tactical 5-unit formula and samples the panel's surface height. A tree instance also authored at `(8, 5)` uses the scenery placement transform, terrain anchor, pivot, rotation, and stored height instead. The matching integers let the two appear together, but neither record is the other's coordinate source.

## FE9-SYS-059 — Passability rules and lifecycle

<span id="fe9-sys-059"></span> Every cell begins with four ground openings: west, east, south, and north in bits 0–3. Height filtering closes an edge when either shared corner differs by at least 400 elevation units. Sparse `maplink` entries then provide authored exceptions, `maplinkAt` supplies directional threat-search cost hints in bits 8–11, and `maplinkAbs` replaces the low openings while generating the corresponding high-nibble flying blocks. The playable inset finally closes outward edges at the boundary.

This order matters. A sparse authored opening can restore a ground edge closed by height, while an absolute record owns the cell and should not be casually overwritten. Ground movement follows low openings; flying movement uses the high directional block state; threat projection can cross a closed ground edge at a higher cost when its block bit permits it.

## FE9-SYS-067 — Height and terrain conformance

<span id="fe9-sys-067"></span> Three panel layers store four signed corner elevations per shared record: combined ground/object, base ground, and roof. Index grids select those records for each tile. The base surface height is `−elevation / 400`, and the tactical overlay draws two triangles split along the same diagonal as authored terrain. Units sample this logical surface; placed props carry their own vertical value but are normally authored against the tile-center surface.

The terrain mesh, panel heights, object heights, and passability edges must be edited together. Raising only the visible mesh leaves units and the grid below it. Raising only panels can make units float or create 400-unit edge walls. Live tests that reshaped the Prologue confirmed correct play only after the mesh was cut to the panel surface and affected props were moved with it.

## Interactions, edge cases, and evidence

The coordinate constants, terrain anchor, usable inset, panel indexing, elevation conversion, link-load order, directional meanings, height closure, flying interpretation, and threat hints are confirmed by native consumers, all retail maps, and targeted Dolphin edits. Free-angle visual props can have hand-authored footprints that do not follow the quarter-turn approximation, but that does not change the reviewed tactical coordinate, link, or height model. Exact binary fields remain in [Map File Format](../formats/map-format.md); this page owns their system-level relationship.
