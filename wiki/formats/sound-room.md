---
id: "sound-room"
title: "soundroom.bin"
description: "The list of pictures the Sound Room cycles through behind its track menu"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Graphics","Audio"]
aliases: ["tellius_archive.html#/sound-room"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/sound-room.md"
---
# soundroom.bin

*The list of pictures the Sound Room cycles through behind its track menu*

The Sound Room, the jukebox in the extras menu, plays the game's music over a full-screen illustration. `soundroom.bin` is the list of those illustrations. It does not hold the track list: the 64 playable tracks are a fixed table of `BGM_` names in the executable, and no picture belongs to a particular track. <span class="confidence confidence--confirmed">confirmed</span>

## Layout

  The file uses the same plain data container as [FE8Anim.bin](./fe8anim.md): a 32-byte header (file size, data size, pointer count and a symbol count of zero), the data, then the position of every pointer in the data so the loader can relocate it. There is no symbol table. The data is a record count, the records, then the picture names, sorted and stored once each.

<div class="table-wrap">
<table><thead><tr><th>Offset</th><th>Size</th><th>Field</th></tr></thead><tbody>
    <tr><td><code>+0x00</code></td><td>4</td><td>Pointer to the picture's <code>RID_</code> name: a resource of <a class="wl" href="../rect-format/"><code>s/rect.bin</code></a></td></tr>
    <tr><td><code>+0x04</code></td><td>2</td><td>X position, signed</td></tr>
    <tr><td><code>+0x06</code></td><td>2</td><td>Y position, signed</td></tr>
  </tbody></table>
</div>

## How the Sound Room uses it

  On opening, the menu loads the file and shows record 0. Each picture is created exactly as an event script's `RectBuild` would create it, then moved to the record's X and Y (the rect's position properties 0 and 1). The pictures form a slideshow that wraps at the record count:

- Playing a track with A shows the next picture.
- X hides the menu. While it is hidden, A or Right shows the next picture and Left the previous one; B, X or Start brings the menu back.
- The outgoing picture fades out over 64 frames while the new one fades in.

  Because the count is read from the file, pictures can be added, removed or reordered, and any rect resource can be used, including a new one. <span class="confidence confidence--confirmed">confirmed</span> An edited list has not yet been run in the game.

## The vanilla list

  Twenty-one pictures: event illustrations (`RID_再会と別離-A`/`-B`, “reunion and parting”; `RID_聖天馬騎士`, “holy pegasus knight”; `RID_クリミアの復興1`/`2`, “Crimea's restoration”; the tower, the Goldoan dragons and others), three views of the crumbling castle, and the exteriors of the six nations (Crimea, Daein, Phoenicis, Begnion, Gallia, Kilvas).

  The layout area is 608 × 448. The full-frame pictures sit at 0, 0. Larger ones use a negative offset to choose the part that is shown: the 608 × 800 tower is at Y −250, the 608 × 912 second restoration picture at Y −420, and the 856 × 480 crumbling-castle view at X −40.
