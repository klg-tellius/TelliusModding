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
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/maps-system.md"
---
# Maps

*How one chapter's battlefield is assembled from terrain, placed 3D scenery, and unit deployment*

A chapter's battlefield is built from two files that never touch each other directly but are laid out in the same physical space: [`map.cmp`](../formats/map-format.md) describes the terrain and every piece of scenery placed on it, and [`dispos.cmp`](../formats/dispo-format.md) describes which units are standing where when the chapter begins. Both live in the same `zmap/bmapNN/` folder, one per chapter (or per battle-map phase, for chapters with more than one).

!!! info "Mental model: stage, tiles, and actors"
    The map archive builds the **stage**: geometry, props, elevation, light, fog, and invisible markers. Deployment places the **actors** on the tactical tile grid. Event scripting then changes that state over time. A unit at tile (8, 5) is not a 3D prop instance at object coordinates (8, 5); the two systems merely render into the same scene.

## What's inside map.cmp

  Decompressing `map.cmp` doesn't give terrain data directly — it gives a [pack archive](../formats/pack-archive.md) bundling `map.bin` alongside that chapter's own 3D model files (terrain mesh, water plane, and any decorative props like trees or flower beds). `map.bin` itself is a set of named sections:

- **Capacity** — the map's grid dimensions (`x_size`/`y_size`) and a handful of other structural counts.
- **Objects** (`mapbuilddesc`) — one record per distinct placeable thing: the terrain itself, a water plane, decorative props, and invisible logic-only markers with no visual model at all. See [Map Objects & Placement](./map-objects.md).
- **Instances** (`mapbuildinst`) — one record per actual placement of an object into the world, with its own position and rotation. The same object can be placed more than once. See [Map Objects & Placement](./map-objects.md) and [Coordinate Systems & Grids](./map-grid.md).
- **Panels** (`uniquepanel` / `uniquepanelBase` / `uniquepanelRoof`) — per-tile corner elevation data: ground+object together, ground alone, and building roofs separately, which is what lets a unit standing on a rooftop read as physically higher than one on the ground beneath it.
- **Lighting, fog, and ambient grid settings** — single-record sections controlling the scene's overall look. A map's fog section, when present, stores whether fog is active, which rendering mode it uses, a screen-space offset, and an RGB tint; a map with no fog section simply leaves fog off.

  Two further systems build on this same map data: [Terrain Texture Blending](./terrain-texture-rendering.md) explains how a terrain material's textures actually blend on screen, and [Weather](./weather.md) covers optional ambient weather effects layered over the scene.

## What's inside dispos.cmp

  A separate [pack archive](../formats/pack-archive.md) holding four files: `dispos_c.bin`, whose groups appear on every difficulty, and `dispos_n/h/m.bin`, one of which the script picks by difficulty. Each is a list of named unit groups; a record names a character or generic enemy, their class, level, army, inventory, stat bonuses, spawn tile and the tile they walk to, and — for enemy units — their AI behavior for attacking, moving, and healing. See [Dispo Format](../formats/dispo-format.md) for the full field layout and [Characters](./characters.md)/[Classes](./classes.md) for what those IDs resolve to.

## Two coordinate systems, not one

  Positioning something on a map turns out to mean two different things depending on what's being positioned. [Placing a 3D object](./map-objects.md) (the terrain mesh, a tree, a water plane) uses one transform; [the tactical grid](./map-grid.md) a player actually moves units on uses a different, simpler one that happens to share the same base tile size. Both are covered in full, with their confidence levels clearly separated, on [Coordinate Systems & Grids](./map-grid.md).

## Worked example: placing a soldier beside a tree

  The tree is defined once as a map object and placed by an instance record using the scenery transform. The soldier is defined by a deployment record using tactical tile coordinates. Their visual proximity is the result of both coordinate systems resolving into the same world; there is no pointer from the soldier to the tree. Movement and occupancy rules apply to the soldier's tile, while the tree's footprint and flags describe scenery.

  The tactical camera itself rotates in fixed steps rather than spinning freely — each step is clamped to a set angle range and plays its own confirming sound cue, rather than exposing free continuous rotation.
