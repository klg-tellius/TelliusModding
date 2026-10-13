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
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/graphics-system.md"
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

## A background can hold more than one image

  A single background file commonly holds several images at once too — a day and night variant of the same location, or progressive damage states for a scene — each an independent image inside the same file, at its own fixed dimensions.
