---
id: "rd-world-map-routes"
title: "World-map route lines (Radiant Dawn)"
description: "gmap/curve: the curves an army's route is drawn along, and the line styles"
games: ["radiant-dawn"]
section: "formats"
article_type: "format-reference"
tags: ["Maps","Radiant Dawn"]
aliases: []
status: "published"
last_reviewed: "2026-11-15"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/rd-world-map-routes.md"
---
# World-map route lines (Radiant Dawn)

*gmap/curve: the curves an army's route is drawn along, and the line styles*

When a world-map scene shows an army on the move, the game draws a textured line along a curve, read from `gmap/curve/<name>.bin`. The name follows the chapter (`curve0105_1`, `curve0304_12`); four `curveTest` files are leftovers. Up to eight routes can be on screen at once. <span class="confidence confidence--confirmed">engine</span>

## Curve files

  Big-endian, a 0x30-byte header and then the points: <span class="confidence confidence--confirmed">engine + files</span>

<div class="table-wrap">
<table><thead><tr><th>Offset</th><th>Field</th></tr></thead><tbody>
    <tr><td>+0x00</td><td>Zero</td></tr>
    <tr><td>+0x04</td><td>The curve's name, padded with NULs to 24 bytes</td></tr>
    <tr><td>+0x1C</td><td>Frames the line takes to draw (65 to 300)</td></tr>
    <tr><td>+0x20</td><td>Point count</td></tr>
    <tr><td>+0x24</td><td>Line style 0–7: the line picture in <code>gmap/tpl/gmap.tpl</code> and the style file <code>linedefine&lt;style+1&gt;.bin</code></td></tr>
    <tr><td>+0x28</td><td>Colour: 0, 1, 2 or other, one of four colour pairs in the game code (retail uses 0, 1 and 2)</td></tr>
    <tr><td>+0x2C</td><td>Zero on disc; the loader stores the points' address there</td></tr>
  </tbody></table>
</div>

  A point is six floats: x, y and z, then a tangent x, y and z. Both z values are zero everywhere, and x and y are pixels on the 608 × 448 screen. The line bends through the points following their tangents; the app's preview draws a cubic Hermite curve, which follows the same points and tangents, though the game's own interpolation was not traced in full. <span class="confidence confidence--strong">engine + files</span>

## Line styles

  The eight `linedefine<n>.bin` files hold two little-endian doubles, unusual on this big-endian console. The game swaps them once after loading and records that by writing a 1 at +0x10. The Japanese disc's copies end before that word. The first double scales the line's width (10 for most styles, 5 and 15 for others); the second is the length one repeat of the line texture covers. <span class="confidence confidence--confirmed">engine</span>

  The Japanese disc lacks six US curves (`curve0304_11` to `_16`). Every curve and style file on the three discs rebuilds byte for byte. <span class="confidence confidence--confirmed">files</span>
