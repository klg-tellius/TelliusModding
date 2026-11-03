---
id: "regional-releases"
title: "Regional Releases"
description: "What differs between the North American, European and Japanese discs of Path of Radiance, file by file"
games: ["path-of-radiance"]
section: "systems"
article_type: "reference"
tags: ["Structure", "Save Data"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/regional-releases.md"
---
# Regional Releases

*What differs between the North American, European and Japanese discs of Path of Radiance, file by file*

Path of Radiance shipped on three discs: North America (`GFEE01`), Europe (`GFEP01`) and Japan (`GFEJ01`). They run the same engine on the same data formats. Most files are byte-identical or differ only in their text, and a modding tool built for one release reads the other two with a short list of exceptions, all described below. <span class="confidence confidence--confirmed">data + engine</span>

## Files that are identical

Every map (`zmap/`), every deployment file, every 3D model, skeleton and animation, the battle effect tables and the sound banks match byte for byte, or differ only where they hold text. Every file format reads and rebuilds without loss on all three discs, and no file on the European or Japanese disc uses a format the North American one does not. <span class="confidence confidence--confirmed">data</span>

## Text

<div class="table-wrap">
<table><thead><tr><th>Release</th><th>Languages</th><th>How letters are stored</th></tr></thead><tbody>
    <tr><td>North America</td><td>English</td><td>Shift-JIS (code page 932); English text is plain ASCII</td></tr>
    <tr><td>Japan</td><td>Japanese</td><td>Shift-JIS (code page 932)</td></tr>
    <tr><td>Europe</td><td>English, German, French, Italian, Spanish</td><td>A mix: a byte from <code>0x81</code> to <code>0x9F</code> starts a two-byte Shift-JIS character (kana and kanji, used in labels); every other byte is one Latin-1 character, so <code>0xE0</code> is "à" and <code>0xFC</code> is "ü"</td></tr>
  </tbody></table>
</div>

  The European fonts carry glyphs at the single-byte codes `0xA1`&ndash;`0xFF` for those letters. The European disc keeps each language in its own message files: `Mess/c01.m` for English, then `d_` (German), `f_` (French), `i_` (Italian) and `s_` (Spanish) in front of the same names. Its menus read the loose `Mess/common.m` files, because its `system.cmp` carries no messages. The tutorial pages are likewise split into `tut_data_en.bin`, `tut_data_de.bin` and so on, where the other discs have one `tut_data.bin`. <span class="confidence confidence--confirmed">data</span>

## Fonts

  The European disc has no `Fonts/system.cms`. Its executable loads the uncompressed `Fonts/system.gcf` instead, while the North American and Japanese executables load the compressed `.cms` and never read their `system.gcf`. The European fonts are larger because of the accented letters. The game's 35 text colours are the same on all three discs. <span class="confidence confidence--confirmed">engine</span>

## Chapter records

  The Japanese release has no Easy mode, which shows in its chapter table (`ChapterData` in `FE8Data.bin`):

- each record is `0x5C` bytes instead of `0x60`: it keeps three enemy bonus levels (Normal, Hard, Maniac) where the other releases keep four;
- its first field is the chapter title itself ("序章　傭兵"), where the other releases name a message key (`MCT01`); the trial maps name a message key on every disc.

  Every other field is the same, at the same place relative to the start of the record, up to the bonus levels. The European chapter table is the same as the North American one. <span class="confidence confidence--confirmed">data</span>

## Saves

  The save format is the same on all three discs. Every part of the saved game (units, items, convoy, forges, party, map state) is written by the same code, so a save block has the same layout everywhere. Two things tell the releases apart: <span class="confidence confidence--confirmed">engine</span>

- the block magic and version: North America and Japan write `FE8J` and `0x20050201`, Europe writes `FE8X` and `0x20050801`. Each loader accepts only its own pair, so a save does not carry over between releases;
- the memory-card file name: `FIREEMBLEM8J` in North America and Japan, `FIREEMBLEM8` in Europe.

  The title and date text in a block's header are formatted for the release's language.

## The executable

  Most functions of the three executables are the same code at different addresses. The code that differs concerns text: string addresses, date formats, font loading and the language choice. See [main.dol](../formats/main-dol.md) for how the functions are matched across releases. <span class="confidence confidence--confirmed">engine</span>

## Timing on 50 Hz European consoles

  The European disc can run at 50 Hz or 60 Hz, and some code checks which. The `WaitM` script function, which waits a number of milliseconds, divides by 20 ms per frame at 50 Hz and by 16.67 ms at 60 Hz, so a wait lasts the same real time either way; the `EventQuake` screen shake likewise switches its timing constants. `WaitF`, which waits a number of frames, is the same code on every disc, so at 50 Hz a frame wait lasts a fifth longer. <span class="confidence confidence--confirmed">engine</span>

## Other known differences

- The Japanese release gives no class-level critical bonus (see [Combat Mechanics](./combat-mechanics.md)).
- The Japanese `C02` script's string pool ends with two stray bytes after its last string; they are never read.
