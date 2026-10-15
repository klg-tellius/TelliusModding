---
id: "maps-system"
title: "Maps"
description: "How one chapter's battlefield is assembled from terrain, placed 3D scenery, and unit deployment"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Structure","Graphics"]
aliases: ["tellius_archive.html#/maps-system"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/maps-system.md"
system_entries: ["FE9-SYS-055", "FE9-SYS-056", "FE9-SYS-057", "FE9-SYS-058", "FE9-SYS-059", "FE9-SYS-060", "FE9-SYS-061", "FE9-SYS-062", "FE9-SYS-063", "FE9-SYS-064", "FE9-SYS-065", "FE9-SYS-066", "FE9-SYS-067", "FE9-SYS-077", "FE9-SYS-078", "FE9-SYS-079", "FE9-SYS-080"]
system_reviewed: ["FE9-SYS-055", "FE9-SYS-057", "FE9-SYS-058", "FE9-SYS-060", "FE9-SYS-061", "FE9-SYS-077", "FE9-SYS-078"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Maps

*How one chapter's battlefield is assembled from terrain, placed 3D scenery, and unit deployment*

A chapter's battlefield is built from two files that never touch each other directly but are laid out in the same physical space: [`map.cmp`](../formats/map-format.md) describes the terrain and every piece of scenery placed on it, and [`dispos.cmp`](../formats/dispo-format.md) describes which units are standing where when the chapter begins. Both live in the same `zmap/bmapNN/` folder, one per chapter (or per battle-map phase, for chapters with more than one).

!!! info "Mental model: stage, tiles, and actors"
    The map archive builds the **stage**: geometry, props, elevation, light, fog, and invisible markers. Deployment places the **actors** on the tactical tile grid. Event scripting then changes that state over time. A unit at tile (8, 5) is not a 3D prop instance at object coordinates (8, 5); the two systems merely render into the same scene.

## FE9-SYS-055 — Map-loading rules and lifecycle

<span id="fe9-sys-055"></span>

  Decompressing `map.cmp` doesn't give terrain data directly — it gives a [pack archive](../formats/pack-archive.md) bundling `map.bin` alongside that chapter's own 3D model files (terrain mesh, water plane, and any decorative props like trees or flower beds). `map.bin` itself is a set of named sections:

- **Capacity** — the map's grid dimensions (`x_size`/`y_size`) and a handful of other structural counts.
- **Objects** (`mapbuilddesc`) — one record per distinct placeable thing: the terrain itself, a water plane, decorative props, and invisible logic-only markers with no visual model at all. See [Map Objects & Placement](./map-objects.md).
- **Instances** (`mapbuildinst`) — one record per actual placement of an object into the world, with its own position and rotation. The same object can be placed more than once. See [Map Objects & Placement](./map-objects.md) and [Coordinate Systems & Grids](./map-grid.md).
- **Panels** (`uniquepanel` / `uniquepanelBase` / `uniquepanelRoof`) — per-tile corner elevation data: ground+object together, ground alone, and building roofs separately, which is what lets a unit standing on a rooftop read as physically higher than one on the ground beneath it.
- **Lighting, fog, and ambient grid settings** — single-record sections controlling the scene's overall look. A map's fog section, when present, stores whether fog is active, which rendering mode it uses, a screen-space offset, and an RGB tint; a map with no fog section simply leaves fog off.

  Two further systems build on this same map data: [Terrain Texture Blending](./terrain-texture-rendering.md) explains how a terrain material's textures actually blend on screen, and [Weather](./weather.md) covers optional ambient weather effects layered over the scene.

The loader establishes dependencies in order: dimensions and section addresses first; panel, terrain, link, object, light/fog, and extra state next; models and textures into the scene; then deployment and runtime grids. A mid-chapter `MapLoad` repeats construction for the replacement map. Scripts that change a tile or object afterward must request `MapUpdate` when occupancy, movement, danger, or presentation caches need rebuilding.

## What's inside dispos.cmp

  A separate [pack archive](../formats/pack-archive.md) holding four files: `dispos_c.bin`, whose groups appear on every difficulty, and `dispos_n/h/m.bin`, one of which the script picks by difficulty. Each is a list of named unit groups; a record names a character or generic enemy, their class, level, army, inventory, stat bonuses, spawn tile and the tile they walk to, and — for enemy units — their AI behavior for attacking, moving, and healing. See [Dispo Format](../formats/dispo-format.md) for the full field layout and [Characters](./characters.md)/[Classes](./classes.md) for what those IDs resolve to.

## Two coordinate systems, not one

  Positioning something on a map turns out to mean two different things depending on what's being positioned. [Placing a 3D object](./map-objects.md) (the terrain mesh, a tree, a water plane) uses one transform; [the tactical grid](./map-grid.md) a player actually moves units on uses a different, simpler one that happens to share the same base tile size. Both are covered in full, with their confidence levels clearly separated, on [Coordinate Systems & Grids](./map-grid.md).

## Worked example: placing a soldier beside a tree

  The tree is defined once as a map object and placed by an instance record using the scenery transform. The soldier is defined by a deployment record using tactical tile coordinates. Their visual proximity is the result of both coordinate systems resolving into the same world; there is no pointer from the soldier to the tree. Movement and occupancy rules apply to the soldier's tile, while the tree's footprint and flags describe scenery.

  The tactical camera itself rotates in fixed steps rather than spinning freely — each step is clamped to a set angle range and plays its own confirming sound cue, rather than exposing free continuous rotation.

## FE9-SYS-057 — Terrain-type system

<span id="fe9-sys-057"></span> Each combined panel resolves its terrain name against the 77-entry `TerrainData` table and stores the resulting type in a runtime grid. A type supplies its displayed name, Avoid/Def/Res bonuses, healing percentage, an object-tile bit, and fifteen movement costs. Combat reads the standing unit's tile from this grid; `SetTerrain` can replace the runtime type, but changing the rule grid alone does not repaint the mesh or texture.

Some display names are shared by several internal terrain identities. Impassability also is not one terrain flag: a cost of 255 blocks a movement type, the object bit excludes nearest-free placement, and directional link or height state can close an edge even when both endpoint terrain costs are finite.

## FE9-SYS-058 — Movement-type system

<span id="fe9-sys-058"></span> A class chooses one of the fifteen movement-cost columns. Infantry, armor, magic users, cavalry, fliers, thieves/bandits, and laguz therefore read different costs from the same tile. Flying movement also selects the alternate directional-link interpretation. The resulting cost grid is per unit: changing class or movement traits can change reachable tiles without changing the map.

## FE9-SYS-060 — Pathfinding and movement search

<span id="fe9-sys-060"></span> Movement range is a weighted four-neighbor flood fill. The engine uses two alternating frontier buffers, reads the unit's terrain-cost table, tests the applicable directional opening, rejects blocking occupancy, and relaxes a tile only when the new accumulated cost is strictly cheaper. Equal-cost arrivals therefore retain the route already recorded; deterministic frontier and direction traversal provide the tie break. Tiles whose best cost fits the movement budget are legal candidates, and route reconstruction follows those costs and the selected link mode back toward the start.

The map-link word assigns bits 0–3 to west/east/south/north ground openings, bits 4–7 to the corresponding flying blocks, and bits 8–11 to the threat-search `maplinkAt` directions. Threat edges cost 1 when the low opening or matching `maplinkAt` bit permits them and otherwise 2; a flying-block bit rejects the edge, while terrain `0x1C` can raise cost 1 to 3. Hold-position AI and deployment bridge restrictions are caller policies layered over these primitives, not hidden tie-breaking modes.

## FE9-SYS-061 — Occupancy and collision

<span id="fe9-sys-061"></span> Runtime occupancy maps a tile to its unit handle. `MapGetUnit` exposes that neutral grid directly and `MapUpdate` rebuilds it after scripted mutations; the grid itself does not decide whether an occupant may be passed, targeted, displaced, or used as a stopping tile. Movement, targeting, deployment, rescue/drop, shove, and scripted actions each apply their own allegiance, visibility, and action-state policy to the same lookup.

Deployment and `UnitSetPos`/`UnitMovePos` use a general nearest-free-tile search when their requested destination is occupied. That search rejects out-of-bounds, impassable/object, and eligible placed-object footprint tiles in addition to occupied tiles. Thus pass-through, stop, target, forced displacement, fog-hidden collision, and nearest-free placement form a matrix of caller rules; there is no missing universal collision table to infer from the occupancy map.

## FE9-SYS-077 — Fog of war

<span id="fe9-sys-077"></span> Gameplay fog is a visibility grid, not the colored distance fog used by the renderer. A map's `mapextra` sight bits select a runtime sight mode with difficulty gating. `SetSight(mode, unused)` consumes only its first argument in the US executable, changes that mode, recomputes the map-range overlay, and refreshes the map. A unit's vision getter supplies a Manhattan-radius source: most classes contribute 3, thieves, assassins, and beast laguz contribute 5, and Torch adds 4. Combining friendly sources sets or clears the hidden-by-fog unit-state bit (`0x40`).

That result is consumed before presentation: hidden enemies are omitted from ordinary inspection and target candidates, while movement or Drop can discover an unexpected occupant and produce the “!” ambush response. Range and danger displays therefore must be rebuilt after sight changes. A checkpoint preserves the active map state, and load reconstruction must recompute presentation consistently rather than reveal all units for one frame.

As a worked example, a sight-3 unit with Torch contributes the larger temporary view, then a `SetSight` event forces a visibility/range refresh. `SetFog`, by contrast, only changes the camera's distance-fog type, start/end distances, and color; it cannot reveal an enemy. Exact tile propagation at obstructions and the full inspection/AI exception matrix remain open.

## FE9-SYS-078 — Roof and interior visibility

<span id="fe9-sys-078"></span> Roof handling coordinates three representations. `uniquepanelRoof` supplies roof elevations; flagged roof/house object instances supply a rotated tile footprint; units inside an enabled footprint receive the under-roof state bit (`0x80`). That footprint also excludes tiles from general nearest-free placement, preventing a scripted relocation from casually placing a unit inside concealed geometry.

`RoofOpen`/`RoofClose` animate the matching section, instant variants jump to the result, and `SetRoofEnable` changes whether the section participates before refreshing the map. Opening records tile type `0x22`, so checkpoint reload reconstructs the revealed state. During event skip the animation jumps to its correct endpoint; state recording remains separate and must still converge with normal execution.

For a modded building, matching geometry is not enough: its footprint flags, roof panel elevations, open/close event, enabled state, and saved coordinate must describe the same area. Footprint membership is tested only while the map-wide footprint feature is enabled, the object is active, its descriptor allows footprint tests, and its runtime state is closed. `RoofOpen` changes that runtime endpoint and writes tile record `0x22`; instant and skipped routes reach the same endpoint without intermediate animation. Visibility/placement refresh follows the state change, so geometry presentation never decides occupancy or persistence.

## Interactions and review boundary

Map composition, terrain lookup, movement columns, weighted flood fill, link consumption, and the authoritative occupancy grid are established through decoded formats, named native searches, real-map corpora, and live edits. FE9-SYS-060's strict-cheaper relaxation closes equal-cost route selection; FE9-SYS-061's caller-owned legality closes the apparent collision-matrix gap; FE9-SYS-077's Manhattan source and `SetSight` refresh path close visibility propagation. FE9-SYS-078 is also closed at system level through descriptor/map gates, tile record `0x22`, and endpoint reconstruction. No new article is required for these systems.

FE9-SYS-062–065 are reviewed in [Tactical Interface](./tactical-interface.md), which owns overlay composition, targeting modes, cursor focus, hover filtering, and reconstruction. FE9-SYS-066 is reviewed in the focused [Map Camera](./map-camera.md) article. Keeping those view/controller systems separate prevents this page's pathfinding and occupancy rules from being confused with their presentation.
