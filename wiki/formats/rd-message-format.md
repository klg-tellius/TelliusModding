---
id: "rd-message-format"
title: "Message Format (Radiant Dawn)"
description: "The byte-code that replaced Path of Radiance's $ commands"
games: ["radiant-dawn"]
section: "formats"
article_type: "format-reference"
tags: ["Text","Radiant Dawn"]
aliases: ["tellius_archive.html#/rd-message-format"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/rd-message-format.md"
---
# Message Format (Radiant Dawn)

*The byte-code that replaced Path of Radiance's $ commands*

Radiant Dawn keeps Path of Radiance's message files and its scene language (layouts, a cast of portraits, boxes, waits, pauses) but writes the commands differently. Instead of printable `$` codes, every command starts with a control byte below `0x20`, and that byte says how long the command is. Ordinary text and the `#` and `@` markup (fonts, colours, values, button icons) are unchanged. <span class="confidence confidence--confirmed">engine + every message</span>

## The command bytes

<div class="table-wrap">
<table class="tight"><thead><tr><th>Bytes</th><th>Command</th></tr></thead><tbody>
    <tr><td><code>00</code></td><td>End of the message</td></tr>
    <tr><td><code>01</code> X</td><td>One-letter command</td></tr>
    <tr><td><code>02</code> XY</td><td>Two-letter command</td></tr>
    <tr><td><code>03</code> XYZ</td><td>Three-letter command (only <code>DFC</code>)</td></tr>
    <tr><td><code>04</code> X&amp;hellip;<code>|</code></td><td>A letter and an argument up to a <code>|</code></td></tr>
    <tr><td><code>05</code> XY<code>|</code>&amp;hellip;<code>||</code></td><td>A two-letter list: fields each ending with <code>|</code>, closed by an empty field</td></tr>
    <tr><td><code>07</code> a p</td><td>Actor <em>a</em> speaks at position <em>p</em>: the box and nameplate switch to it, and the box is cleared when the speaker changes</td></tr>
    <tr><td><code>08</code> p f, <code>0E</code> p f</td><td>Bring the current actor in at position <em>p</em>, facing <em>f</em> (<code>D</code> the seat's default, <code>L</code>, <code>R</code>). <code>08</code> ends the current text tick, <code>0E</code> carries on</td></tr>
    <tr><td><code>09</code>, <code>0F</code></td><td>Remove the current actor's portrait and box (<code>09</code> ends the tick)</td></tr>
    <tr><td><code>0A</code></td><td>New line</td></tr>
    <tr><td><code>0B</code> xx</td><td>Two bytes the game skips</td></tr>
    <tr><td><code>0C</code> a p</td><td>Make actor <em>a</em> at position <em>p</em> current, without changing the speaker</td></tr>
    <tr><td><code>0D</code> p f</td><td>The current actor takes over the portrait already standing at position <em>p</em></td></tr>
    <tr><td><code>10</code></td><td>Scroll the box to a new page</td></tr>
    <tr><td><code>11</code></td><td>Wait for A (or for the automatic delay set by <code>04 s</code>)</td></tr>
    <tr><td><code>12</code></td><td>End the current text tick without waiting</td></tr>
  </tbody></table>
</div>

  Actor and position digits are hexadecimal (`0`&ndash;`9`, `A`&ndash;`F`). An argument is read Shift-JIS aware, so the second byte of a two-byte character is never taken for the closing `|`. Any other byte below `0x20`, and a letter the game does not know, is skipped and the text continues. <span class="confidence confidence--confirmed">engine</span>

## Letters

<div class="table-wrap">
<table class="tight"><thead><tr><th>Command</th><th>Effect</th></tr></thead><tbody>
    <tr><td><code>01 H</code></td><td>Suspend the message until the event script resumes it (Path of Radiance <code>$H</code>)</td></tr>
    <tr><td><code>01 @</code>, <code>01 *</code></td><td>Release the event script waiting on the message (<code>$UB</code> / <code>$Ub</code>)</td></tr>
    <tr><td><code>01 a</code>, <code>01 s</code></td><td>Second / first mouth set of the current actor (<code>$FA</code> / <code>$FS</code>)</td></tr>
    <tr><td><code>01 P</code>, <code>01 G</code></td><td>Clear the box; dissolve its text in a random pattern <span class="badge plausible">plausible</span></td></tr>
    <tr><td><code>02 w</code>n</td><td>Pause 2<sup>n</sup> ticks</td></tr>
    <tr><td><code>02 mc</code>, <code>md</code>, <code>mo</code></td><td>Mouth still, moving again, held open (vanilla wraps "..." in <code>mc</code>&amp;hellip;<code>md</code>)</td></tr>
    <tr><td><code>02 ec</code>, <code>eh</code>, <code>eo</code></td><td>Eyes closed, half-open, normal</td></tr>
    <tr><td><code>02 sd</code>, <code>se</code>, <code>03 DFC</code></td><td>Disable / enable skipping the conversation with B</td></tr>
    <tr><td><code>02 nc</code></td><td>Toggle the nameplate</td></tr>
    <tr><td><code>02 O</code>n</td><td>Typing sound n (0 silent)</td></tr>
    <tr><td><code>02 F</code>n, <code>04 FT</code>ms<code>|</code></td><td>Screen transition n over a duration in milliseconds; scenes end with <code>F1</code> and open with <code>F2</code> <span class="badge plausible">plausible</span></td></tr>
    <tr><td><code>02 f+</code>, <code>f-</code></td><td>Fade the layout's window frame in / out</td></tr>
    <tr><td><code>04 R</code>, <code>04 B</code>, <code>04 b</code></td><td>Layout; background with the transition; background swapped at once</td></tr>
    <tr><td><code>04 V</code>n name<code>|</code>, <code>02 VW</code>, <code>02 v</code>n</td><td>Play a voice line on channel n; wait for it to end; stop channel n</td></tr>
    <tr><td><code>04 S</code>name<code>|</code></td><td>Play a sound effect</td></tr>
    <tr><td><code>04 W</code>ms<code>|</code>, <code>04 s</code>ms<code>|</code></td><td>Pause for milliseconds; make later waits continue by themselves after that long (voiced scenes)</td></tr>
    <tr><td><code>05 FL</code></td><td>The cast: up to 16 portrait names, numbered from 0 for the actor digits above. Ike, Micaiah, Sothe, Luchino, Meg and the player's avatar are replaced by their current look</td></tr>
  </tbody></table>
</div>

## Example

  A one-line battle quote of the first chapter is, byte by byte: `05 FL|PUGO||` (the cast is Pugo), `04 R上下会話|` (two-box layout), `07 0 4` (actor 0 speaks at position 4), `08 4 D` (bring him in at position 4), the text, then `11` (wait for A). A scene with a backdrop instead names large portraits (`L_EDDIE`) and the 背景会話 layout, places each actor with `0C` and `0E`/`08`, and sets the background with `04 B`.

## Layouts and speech balloons

  Layouts are resources of `window/RectDesc_en.bin` (the shop greeting's in `RectBase_en.bin`), the same container as [Rect.bin](./rect-format.md) with a 48-byte text-box layer: window and page-cursor resources, text colour, text and cursor positions, width, line height, line count, typing speed and the position it belongs to. In the two-box family (上下会話, 背景上下会話, the tutorial layouts) each position has its own box, a speech balloon the game places when the actor comes in: the widest line plus 224 pixels (128 less when the actor has no portrait), rounded up to 48-pixel tiles and kept between 336 and 576. Each of the eight positions has a fixed corner (position 0 top left, 1 bottom right&hellip;), and the portrait stands at the seat point of the layout, inside the balloon. The background family (背景会話 and its variants) has one shared box and nine portrait seats. <span class="confidence confidence--confirmed">engine</span>

<div class="table-wrap">
<table class="tight"><thead><tr><th>Layout</th><th>Messages (US English)</th></tr></thead><tbody>
    <tr><td>上下会話, two boxes</td><td class="num">4,913</td></tr>
    <tr><td>背景会話, scene over a background</td><td class="num">691</td></tr>
    <tr><td>TUT会話, tutorial</td><td class="num">390</td></tr>
    <tr><td>背景上下会話, two boxes over a background</td><td class="num">125</td></tr>
    <tr><td>紹介会話, introductions; GMAP会話, world map; TUT小会話; 背景なし会話; 字幕会話, voiced subtitles; ダイアログ会話; BASE_SHOP_MESS; 背景のみ会話; のみ会話</td><td class="num">69 to 10</td></tr>
  </tbody></table>
</div>

  Open: the meaning of the flag letters `I`, `J`, `S`, `c`, `g`, `BO`, `KH`, `PL`/`PH`, `WO`/`WX`, the numbers of the `rc` and `FX` lists, and how the window art is cut into tiles. <span class="confidence confidence--open">open</span>
