---
id: "font-format"
title: "Font"
description: "Five bitmap fonts: a glyph table over grayscale texture sheets"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Graphics"]
aliases: ["tellius_archive.html#/font-format"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/font-format.md"
---
# Font

*Five bitmap fonts: a glyph table over grayscale texture sheets*

Every piece of text the game draws, from dialogue to menu labels, comes from one of five bitmap fonts. A font file holds a small header, a table saying where each character sits, and one or more grayscale texture sheets holding the character images. The game has no other text source: a character missing from the font cannot be drawn.

## The five fonts

  Text refers to a font by number: the [message code](./message-format.md) `#F` switches between them mid-sentence, and menu code selects one directly. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>#</th><th>Name</th><th>File</th><th>Characters</th><th>What it looks like</th></tr></thead><tbody>
    <tr><td>0</td><td>system</td><td><code>Fonts/system.cms</code> (<a class="wl" href="../lz10/">LZ10</a>)</td><td>3,988</td><td>The general UI font: full Japanese character set plus ASCII</td></tr>
    <tr><td>1</td><td>fe_font</td><td><code>Fonts/fe_font.gcf</code></td><td>95</td><td>The invented Tellius alphabet: calligraphic letters mapped onto the ASCII codes, so ordinary text in this font renders in the in-world script</td></tr>
    <tr><td>2</td><td>talk</td><td><code>Fonts/talk.gcf</code></td><td>4,005</td><td>The dialogue font: same character set as system, slightly taller</td></tr>
    <tr><td>3</td><td>bigkana</td><td><code>Fonts/bigkana.gcf</code></td><td>95</td><td>Large Latin serif (the name dates from the Japanese release)</td></tr>
    <tr><td>4</td><td>alpha</td><td><code>Fonts/alpha.gcf</code></td><td>77</td><td>Large condensed sans-serif: letters, digits and a little punctuation</td></tr>
  </tbody></table>
</div>

  Fonts 1–4 are loaded at boot from copies bundled in `system.cmp`, which take priority over the loose files, so an edit has to reach both. The system font is loaded separately from the compressed `system.cms`. The disc also carries a loose `Fonts/system.gcf` that the game never loads. <span class="confidence confidence--confirmed">confirmed</span>

## File layout

<div class="table-wrap">
<table><thead><tr><th>Offset</th><th>Size</th><th>Field</th></tr></thead><tbody>
    <tr><td>0x00</td><td>4</td><td>Header size, always 0x20 (not read by the game)</td></tr>
    <tr><td>0x04</td><td>2</td><td>Highest character code in the table</td></tr>
    <tr><td>0x08</td><td>2</td><td>Ascent: pixels above the baseline</td></tr>
    <tr><td>0x0A</td><td>2</td><td>Descent: pixels below it (line height = ascent + descent)</td></tr>
    <tr><td>0x0C</td><td>2</td><td>Widest glyph, used as a fixed cell width for number columns <span class="badge strong">strong</span></td></tr>
    <tr><td>0x10</td><td>4</td><td>Zero on disc; filled with the line height when loaded</td></tr>
    <tr><td>0x14</td><td>4</td><td>Bytes per sheet</td></tr>
    <tr><td>0x18</td><td>2</td><td>Texture format, 0 = I4 (4-bit grayscale)</td></tr>
    <tr><td>0x1A</td><td>2</td><td>Number of sheets</td></tr>
    <tr><td>0x1E / 0x20</td><td>2 + 2</td><td>Sheet width and height</td></tr>
    <tr><td>0x22</td><td>2</td><td>Offset of the glyph table (0x30)</td></tr>
    <tr><td>0x24</td><td>4</td><td>Offset of the first sheet; the glyph table ends here</td></tr>
    <tr><td>0x28</td><td>4</td><td>Total size of all sheets</td></tr>
  </tbody></table>
</div>

  Unlisted header bytes are zero. After the table come the sheets back to back, and the file ends with the last one.

## Glyph records

  Each character is a 16-byte record: its code (2 bytes), sheet number, and the left and top pixel of its box on that sheet (2 bytes each); the box width and height (1 byte each); then three signed bytes: horizontal bearing, vertical bearing (how far the glyph top sits above the baseline), and advance (how far the pen moves afterwards). Three zero bytes pad the record. <span class="confidence confidence--confirmed">confirmed</span>

  Codes are single bytes for ASCII and two bytes for Japanese characters, using the Windows code page 932 variant of Shift-JIS; the large fonts include its extra symbol row (circled numbers ①–⑳, Roman numerals, unit abbreviations). Unassigned codes in the large fonts hold a one-pixel dot.

## How a character is found

  The records are sorted by code and the game binary-searches them. If the character is not in the font, it tries the white star ☆ (code 0x8199) instead, and if that is missing too, it uses the first record, a space in every vanilla font. So a character missing from the dialogue font shows up as ☆, while one missing from the three small fonts simply disappears. <span class="confidence confidence--confirmed">confirmed</span>

## Drawing a glyph

  To draw a character the game binds its sheet as a texture, draws the glyph box at *x* + horizontal bearing and *y* + ascent − vertical bearing, tints it with the current [#C colour](./message-format.md), and moves right by the advance. The gray level of each pixel is its coverage.

## Example

  In the dialogue font the letter `A` (code 0x41) advances 13 pixels and every digit advances 12, so numbers line up in columns. The same `A` written in font 1 is drawn as a Tellius letter instead.

## Which font is used where

  Screen text is queued as 2D drawing commands; the kind of text command decides the font. Menus use one kind, the dialogue box another, and a `#F` code inside the text can switch fonts partway through. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th>Font</th><th>Where it appears</th></tr></thead><tbody>
    <tr><td>system</td><td>Every menu, status, forecast, shop and list screen; tutorial windows; speaker names in the conversation log</td></tr>
    <tr><td>talk</td><td>Dialogue box lines and the lines of the conversation log</td></tr>
    <tr><td>fe_font</td><td>Lines spoken in the ancient language: the heron galdr, Leanne and Reyson's exchanges, and the endgame. The text switches in with <code>#F01</code> and back with <code>#F02</code></td></tr>
    <tr><td>bigkana</td><td>The title menu and the file menu: each label is prefixed with <code>#F03</code></td></tr>
    <tr><td>alpha</td><td>The names in the staff roll, drawn with <code>#F04</code></td></tr>
  </tbody></table>
</div>

  A font switch only lasts until the end of the current line. The dialogue box draws each line as a separate piece of text that starts in the talk font, which is why the game's own ancient-language lines repeat `#F01` at the start of every line. Debug overlays use a separate built-in 8×8 font that is not stored in these files.

  The message code `$O`, which always travels with these font switches, is not a font code: it picks the typing sound played as the text appears (see [Message Format](./message-format.md)).

## Replacing a font

  A font file is loaded into memory sized from the file itself, so a replacement may be larger than the original; nothing in the game reserves a fixed-size buffer for it. The cost is memory, and for fonts 1–4 a larger `system.cmp`, which is loaded whole at boot. <span class="confidence confidence--strong">strong</span>

  Glyph boxes can sit anywhere on the sheets, since the game reads only each record's sheet, position and size. What must hold: records sorted by code, a texture format and sheet size the header describes, and the original ascent and descent if text should stay on its lines. Only characters with a code page 932 code can appear in game text, so a letter such as `é` needs a spare code of its own before any font can show it.

!!! warning "Open"
    Whether chapter title cards, map names and battle damage numbers are font text or pre-drawn images is not yet established. The shadow and outline behind dialogue text are described in [Message Format](./message-format.md). <span class="confidence confidence--open">open</span>
