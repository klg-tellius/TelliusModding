---
id: "staffroll"
title: "staffroll.bin"
description: "The end credits: three columns per line, scrolled from the bottom of the screen"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Text"]
aliases: []
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/staffroll.md"
---
# staffroll.bin

*The end credits: three columns per line, scrolled from the bottom of the screen*

The staff credits that roll after the ending live in `ending/staffroll_noa.bin` (137 lines; the US release reads only this one) and `ending/staffroll.bin` (the shorter Japanese list, 111 lines). <span class="confidence confidence--confirmed">confirmed</span>

## Layout

  The file uses the plain data container shared with [soundroom.bin](./sound-room.md): a 32-byte header (file size, data size, pointer count, symbol count 2), the data, the position of every pointer in the data, then two symbols, `END_STAFFROLL_LINES` and `END_STAFFROLL_STRS`.

<table><thead><tr><th>Offset</th><th>Meaning</th></tr></thead><tbody>
<tr><td><code>+0x00</code></td><td>Pointer to the file's build time</td></tr>
<tr><td><code>+0x04</code></td><td>Pointer to its author's name</td></tr>
<tr><td><code>+0x08</code></td><td>Line count (<code>END_STAFFROLL_LINES</code>)</td></tr>
<tr><td><code>+0x0C</code></td><td>One 12-byte row per line (<code>END_STAFFROLL_STRS</code>): three string pointers, zero for an empty column</td></tr>
</tbody></table>

  The strings follow the rows, sorted and stored once each.

## How the credits are drawn

  The scroll length is the line count times 48 units, and each line advances by a fixed step. Each of the three columns is drawn only when its pointer is set: <span class="confidence confidence--confirmed">confirmed</span>

- the first column (a role such as "Producer") is right-aligned to x 288, just left of the screen's middle;
- the second (a heading such as `#F04Movie`) is centred on x 304 and carries its own font code;
- the third (a name) starts at a fixed x right of the middle and is drawn in the alpha font (`#F04%s`).

  A line with no column set is a blank line between groups.
