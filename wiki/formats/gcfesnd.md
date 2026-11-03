---
id: "gcfesnd"
title: "gcfesnd.bin"
description: "The game-specific sound cue catalog layered above the MusyX engine"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Audio","Registry"]
aliases: ["tellius_archive.html#/gcfesnd"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/gcfesnd.md"
---
# gcfesnd.bin

*The game-specific sound cue catalog layered above the MusyX engine*

`gcfesnd.bin` is the game-specific catalog above [MusyX](./musyx.md). It contains symbolic `BGM_*` cue names, roughly 1,150 `SFX_*` names, and the filenames of streamed [STM music tracks](./stm-format.md).

## Record array

  After a 0x20-byte header, a flat array of self-sized records runs until a zero length byte: 148 twelve-byte `BGM_*` records, then 1,154 twenty-byte `SFX_*` records. All fields are big-endian.

<div class="table-wrap">
<table class="wikitable"><tr><th>Offset</th><th>Size</th><th>SFX field</th></tr>
  <tr><td>+0x00</td><td>4</td><td>Name string offset (add 0x20)</td></tr>
  <tr><td>+0x04</td><td>1</td><td>Record length, always 20</td></tr>
  <tr><td>+0x05</td><td>1</td><td>Flags; low 2 bits select the voice class (values 0, 1, 8 seen)</td></tr>
  <tr><td>+0x06</td><td>1</td><td>Default volume, 0-127</td></tr>
  <tr><td>+0x07</td><td>1</td><td>Pan (0x40 = centre on 1,131 of 1,154 cues)</td></tr>
  <tr><td>+0x08</td><td>4</td><td>Sound id into the MusyX banks; several cues share one id (0x158 is the silent dummy)</td></tr>
  <tr><td>+0x0C</td><td>4</td><td>Four small bytes, first usually 0x1E (priority/range-like, inferred from the game's accessors)</td></tr>
  <tr><td>+0x10</td><td>4</td><td>Distance-like value (2000, 100, 200, 150, 750 ...)</td></tr></table>
</div>

  Cue names group by second component: BTL (632), BMP (214), ARAM (114), SYS (71), EVT (59), ENV (52) and a few others. The meaning of the last two fields is inferred, not proven.

## How a cue name reaches audio data

  The SFX portion contains an ascending numeric-ID/string-offset table. BGM playback instead passes a symbolic name into a generic native lookup. That lookup computes two polynomial hashes (multipliers 37 and 31); the first selects one of 509 buckets, while the second helps reject collisions in the bucket's linked list.

  At boot the loader walks the record array by each record's length byte and registers every record under its name, wherever it sits. BGM playback reads only the record the name resolves to: its type byte selects the voice (every music record is a streamed voice) and its path names the `.stm` file. A music record added after the sound effects therefore plays like a retail one. <span class="confidence confidence--confirmed">engine</span>

  The bucket table is populated in zero-initialized runtime memory. Consequently the executable proves how names are resolved, while a static copy of the DOL cannot by itself show the final cue-to-loaded-track mapping for every BGM name.
