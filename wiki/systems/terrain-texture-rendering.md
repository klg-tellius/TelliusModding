---
id: "terrain-texture-rendering"
title: "Terrain Texture Blending"
description: "Why a terrain material's extra textures need a runtime callback to ever appear at all"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Graphics","Structure"]
aliases: ["tellius_archive.html#/terrain-texture-rendering"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/terrain-texture-rendering.md"
system_entries: ["FE9-SYS-081"]
system_reviewed: ["FE9-SYS-081"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-13"
system_known_gaps: []
system_gap_work: []
---
# Terrain Texture Blending

*Why a terrain material's extra textures need a runtime callback to ever appear at all*

A map's [terrain model](../formats/map-format.md) can list several textures on one material, but listing them is not enough to make them all appear. Ordinary static rendering only ever binds the first texture on a material — anything beyond that requires the map system to register a callback for that specific material by name when its chapter loads, entirely separately from anything stored in the model file itself.

<span id="fe9-sys-081"></span>

## The default path: one texture, modulated

  Without a callback, a material's draw is about as simple as GameCube-era rendering gets: bind the first listed texture, and multiply it by the vertex/light color. This is the standard "texture times lighting" look used across most props and scenery that don't need special treatment.

## Rules and lifecycle: blending two more textures in

  For terrain that needs a richer surface — a road cutting across grass, for instance — the map system can attach up to two extra rendering steps to a named material at load time:

1. **A dual-sample blend.** The material's own first texture is sampled a second time, through the model's second UV set instead of its first, and the two samples are blended together by a grey mask: the image stored right after the first texture, laid over the map from above (see below). Black keeps the first sample, white the second — and the second shows whatever part of the image the second UV set points at there: on the Prologue the dirt path along its roads, the flower meadow and rocks elsewhere. This is how one texture image can represent two different surface looks (grass and dirt path, for instance) that blend smoothly instead of tiling as one flat image.
2. **A final overlay multiply.** Whatever the material's *last* listed texture is gets multiplied over the blended result, also laid over the map from above. For terrain, this is typically used as a soft light/shadow layer rather than a distinct visible surface.

  An optional third step can multiply in the moving cloud-shadow overlay described in [Weather](./weather.md), when the chapter's weather calls for it.

!!! info "Two textures can look like one, and one texture can look like several"
    Because the dual-sample step reuses the material's own first texture through a second UV set, a terrain material listing three texture slots doesn't necessarily mean three distinct images — it can mean one shared image sampled two different ways, plus one true overlay image.

## Where the on-the-fly textures come from

  Both images are stored in the map's texture file; what the game computes is where they fall. Their top-down texture coordinates come from a handful of per-map values — two panel-offset bytes, a half-width and half-height, and a projection-extent value, all in the map's extra-data section — combined with the base terrain's placement. For the mask the offsets cancel out: it always covers 640 × 640 units, 128 tiles at four pixels each, from the terrain's corner. On the Prologue the mask is a 512 × 512 greyscale image and the atlas a 512 × 1024 image whose top half the first UV set uses. <span class="confidence confidence--confirmed">engine + files</span>

## Worked example: one formula, four different maps

  The same projection formula, fed each map's own panel-offset, half-size, and extent values, produces a differently-scaled but structurally identical pair of blend/overlay textures for each map — confirmed across four separate chapter terrains built from the same base formula, each with its own offset and scale numbers rather than a shared hardcoded projection.

## Not every special material behavior is texture blending

  The same per-material callback mechanism also covers effects that have nothing to do with adding textures. A placed object such as a moving water/wave prop can carry a shape flag that switches its blend mode from ordinary opaque drawing to an additive blend: under that mode, a texture's black pixels contribute nothing to the final image and effectively vanish, while its lighter pixels add brightness on top of whatever is already drawn beneath. This is how a wave texture with genuinely solid black regions in its own source image can still read on screen as translucent white foam rather than as a black rectangle.

## Which materials get which step

  The dual-sample blend is attached by name, to materials called `map_base` or `map_wall`; `map_water` gets its own multi-pass step. The final overlay multiply is attached without a name, to every material of the terrain models. So a terrain material with any other name still has its last listed texture multiplied over it: a Prologue terrain rebuilt with its own material name and an all-white last texture drew its first texture unchanged. <span class="confidence confidence--confirmed">engine + in game</span>

## Native order and sampler state

Callback-array order is draw order. The projected dual callback first combines texture 0 sampled through UV0 and UV1 using the projected mask, then the global last-record callback multiplies the final material texture, and the optional common-texture callback multiplies the moving cloud overlay. The terrain images carry their sampler state in TPL: the shipped mipmapped map textures use repeat wrapping, trilinear minification, linear magnification, zero LOD bias, and one stored half-size level. Lighting enters through the raster color in the base sample before the later multiplicative stages. The final actor is submitted in its scene render list; these callbacks do not reorder unrelated objects.

## Interactions and limits

FE9-SYS-081 is reviewed without a blocking gap. Material-name selection, callback order, both UV sources, mask polarity, projection matrices, texture identities, TEV combination, mip/filter state, light modulation, weather overlay, and the separate water path are established. Emulator-versus-hardware pixel rounding remains a fidelity test rather than an unknown system rule.
