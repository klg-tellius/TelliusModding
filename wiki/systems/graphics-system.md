---
id: "graphics-system"
title: "Graphics & Images"
description: "Which folder holds which kind of image, and the constraints that come with each one"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Graphics"]
aliases: ["tellius_archive.html#/graphics-system"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/graphics-system.md"
system_entries: ["FE9-SYS-304", "FE9-SYS-305", "FE9-SYS-306", "FE9-SYS-307", "FE9-SYS-308", "FE9-SYS-309", "FE9-SYS-310", "FE9-SYS-311", "FE9-SYS-312", "FE9-SYS-313", "FE9-SYS-314", "FE9-SYS-315", "FE9-SYS-316", "FE9-SYS-318", "FE9-SYS-319", "FE9-SYS-320", "FE9-SYS-321", "FE9-SYS-322"]
system_reviewed: ["FE9-SYS-304", "FE9-SYS-305", "FE9-SYS-306", "FE9-SYS-307", "FE9-SYS-308", "FE9-SYS-309", "FE9-SYS-310", "FE9-SYS-311", "FE9-SYS-314", "FE9-SYS-315", "FE9-SYS-316", "FE9-SYS-318", "FE9-SYS-319", "FE9-SYS-320", "FE9-SYS-321", "FE9-SYS-322"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Graphics & Images

*Which folder holds which kind of image, and the constraints that come with each one*

Every 2D image in the game — backgrounds, portraits, UI chrome, world-map art — is stored as a [TPL texture](../formats/tpl-texture.md), either standalone or wrapped in [LZ10](../formats/lz10.md) compression. What varies by folder is what kind of image it is and how it's used, not the underlying container.

  This article covers 2D image resources specifically; for how a 3D terrain material blends multiple textures at once, see [Terrain Texture Blending](./terrain-texture-rendering.md).

## How to follow an image from system to pixels

First identify which game system requests the resource and by what name or path. Then remove any compression wrapper, parse the TPL image and palette, and finally apply resource-specific rules such as shared portrait palettes or background-label lookup.

## Example

A portrait request selects a file under `Face/`; LZ10 expands its `.cms` to a multi-image TPL whose base face and mouth/eye pieces may share one palette. A dialogue background instead resolves through [Rect.bin](../formats/rect-format.md) to a usually standalone CMPR TPL under `s/`.

<div class="table-wrap">
<table><thead><tr><th>Folder</th><th>Contents</th></tr></thead><tbody>
    <tr><td><code>s/</code></td><td>Full-screen backgrounds behind dialogue and menu scenes — the most common use of the format, always block-compressed (CMPR)</td></tr>
    <tr><td><code>Face/</code></td><td>Character portraits — LZ10-compressed, one file per character variant</td></tr>
    <tr><td><code>illust/</code></td><td>Full-screen CG illustration art</td></tr>
    <tr><td><code>ending/</code></td><td>Ending-sequence art</td></tr>
    <tr><td><code>window/</code></td><td>UI window chrome and layout art</td></tr>
    <tr><td><code>etc/</code></td><td>Miscellaneous graphics not covered by the other folders</td></tr>
    <tr><td><code>gmap/</code></td><td>World-map screen art</td></tr>
    <tr><td><code>zu/</code></td><td>Battle models (uncompressed packs, one per weapon type, and loose textures)</td></tr>
  </tbody></table>
</div>

## Portraits share one palette per character

  A portrait file holds several images at once — one large base face plus a handful of tiny animation-frame pieces (eye blinks, mouth flaps) — and, confirmed on real files, nearly all of them point at the exact same color palette. That's a real constraint on any replacement image: a new portrait is limited to that one shared palette's roughly 256 colors, because generating a fresh palette for just one of those images would recolor every sibling image sharing it too.

## Item and skill icons share one sheet

  `window/icon.tpl` holds every item and skill icon, cut into grids 32 cells wide. Its first image (768×216) has 24×24 cells: menu glyphs and buttons, then from cell 96 the item icons, one per item icon number. Its second image (1024×96) has 32×32 cells: 46 skill icons, blank frames, then status and unit-type badges; a skill's icon number *n* is cell *n* − 1. Each image has one palette shared by all its cells, so a new icon has to fit colours left in it. The game reads the copy bundled in `system.cmp`. <span class="confidence confidence--confirmed">confirmed</span>

## Texture system

<span id="fe9-sys-305"></span> TPL resources own encoded image data, dimensions, format, sampler state, optional palettes, and contiguous mip chains; LZ10 is only an outer transport wrapper. The native loader forwards wrap S/T, min/mag filters, LOD bias, edge LOD, and min/max LOD into the GX texture object. Every shipped mipmapped map/battle-scenery image uses trilinear minification, linear magnification, zero bias, and one half-size level, while ordinary non-mipmapped images use their own stored sampler values. Consumers resolve loaded archives before disc files, so the copies inside `system.cmp` take precedence over identical loose resources. Portrait siblings sharing one palette and icon sheets sharing one image palette remain critical replacement constraints.

## Icon atlas system

<span id="fe9-sys-309"></span> Icon identity is an index into one of two fixed grids in `window/icon.tpl`, not a separate image filename. Image 0 is 768×216 with 24×24 cells: menu glyphs occupy the prefix and item icon number *n* is cell `96 + n` (the renderer passes glyph `n + 0x61`). Image 1 is 1024×96 with 32×32 cells: visible skill icon number *n* is cell `n - 1`, zero draws none, and the later cells hold status, affinity-style, and unit-type badges addressed directly by their UI consumers. Each sheet has one shared palette, and the game reads the bundled `system.cmp` copy.

## Map models and overrides

<span id="fe9-sys-314"></span> **Map-model registry.** `FE8Anim.bin` maps all 508 animation records from identity to `ymu/` folder, supported weapon category, action clips, and army texture context without exceptions in the decoded registry. The class/character supplies the animation identity; the registry supplies resources and roles. See [Combat & Battle Animation](./combat-animation.md) for the presentation consumer.

<span id="fe9-sys-315"></span> **Slots and overrides.** Map presentation first uses a non-null character animation ID and otherwise falls back to the class animation ID. Detailed battle selection performs the parallel lookup in `jobList.dbx`: a matching `(JID, optional PID)` character-specific row outranks the class row. Character-tagged variants then specialize compatible textures/animations on the shared rig; an absent specialization falls back to the selected base record rather than inventing a resource name.

## Runtime rendering and presentation systems

<span id="fe9-sys-304"></span> **Render pipeline.** Scene cameras submit five ordered model lists. List 3 is drawn before ordinary geometry with the opaque preset; list 0 is opaque, list 1 alpha-tested, list 2 alpha-blended, and list 4 follows the blended pass. Shape flags normally route geometry into lists 0–2, while actor overrides can force all three shape families into one list. Late particles/effects and queued 2D primitives then compose presentation before the display copy. Scene owners decide what exists; each preset/callback must restore shared GX state for the following list.

<span id="fe9-sys-306"></span> **2D sprite/UI compositor.** UI callers enqueue primitive records—observed draw types include 5, 6, 7, 8, and `0xA`—carrying a TPL/atlas image, source and destination rectangles, palette/color, clipping, blend state, and layer. The compositor flushes those queues in type/layer order after the scene passes. Windows, icons, portraits, glyphs, and overlays are consumers of this presentation queue, never authoritative gameplay state.

<span id="fe9-sys-307"></span> **UI layout.** `Rect.bin` and screen-specific layout resources provide absolute rectangles and resource bindings; runtime widgets add parent/child relationships, focus, visibility, and refresh state. Children inherit scene/widget ownership rather than tactical coordinates. A widget may remember cursor or focus, but it rebuilds displayed values from authoritative systems after mutation; malformed or overlapping authored rectangles are a resource-validation problem, not a hidden gameplay rule.

<span id="fe9-sys-308"></span> **Font and glyph system.** The US build has five indexed bitmap fonts. A GCF file has a 0x30-byte header, sorted 16-byte glyph records, and I4 texture sheets. Input decoding accepts one-byte characters or valid two-byte CP932 sequences; lookup caches the last glyph, then binary-searches the table. Missing codes fall back to `0x8199` (white star), or to the first record (space) when that font lacks the star. Drawing binds the record's sheet, places a quad at bearing X and `baseline + ascent - bearingY`, and advances by its signed advance. The selected primitive type and `#F` markup choose system, dialogue, Tellius, large-label, or credits fonts; all five remain resident.

<span id="fe9-sys-310"></span> **3D model loading.** A model actor joins `.g` skeleton records, `.gs` shape/material/display-list data, TPL textures, and optional `.ga` animation. Relocated pointers and counts identify every array; shapes select rigid, hardware multi-matrix (at most ten bones), or CPU-blended vertices. Animation channels overwrite the skeleton value block before local/world matrices are rebuilt. Resource identity comes from the map/battle/effect registry and folder; allocation is actor-owned, while missing required geometry/skeleton data rejects actor construction and teardown releases the linked buffers as one unit.

<span id="fe9-sys-311"></span> **Material/render state.** Shape-list selection supplies the base opaque, alpha-test, or blended preset. Shape flags then define additive (`src alpha + one`) or subtractive blending, depth-test/write suppression, cull mode, hidden state, camera-transition behavior, and callback bypasses; material records provide texture ids and colors. Map setup may install name-based callbacks and mark the material for extra stages even when raw material flags are zero. Each callback binds its textures/TEV stages for that draw, and the next list/material preset re-establishes shared state.

<span id="fe9-sys-316"></span> **Map-unit animation.** The map actor consumes FE8Anim identity, facing, status/visibility, weapon context, and an action bit. Registry actions are ordered wait, move, attack 1/2, critical, rod, tackle, escape, ready, damage, transform, dead, magic 1/2, critical 2, move 2, and event. If the requested action bit is absent, selection falls back to tackle. The actor controller advances the clip, emits markers, and returns to its legal idle/final state.

<span id="fe9-sys-318"></span> **Effect registry.** `FE8Effect.bin` is the same relocated-container family as `FE8Anim.bin` and contains 263 fixed 12-byte records under its exported effect table. Every record holds a resolved `EID_*` name pointer, a four-byte flags word, and an optional pointer to another effect record. The pointer is a chain link rather than a fixed sibling: following a tiered entry such as `EID_FIRE4` reaches `_2`, `_3`, and finally a `_2D` terminal, with at most three links in shipped data. All 263 names resolve, and the chain graph is finite in the retail file. Callers look up the symbolic ID, walk the configured chain as their presenter requires, load the corresponding `yme/` resources, create/update/draw the instances, then release them. The registry selects visual resources; it does not own the combat or script consequence being illustrated.

<span id="fe9-sys-319"></span> **Particle emitters.** Effect animation footer slot 8 begins with magic `0x12345678`, relocation state, and an emitter count. Each 0x34-byte emitter points to per-stage timing/initial XYZ, curve ranges, 0x0C-byte curve descriptors, and `(frame, signed value)` keys. Stage positions scale by 1/64; curves drive translation, scale, rotation, and RGBA. Low draw-flag bits choose line or textured-stage paths, with additional bits controlling actor visibility, additive/subtractive blending, depth testing, and TEV order. The retail corpus contains 177 such blocks, 574 emitters, and all pointer/range checks pass. Instance lifetime and actor attachment remain presentation-only.

<span id="fe9-sys-320"></span> **Screen transitions.** Fade/wipe objects store their start and requested final color/alpha, duration, and progress while taking scene/input presentation control. Their process exposes asynchronous completion and releases that ownership at the endpoint. Skip jumps directly to the same final values and completion signal, so required scene mutations never depend on observing intermediate frames.

<span id="fe9-sys-321"></span> **Lens flare and post effects.** These run after main scene geometry, project a light/effect source through the final camera, reject or clip off-screen elements, and blend screen-space sprites in the late effect pass. Visibility, spacing, color, and intensity belong to that presenter. Creating or removing the effect cannot change tactical illumination, fog visibility, targeting, or saved map state.

<span id="fe9-sys-322"></span> **Visibility and culling.** Actor state and descriptor flags reject hidden or draw-suppressed objects before shape traversal. Ordinary bounds use the camera frustum; descriptor bit `0x08` selects the extended overlap test and is also installed for multi-tile footprints. Per-shape cull bits select back, front, none, or inherited culling, with an actor mirror flag swapping front/back. Hidden shape bit `0x400` suppresses shipped weapon placeholders, while actor/list override flags reroute rather than delete geometry. These checks affect update/draw submission only; tactical existence and saved state remain authoritative elsewhere.

## A background can hold more than one image

  A single background file commonly holds several images at once too — a day and night variant of the same location, or progressive damage states for a scene — each an independent image inside the same file, at its own fixed dimensions.

## Known gaps and scope limits

All graphics entries assigned to this page are reviewed without a blocking research gap. Executable and full-corpus traces establish formats, ordered render paths, 2D queues/layout ownership, model override priority, map-action fallback, transition convergence, post-effect boundaries, and teardown. Specialist format/rendering pages carry deeper byte tables; no new primary article is required.
