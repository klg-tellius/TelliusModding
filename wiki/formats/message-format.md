---
id: "message-format"
title: "Message Format"
description: "Chapter dialogue text, with an inline scripting language for portraits and pacing"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Chapter data","Editable","Text"]
aliases: ["tellius_archive.html#/message-format"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/message-format.md"
---
# Message Format

*Chapter dialogue text, with an inline scripting language for portraits and pacing*

Every line of dialogue and narration lives in a message file, one per chapter plus shared files such as `common.m`. Each message has an ID (for example `MS_02_OP_01`) and a text. The text is written in a small inline language: ordinary sentences interrupted by `$`-prefixed commands that set up the scene, move portraits, and control pacing. `$K` waits for a button press, `$w3` pauses briefly, and `$FCL_IKE|` brings up Ike's large portrait.

## File layout

A message file is a relocatable resource, the same container family used by many other data files. After a 32-byte header comes the text blob, then a table of `(text offset, ID offset)` pairs, then the ID strings. The header's export count is the number of messages, and the pair table is the export table.

## How the game finds a message

Loading a message file registers every message ID in the engine's single global name table. The same table holds sound cues and script scene names. An [event script](./event-script.md) plays a message by naming it, for example `TalkEvent("MS_02_OP_01")`. The engine looks the ID up and opens the message window with its text. <span class="confidence confidence--confirmed">confirmed</span>

  The table stores two numbers per name: a bucket (each byte ×37, modulo 509) and a check value (each byte ×31), computed over signed bytes. A lookup returns the first entry in the bucket whose check value matches; the name itself is never compared. Two consequences follow:

- The order of messages inside a file does not matter, although every retail file is sorted alphabetically by ID.
- Two different IDs with the same bucket and check value would shadow each other, and the one registered first wins. No two retail message IDs collide.

  Text beginning with `@` is a template: `@{0}`&hellip;`@{9}` are replaced by runtime values before display.

## How a message becomes a scene

A message is a little scene script. It picks a layout (the window and portrait-seat arrangement) and optionally a background, loads portraits into seats, then shows lines of text in textboxes. The message controls how the exchange is presented. The event script decides when it plays, and a message can hand control back to the script partway through and resume later.

  There are two styles. **Box style** (layout 上下会話, “up-down conversation”) pairs each of four textboxes with one portrait seat: `$c0ZAWANAR|` opens box 0 with that face, and `$s0` selects it for text. **Seat style** (背景会話, “background conversation”, and the world-map layout GMAP会話) uses up to nine seats: `$F1$FCL_TIAMAT|` loads Titania into seat 1, and `$F1$P` starts a line spoken from that seat.

## Command reference

<div class="table-wrap">
<table class="tight"><thead><tr><th>Code</th><th>Meaning</th></tr></thead><tbody>
    <tr><td><code>$R&lt;layout&gt;|</code></td><td>Layout, e.g. 上下会話, 背景会話, GMAP会話, 背景なし会話; clears every textbox</td></tr>
    <tr><td><code>$B&lt;background&gt;|</code></td><td>Background image, e.g. 村-崖 (“village-cliff”), 平原-昼 (“plains-day”) — see <a class="wl" href="../tpl-texture/">backgrounds</a></td></tr>
    <tr><td><code>$=dddd</code>, <code>$&lt;</code></td><td>Screen-transition duration in ms (9999 = default 267 ms); start the transition</td></tr>
    <tr><td><code>$F&lt;0-8&gt;</code></td><td>Select portrait seat N</td></tr>
    <tr><td><code>$FC&lt;name&gt;|</code>, <code>$FD</code></td><td>Load a portrait into the current seat (<code>L_</code> names are the large ones; see <a class="wl" href="../face-data/">Face Data</a>); remove it</td></tr>
    <tr><td><code>$Fc</code> <code>$Fh</code> <code>$Fo</code> <code>$Fd</code></td><td>Eyes closed / half-open / held open / normal blinking</td></tr>
    <tr><td><code>$Ff</code>, <code>$Fs</code></td><td>Quick / normal blinking</td></tr>
    <tr><td><code>$FS</code>, <code>$FA</code></td><td>First / second mouth texture set (not show/hide)</td></tr>
    <tr><td><code>$c&lt;0-3&gt;&lt;name&gt;|</code></td><td>Open textbox N and load that portrait into seat N</td></tr>
    <tr><td><code>$s&lt;0-3&gt;</code>, <code>$d&lt;0-3&gt;</code></td><td>Select (and clear) textbox N; dismiss box N and its portrait</td></tr>
    <tr><td><code>$W-</code> <code>$W+</code> <code>$WD</code></td><td>Hide all windows / show them again / hide the current one</td></tr>
    <tr><td><code>$ND</code></td><td>Toggle the speaker nameplate</td></tr>
    <tr><td><code>$P</code></td><td>Clear the current box and start a new line</td></tr>
    <tr><td><code>$K</code></td><td>Wait for a button press; the text stays on screen — the most common code in the game</td></tr>
    <tr><td><code>$N</code></td><td>Start a new text line</td></tr>
    <tr><td><code>$w&lt;n&gt;</code></td><td>Pause 2<sup>n</sup> frames</td></tr>
    <tr><td><code>$MC</code>&amp;hellip;<code>$MD</code></td><td>Stop and restart mouth movement — wraps “...” and “--” so the speaker's mouth stays still</td></tr>
    <tr><td><code>$H</code></td><td>Hand control back to the event script; the message resumes later</td></tr>
    <tr><td><code>$UB</code>, <code>$Ub</code></td><td>Let the event script waiting on the message run again (the two behave the same). Always followed by <code>$H</code>: at the end of a message it keeps the windows and portraits for the next message; mid-message it lets the script move the camera or units before the text resumes</td></tr>
    <tr><td><code>$SD</code>, <code>$SE</code></td><td>Skip disable / enable. B normally skips the whole conversation; after <code>$SD</code> it advances the text like A instead. Used around choices so a decision cannot be skipped past (<code>$DC</code> is an unused alias of <code>$SD</code>)</td></tr>
    <tr><td><code>$Y</code></td><td>Move on without waiting for a button press, e.g. when a speaker is cut off</td></tr>
    <tr><td><code>$G</code></td><td>Record the following text in the text log as narration, with no speaker name (world-map narration)</td></tr>
    <tr><td><code>$O&lt;n&gt;</code></td><td>Typing sound played as text appears: 1 dialogue, 2 ancient language, 3 world-map narration, 4 tutorial, 0 silent</td></tr>
    <tr><td><code>#Cxx</code>, <code>#c</code>, <code>#Fxx</code></td><td>Text colour from the palette / previous colour; <a class="wl" href="../font-format/">font</a> (system, fe_font, talk, bigkana, alpha) for the rest of the line</td></tr>
    <tr><td><code>#Pnnn</code></td><td>Inline icon: cell <code>nnn</code> (hex) of <code>window/icon.tpl</code>, 24&amp;times;24, 32 per row, centred on the line and 24 px wide. <code>#P027</code> is the A button, <code>#P028</code> the B button, <code>#P00F</code>&amp;ndash;<code>#P016</code> the weapon types</td></tr>
  </tbody></table>
</div>

  The background name 支援背景 (“support background”) stands for the current chapter's conversation background, set in the chapter data. <span class="confidence confidence--confirmed">confirmed</span>

## Timing

Text appears one character per tick. A tick lasts 10 frames at the Slow message speed, 4 at Normal and 1 at Fast; at Max the whole page appears at once. Opening, clearing or closing a box, waiting for a button, `$Y` and `$w` each end the current tick, so the next character waits for the following one. A press of A shows the rest of the page at once. Boxes and portraits fade in and out over 8 frames, and the portraits of characters who are not speaking dim over 4 frames. Screen fades (`$<`, `$>`) last the `$=` duration and run while the text continues. Z at a wait opens the text log, which keeps the last 256 lines. <span class="confidence confidence--confirmed">confirmed</span>

## Text effects

Every dialogue window draws its text with a **drop shadow**, the glyphs again in black at half opacity 2 pixels down and right, and a 1-pixel black **outline**, the glyphs redrawn in black in eight directions around their position. The choice dialog uses neither. Inside a text, `#E`/`#e` switch the shadow on or off and `#O`/`#o` the outline; `#Ixx` slants the following letters so that the top of the line leans `xx`/16 pixels to the right (`#i` ends it); `#Rxx`, `#Gxx`, `#Bxx` and `#Axx` set the red, green, blue or opacity of the text colour. `#D` returns to the default colour, size and slant and turns the shadow and outline off. The game's own texts never use these codes. <span class="confidence confidence--confirmed">confirmed</span>

## Text scale

`#Sxx` scales text in both directions, `#Xxx` only horizontally and `#Yxx` only vertically, by `xx`/64: `#S40` is normal size, `#S80` double. `#s`, `#x` and `#y` reset them, as do `#D` and the start of every line. Scaled text grows right and down from the start of its line, the line spacing does not change, and icons keep their size; window widths take the horizontal scale into account. The game squeezes three long defeat conditions of the objective window with `#X3A` (91 %, &ldquo;Exceed 15 turns&rdquo;) and enlarges the tutorial's &ldquo;- Demonstration -&rdquo; title with `#S50` (125 %). <span class="confidence confidence--confirmed">confirmed</span>
