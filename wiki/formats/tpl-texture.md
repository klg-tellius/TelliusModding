---
id: "tpl-texture"
title: "TPL Texture"
description: "GameCube/Wii's native texture container, in nine of its pixel-format variants"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Graphics"]
aliases: ["tellius_archive.html#/tpl-texture"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/tpl-texture.md"
---
# TPL Texture

*GameCube/Wii's native texture container, in nine of its pixel-format variants*

TPL is GameCube/Wii's native texture container—part of the standard GX texture specification and not specific to this game. A file can hold several images, each tagged with its own pixel format. Path of Radiance uses **nine** variants across its complete texture set.

<div class="table-wrap">
<table><thead><tr><th>ID</th><th>Format</th><th>Bits/px</th><th>Palette</th><th>Where it's used</th></tr></thead><tbody>
    <tr><td class="num">14</td><td><code>CMPR</code></td><td class="num">4</td><td>No</td><td>Full-screen images — chapter backgrounds</td></tr>
    <tr><td class="num">9</td><td><code>C8</code></td><td class="num">8</td><td>Yes (256)</td><td>Character portraits; several images per file often share <em>one</em> palette</td></tr>
    <tr><td class="num">8</td><td><code>C4</code></td><td class="num">4</td><td>Yes (16)</td><td>Smaller UI art</td></tr>
    <tr><td class="num">0</td><td><code>I4</code></td><td class="num">4</td><td>No</td><td>Plain grayscale UI art</td></tr>
    <tr><td class="num">2</td><td><code>IA4</code></td><td class="num">8</td><td>No</td><td>Grayscale + alpha, 4+4 bit — soft/transparent edges</td></tr>
    <tr><td class="num">3</td><td><code>IA8</code></td><td class="num">16</td><td>No</td><td>Grayscale + alpha, 8+8 bit</td></tr>
    <tr><td class="num">4</td><td><code>RGB565</code></td><td class="num">16</td><td>No</td><td>Full color, opaque only — incl. the title-screen logo</td></tr>
    <tr><td class="num">5</td><td><code>RGB5A3</code></td><td class="num">16</td><td>No</td><td>Color + alpha as a direct pixel format — small map icons</td></tr>
    <tr><td class="num">6</td><td><code>RGBA8</code></td><td class="num">32</td><td>No</td><td>Full RGBA; unusual tiling (below) — translucent UI panels</td></tr>
  </tbody></table>
</div>

!!! info "RGB5A3 has two pixel layouts"
    Bit 15 selects the layout. When set, the remaining 15 bits are opaque RGB555. When clear, the word stores 3-bit alpha plus 4 bits each of red, green, and blue. C8 and C4 images store palette indexes; their palette entries may use this same RGB5A3 encoding.

  RGBA8 uses a distinctive 4×4 tiled layout: each tile stores all alpha/red pairs first, followed by all green/blue pairs. See [Rect.bin](./rect-format.md) for how full-screen images are named, animated and shown.

## The image header

  Each image has a 0x24-byte header: height and width (2 bytes each), the pixel format, the offset of its pixel data, the horizontal and vertical wrap modes (0 clamp, 1 repeat), the minification and magnification filters, a float LOD bias, then four bytes: edge-LOD enable (`+0x20`), minimum LOD (`+0x21`), maximum LOD (`+0x22`) and an "unpacked" byte (`+0x23`). The game passes the wrap, filter and LOD-bias values to the GameCube's texture hardware as stored. <span class="confidence confidence--confirmed">engine</span>

## Mip levels

  A **mip level** is a smaller copy of an image that the hardware samples when the surface is far from the camera, so distant ground does not shimmer. When an image's maximum LOD is above its minimum LOD, *max − min* extra levels follow its pixel data, back to back: each is half the previous width and height (never below 1 pixel), in the same pixel format and the same tiling. They sit inside the image's own data, before anything else in the file. <span class="confidence confidence--confirmed">whole disc</span>

  Only 3D scenery uses them. In the chapter maps' shared texture file (`zmap/*/map.cmp` → `texpack.tpl`) 696 images carry them, and in the battle-scenery packs (`zbg/`) 828 of 839; elsewhere only `etc/fire.tpl` does. Every one has the same settings: one extra level (LOD 0 to 1), trilinear minification (filter 5, blending between pixels and between the two levels), linear magnification, no LOD bias. The 11 battle-scenery images without a level use plain linear filtering. The stored level matches a 2×2 box average of the full-size image. <span class="confidence confidence--confirmed">whole disc</span>

  *Example:* image 0 of the Prologue's `texpack.tpl` is a 512×1024 CMPR terrain atlas (0x40000 bytes); its 256×512 level follows directly (0x10000 bytes), and image 1's data starts after that.

## How an image reaches the screen

A TPL image header selects dimensions, pixel format, and possibly a palette. The renderer interprets pixels in GX tiles rather than ordinary left-to-right rows. The surrounding game system chooses the TPL resource—portrait, background, UI element, or icon—and may first remove an LZ10 wrapper.

## Worked replacement

Replacing a C8 portrait image means resizing to the slot dimensions, mapping each new pixel to the existing shared palette, tiling indexes in C8 order, and recompressing the containing `.cms`. Regenerating a palette for only one image can recolor sibling mouth or eye frames that point to the same palette. Replacing an image that has mip levels means rebuilding each level from the new picture as well; otherwise the old picture reappears whenever the surface is seen from a distance.

## Known limits

The nine pixel formats listed here are decoded. Resource-specific animation timing, icon indexing, and UI placement belong to their consumer formats rather than TPL itself.
