---
id: "rd-event-scripts"
title: "Event Scripts (Radiant Dawn)"
description: "The chapter scripts: the same container and virtual machine as Path of Radiance, six new instructions, new triggers and a larger flag table"
games: ["radiant-dawn"]
section: "formats"
article_type: "format-reference"
tags: ["Structure","Radiant Dawn"]
aliases: ["tellius_archive.html#/rd-event-scripts"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/rd-event-scripts.md"
---
# Event Scripts (Radiant Dawn)

*The chapter scripts: the same container and virtual machine as Path of Radiance, six new instructions, new triggers and a larger flag table*

Every chapter of Radiant Dawn has a script, `Scripts/C<part><chapter>.cmb` (`C0101` is Part 1's Prologue, `C0407a`&ndash;`C0407e` the five maps of the last chapter, `CFINAL` the endgame), plus the shared `startup.cmb`, `ending.cmb`, the test map `C0000` and four tutorial scripts `T01`&ndash;`T04` that the game loads on demand. The file layout and the virtual machine are the ones of [Event Script](./event-script.md); this page lists what is different. <span class="confidence confidence--confirmed">engine + every script</span>

## What is the same

- The 0x2C-byte header, string pool, function table and 20-byte function records; named functions are registered by name when their script loads, and any loaded script can call them.
- The stack machine: instructions `0x00`&ndash;`0x41` read the same operands and do the same thing, with one exception below. Operands are big-endian and signed; a branch's target is its own position + 1 + the operand.
- Calls to natives and to script functions of other files go through the engine's global name table; a name nobody registered returns 0.

  The word at header offset `0x18` is the script compiler's build date, which the game never reads: `0x20041125` in every Path of Radiance script, `0x20061024` in every Radiant Dawn one.

## The instructions that changed

<div class="table-wrap">
<table class="tight"><thead><tr><th>Opcode</th><th>Radiant Dawn</th></tr></thead><tbody>
    <tr><td><code>37</code> localCall</td><td>The function index takes one byte, or two when the first byte's high bit is set: index = (first &amp; 0x7F) &amp;times; 256 + second. <code>startup.cmb</code> has 589 functions, so its calls need the long form. (Path of Radiance: one byte.)</td></tr>
    <tr><td><code>41</code> printf</td><td>Drops its arguments; nothing is printed.</td></tr>
    <tr><td><code>42</code> inc, <code>43</code> dec</td><td>Pop an address, add or subtract 1 at it, push nothing</td></tr>
    <tr><td><code>44</code> dup</td><td>Push the top value again</td></tr>
    <tr><td><code>45</code> ret0, <code>46</code> ret1</td><td>Return 0 / return 1</td></tr>
    <tr><td><code>47</code> assign</td><td>Pop a value and an address, store the value, push nothing</td></tr>
  </tbody></table>
</div>

  Path of Radiance's interpreter has no case for `42`&ndash;`47`. <span class="confidence confidence--confirmed">engine</span>

## How Radiant Dawn's compiler writes common statements

<div class="table-wrap">
<table class="tight"><thead><tr><th>Statement</th><th>Bytecode</th></tr></thead><tbody>
    <tr><td><code>x = e;</code></td><td><code>pushaddr x</code>, e, <code>assign</code> (Path of Radiance: <code>store</code>, <code>pop</code>)</td></tr>
    <tr><td><code>x += e;</code></td><td><code>pushaddr x</code>, <code>deref</code>, e, <code>add</code>, <code>assign</code></td></tr>
    <tr><td><code>return 0;</code> / <code>return 1;</code></td><td><code>ret0</code> / <code>ret1</code>; any other value: e, <code>return</code></td></tr>
    <tr><td>end of a function</td><td><code>ret0</code>, left out after a final <code>return</code>; functions run by a trigger keep Path of Radiance's <code>push 0</code>, <code>return</code></td></tr>
    <tr><td><code>x++;</code></td><td><code>pushvar x</code>, <code>pushaddr x</code>, <code>inc</code>, <code>pop</code></td></tr>
    <tr><td><code>++x</code></td><td><code>pushaddr x</code>, <code>inc</code>, <code>pushvar x</code></td></tr>
    <tr><td><code>switch (v) { case a: case b: &amp;hellip; }</code></td><td>v; for each case, <code>dup</code>, its value, <code>eq</code>, <code>branchnz</code> to the case's code for each of its values, then <code>branch</code> to the next case's tests; the code of each case; the default's code; <code>pop</code> at the end. <code>break</code> jumps to that <code>pop</code>.</td></tr>
  </tbody></table>
</div>

## Example

  `startup.cmb`'s `UnitIsStay(unit)` returns 1 for units of forces 0 and 5. Its bytecode reads: `pushvar 0`, `externCall UnitGetForce`, `dup`, `push 0`, `eq`, `branchnz` &rarr;A, `dup`, `push 5`, `eq`, `branchnz` &rarr;A, `branch` &rarr;B; A: `ret1`; B: `branch` &rarr;C; C: `pop`, `ret0`: a switch with one case for 0 and 5 that returns 1, an empty default, and `return 0` after it.

## Triggers

  A function's type (record byte `0x0C`) says when the game runs it, and its parameters (16-bit values, strings given as pool offsets) narrow that down. Types 0&ndash;12 and 15 mean what they mean in [Path of Radiance](./event-script.md). A *condition* below is a string that names either a registered flag, in which case the event is skipped once the flag is set, or a function of the loaded scripts that the game calls and that must return non-zero. <span class="confidence confidence--confirmed">engine</span>

<div class="table-wrap">
<table class="tight"><thead><tr><th>Type</th><th>Runs when</th><th>Parameters</th></tr></thead><tbody>
    <tr><td>3, 6</td><td>Before / after a phase starts</td><td>first turn, last turn (0 = every turn), phase (0 player, 1 enemy, 2 other; any if negative)</td></tr>
    <tr><td>4</td><td>A unit moves into a zone</td><td>x1, y1, x2, y2 (a corner of 0 or less counts from the right or bottom edge), army (any if negative), one-time flag</td></tr>
    <tr><td>5</td><td>A unit acts on a tile</td><td>x, y, action (below), one-time flag</td></tr>
    <tr><td>8</td><td>Two units talk</td><td>character 1, character 2, either-way flag, condition</td></tr>
    <tr><td>9</td><td>A fight starts</td><td>character 1, character 2 (empty = anyone), either-way flag, condition</td></tr>
    <tr><td>13</td><td>A support conversation</td><td>character 1, character 2, level. No Radiant Dawn script uses it; without a match, the game runs the support by name as a type-16 function</td></tr>
    <tr><td>14</td><td>A base conversation</td><td>event name, flag. The menu looks up <code>CONV_INFO_DATA_&lt;chapter&gt;_&lt;event name&gt;</code> in <a class="wl" href="../rd-conversation-data/">FE10Conversation.cms</a> (Path of Radiance had three parameters: flag, character, stars)</td></tr>
    <tr><td>16</td><td>Called by name</td><td>event name</td></tr>
    <tr><td>17</td><td>The Rescue command</td><td>rescuer, rescued unit (empty = anyone), either-way flag, one-time flag</td></tr>
    <tr><td>18</td><td>The Give or Take command</td><td>carrier, other unit, carried unit (each empty = anyone), either-way flag, one-time flag</td></tr>
    <tr><td>19</td><td>A moving unit enters a tile; its move stops there</td><td>character, x, y (65535 = any), condition (the function gets x and y)</td></tr>
    <tr><td>20</td><td>A character's epilogue entry, in the ending</td><td>character (empty = anyone), condition</td></tr>
  </tbody></table>
</div>

  The tile actions of type 5: 9 visit, 11 door, 12 chest, 13 seize, 14 escape, 38 destroy (a wall or a house), 42 arrive, 55 light a torch, 58 open, 59 put a torch out. Type 5 events also drive what the map menu offers on a tile, and the game reads a chest's item from its event's call to `MindGetItem`. Action 45 (three tiles of Part 1 Chapter 7) is not identified. <span class="confidence confidence--confirmed">engine + scripts</span>

## Flags

  The flag table works as in [Event Flags](../systems/event-flags.md) with 128 slots instead of 96. Eight engine flags come first: `gf_canceled`, `gf_gameover`, `gf_complete` and `gf_reserved2`&ndash;`6`. `startup.cmb`'s `RegistGlobalFlags` adds 19 campaign flags: who died (Pelleas), Ike's restored memory in 4-7, the seven triangle-attack members, three battle conversations, the Black Knight's appearances in 1-11 and 3-8, the brothers' conversation in 3-3, Soren's conversation in 4-7, Yune's protection, and one reserved slot never used. A chapter registers its own flags from the top slot down. <span class="confidence confidence--confirmed">engine + scripts</span>

## Native functions

  656 functions are built into the executable, registered by nine parts of the game (map scenes, units and the battle map, battle-map scenes, chapter results, event arrows, scripted 3D scenes, the ending, a conversation signal and a general group). 291 are new compared with Path of Radiance, 24 take a different number of arguments, and 43 are gone, several of them now written in script in `startup.cmb` (`WaitM`, `WaitF`, `InstantDispos`), which exports 511 functions in all. Vanilla scripts still pass an argument to `StaffRoll`, `WarRecord` and `VOICEAllStop`, which take none; the extra value is simply left on the stack until the function returns. Each one is described on [Script Functions (Radiant Dawn)](../systems/rd-script-functions.md). <span class="confidence confidence--confirmed">engine</span>

  Open: where a Radiant Dawn save keeps the flag bits, and whether the chapter-start reset clears the chapter flags from slot 127 down as Path of Radiance's does from 95. <span class="confidence confidence--open">open</span>
