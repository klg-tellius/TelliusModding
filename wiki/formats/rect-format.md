---
id: "rect-format"
title: "Rect.bin"
description: "The game-wide table of full-screen images and how each one is animated and shown"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Graphics","Registry"]
aliases: ["tellius_archive.html#/rect-format"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/rect-format.md"
---
# Rect.bin

*The game-wide table of full-screen images and how each one is animated and shown*

Every full-screen picture that an event can put on screen is a **rect resource**: conversation and cutscene backgrounds, the illustrated region maps, the title screen and its animated flame, the game-over and ending art. `s/rect.bin` holds them all. Each resource has a Japanese-derived name beginning `RID_` (for example `RID_街-夜`, “town, night”), points at one or more images of a file in `s/`, and carries the few settings that decide how those images are animated and shown. The `s/` files themselves are ordinary [TPL textures](./tpl-texture.md); the file names are opaque three-character codes, so the resource names are what identify a picture.

## How a script uses a resource

  An event script calls `RectBuild("RID_…")` to create the image (or `RectLeave` to create it without tying it to the running event). The name is looked up in the engine's global name table, which the resource file fills when it loads. The resulting image can then be moved, faded, scaled, rotated, brightened or removed with the other `Rect*` calls. `RectPreLoad` loads a resource's textures ahead of time so it appears without a hitch. <span class="confidence confidence--confirmed">confirmed</span>

## What a resource contains

<div class="table-wrap">
<table><thead><tr><th>Setting</th><th>Meaning</th></tr></thead><tbody>
    <tr><td>Layers</td><td>One to 255 images. Each names a texture file, the image number inside it, the rectangle of the texture to show (all vanilla layers show the whole texture) and an alpha.</td></tr>
    <tr><td>Composition mode</td><td>How several layers combine: <strong>stack</strong> them, show them as a hard <strong>flip-book</strong>, or <strong>cross-fade</strong> from one to the next. All 195 vanilla resources use cross-fade.</td></tr>
    <tr><td>Period</td><td>Seconds for one pass through all layers, from 0.8 s up to 10 s. A resource with one layer never changes, so its period is irrelevant.</td></tr>
    <tr><td>Brightness</td><td>255 leaves the picture alone; smaller values darken it. Vanilla uses 122–255 (full-frame art is always 255); many conversation backdrops are dimmed a little so the dialogue box reads clearly.</td></tr>
    <tr><td>Overlay</td><td>An optional self-running weather or particle effect drawn with the picture: snow (the eleven snow scenes), sand (the desert), mist (the river plain) and a particle overlay used by the two altar scenes.</td></tr>
  </tbody></table>
</div>

## Animation

  With several layers the resource is a short looping animation. A clock advances once per frame so that one pass over all layers lasts exactly the period; each layer owns an equal share. In cross-fade mode the current layer is drawn opaque and the next one fades in over it, then the cycle continues and wraps. The layers are usually lighting variants: the night version of the command room (`RID_アジト-作戦室-夜`) is four candle-flicker frames over 1.85 seconds; a door scene has an open and a closed state; the title flame is forty frames over ten seconds. <span class="confidence confidence--confirmed">confirmed</span>

!!! info "Size and pivot"
    A resource is as large as its first layer's rectangle. That size is also its default pivot (half the width and height), the origin of scaling and rotation, and what the “align inside the 608 × 448 layout area” script call measures.

## Properties scripts can change

  A shown image keeps eleven properties, addressed by number by `RectSet`, `RectGet` and `RectSetCurve`: X and Y position, a depth offset, the pivot X and Y, horizontal and vertical scale (percent), rotation, opacity (0–255) and brightness (0–255, 128 is normal). Opacity and brightness are reset after every drawing pass so they never leak into other graphics. <span class="confidence confidence--confirmed">confirmed</span>

## The images

- 195 distinct texture files, none shared between resources, holding 316 images. Almost all are CMPR; the title logo is RGB565 and two others are RGB5A3.
- Most resources are 608 × 296 (the strip above the dialogue box, 114 of them) or 608 × 448 (full frame, 39). Region exteriors are 664 × 448; the title is 512 × 320; scrolls and world-map pieces run taller (up to 608 × 912) or wider (up to 1024 × 616, the largest a texture can be).
- Three files in `s/` are used by no resource.
- One vanilla resource asks for two more rows than its texture has; the extra rows are simply never drawn.

## What a new resource needs

  The game finds a texture file by path, first among the loaded archives and then on the disc, so a new file under `s/` with any name is found. The resource needs a name, at least one layer, and a texture no larger than 1024 pixels on either side; the resource table itself is a relocatable file whose export list must stay sorted by name. Because the game reads the copy inside `system.cmp`, an edited table has to be present there. <span class="confidence confidence--strong">strong evidence</span> An edited table has not been run in the game.

## The other resource files

  The window and ending files (`window/RectDesc.bin`, `RectBases.bin`, `RectUnitList.bin`, `ending/RectFinale.bin`) use the same container and descriptor and differ only in the kinds of layer they hold. Besides the textured quad, a layer can be a **text line** (a message ID or literal text with inline markup, a position and an alignment), a **rectangle with four corner colours** (panels, letterbox bars, fade masks; the corners run upper-left, upper-right, lower-left, lower-right), a **quad with corner colours**, a **dialogue textbox** (frame, panel and cursor resources, text origin, width, line height, line count, typing speed, portrait seat) and a **seat table** (where each portrait stands and which way it faces). <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>File</th><th>What it defines</th></tr></thead><tbody>
    <tr><td><code>window/RectDesc.bin</code></td><td>The shared interface vocabulary, loaded at boot: the nine dialogue layouts (up-down, background, no-background, world-map, tutorial&amp;hellip;), the text-window frames, the page and world-map cursors (16- and 12-frame flip-books), the weapon-triangle icons, the cinema letterbox and the fade masks.</td></tr>
    <tr><td><code>window/RectBases.bin</code></td><td>The base shop windows: a frame with a title strip and a dialogue box for each of the four shops, and the warehouse plate.</td></tr>
    <tr><td><code>window/RectUnitList.bin</code></td><td>The unit-list panel.</td></tr>
    <tr><td><code>ending/RectFinale.bin</code></td><td>The ending: 22 illustration slides, one portrait per character, and the whole staff roll as text resources.</td></tr>
  </tbody></table>
</div>

  Everything in these files is plain data, so text, positions, colours and images can be changed without touching the executable. The Sound Room's slideshow is a list of these resources too: see [soundroom.bin](./sound-room.md).

Each text line and each dialogue textbox carries two switches: a drop shadow (2 pixels, black at half opacity) and a 1-pixel black outline. Lines with icons and three large headings (Staff Credits, Satoru Iwata, Demonstration) use the outline; every dialogue textbox except the choice dialog uses both. <span class="confidence confidence--confirmed">confirmed</span>
