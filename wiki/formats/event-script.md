---
id: "event-script"
title: "Event Script"
description: "Compiled bytecode driving chapter setup, cutscene triggers, and win/lose conditions"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Chapter data","Editable","Scripting"]
aliases: ["tellius_archive.html#/event-script"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/event-script.md"
---
# Event Script

*Compiled bytecode driving chapter setup, cutscene triggers, and win/lose conditions*

The compiled bytecode driving a chapter — setup, cutscene triggers, win/lose conditions. Not compressed or archived: a direct binary file per chapter, plus `startup.cmb` (helpers every chapter calls) and `ending.cmb`. Each function inside a script carries a **trigger type** (start of turn, start of phase, a unit reaching a tile, ...) and parameters controlling exactly when it fires; a stack-machine bytecode body does the actual work once triggered. See [Events & Scripting](../systems/events-scripting.md) for how the engine runs it.

  For a step-by-step explanation of modules, event state, execution, timing and the boundaries of script-driven changes, read [Events & Scripting](../systems/events-scripting.md). Its scope is the researched US Path of Radiance executable. Every function a script can call is described on [Script Functions](../systems/script-functions.md).

## How a script function becomes an event

  The engine evaluates a function's trigger and parameters; when eligible, it starts that function's stack-machine bytecode. Instructions manipulate values and branch locally, while external calls request native game operations. The format therefore stores both the condition and the response, but mutable chapter state lives outside the file.

## File layout

<div class="table-wrap">
<table class="tight"><thead><tr><th>Offset</th><th>Content</th></tr></thead><tbody>
    <tr><td class="num">0x00</td><td>Header (0x24 bytes): <code>"cmb\0"</code>, the file name, a constant <code>0x20041125</code> at <code>+0x18</code>, a word the loader overwrites at <code>+0x20</code>, and the script's global-slot count at <code>+0x22</code></td></tr>
    <tr><td class="num">0x24</td><td>Offset of the string pool (always <code>0x2C</code>)</td></tr>
    <tr><td class="num">0x28</td><td>Offset of the function table</td></tr>
    <tr><td class="num">0x2C</td><td>String pool: NUL-separated Shift-JIS strings, padded to 4 bytes</td></tr>
    <tr><td>table</td><td>One 32-bit address per function, ended by a 0 word</td></tr>
    <tr><td>functions</td><td>Per function, 4-byte aligned: a 20-byte record, its trigger parameters, an optional name, then the code</td></tr>
  </tbody></table>
</div>

  Header, table and record words are little-endian; instruction operands are big-endian. <span class="confidence confidence--confirmed">confirmed</span>

## Function record

<div class="table-wrap">
<table class="tight"><thead><tr><th>Offset</th><th>Size</th><th>Field</th></tr></thead><tbody>
    <tr><td class="num">+0x00</td><td>4</td><td>Address of the function's name (0 = anonymous)</td></tr>
    <tr><td class="num">+0x04</td><td>4</td><td>Address of the code</td></tr>
    <tr><td class="num">+0x08</td><td>4</td><td>0 on disc; the loader stores the owning script here</td></tr>
    <tr><td class="num">+0x0C</td><td>1</td><td>Trigger type</td></tr>
    <tr><td class="num">+0x0D</td><td>1</td><td>Argument count</td></tr>
    <tr><td class="num">+0x0E</td><td>1</td><td>Trigger-parameter count</td></tr>
    <tr><td class="num">+0x0F</td><td>1</td><td>Unused</td></tr>
    <tr><td class="num">+0x10</td><td>2</td><td>Function index (its position in the table)</td></tr>
    <tr><td class="num">+0x12</td><td>2</td><td>Frame size: arguments plus local variables, in 4-byte slots</td></tr>
    <tr><td class="num">+0x14</td><td>2 &amp;times; n</td><td>Trigger parameters</td></tr>
  </tbody></table>
</div>

  The name, when present, follows the parameters (NUL-terminated, padded to 4); the code follows, padded with 1 to 4 bytes to the next 4-byte boundary. Padding and the unused byte are never read, and a few chapters hold leftover non-zero values there. A named function is registered globally when its script loads, so any loaded script can call it by that name.

## Trigger types

  Every trigger value across the 43 chapter scripts falls inside 0&ndash;15. Trigger parameters may be raw numbers, character identifiers, flag names, or debug labels resolved through the script's string pool (a label parameter of 0 means "none").

<div class="table-wrap">
<table class="tight"><thead><tr><th>Type</th><th>Trigger</th><th>Notable params</th></tr></thead><tbody>
    <tr><td class="num">0</td><td>None — runs only when called</td><td>—</td></tr>
    <tr><td class="num">1 / 2</td><td>Map goal achieved / failed</td><td>The watched flag (<code>gf_complete</code> / <code>gf_gameover</code>)</td></tr>
    <tr><td class="num">3 / 6</td><td>Before / after a phase starts</td><td>First and last turn, phase (0=player, 1=enemy, 3=partner) — raw numbers</td></tr>
    <tr><td class="num">4</td><td>A unit moves into a zone</td><td>Zone bounds, which side triggers, a resolved debug event-name</td></tr>
    <tr><td class="num">5</td><td>A unit acts at a location</td><td>Location, action (9 visit, 11 door, 12 chest, 13 seize, 14 escape, 37 destroy house, 41 arrive, 44 other), and a resolved debug name; it does not identify the acting character</td></tr>
    <tr><td class="num">7</td><td>After every action</td><td>—</td></tr>
    <tr><td class="num">8 / 9</td><td>Two units talk / fight starts</td><td>Two resolved <code>PID_</code> character references (an empty second one on a fight matches anyone), a direction flag (0: the first character must be the one talking or attacking, the second its target; 1: either way round), and a one-time flag name — the event is skipped while that flag is set</td></tr>
    <tr><td class="num">10 / 11</td><td>A unit's death (back on the map / in battle)</td><td>A <code>PID_</code> character reference</td></tr>
    <tr><td class="num">12</td><td>Scenario complete</td><td>A debug name</td></tr>
    <tr><td class="num">13</td><td>A support conversation</td><td>Two <code>PID_</code> references, support level (1 = C, 2 = B, 3 = A)</td></tr>
    <tr><td class="num">14</td><td>A base conversation</td><td>An “info flag” name, a character reference in the distinct <code>MPID_</code> ID family, a star count</td></tr>
    <tr><td class="num">15</td><td>Selecting a unit</td><td>—</td></tr>
  </tbody></table>
</div>

  A debug listing left in the executable, headed “C-minor registered function list” — **C-minor** being the developers' name for this script language — gives each type its original name: 1 Complete, 2 Gameover, 3 Turn, 4 Area, 5 Poke, 6 TurnAfter, 7 Taiki (“wait”), 8 Talk, 9 BossTalk, 10 Die, 11 LocalDie, 12 Achieve, 13 Yell, 14 BaseTalk, 15 Pickup, and `local` for type 0. <span class="confidence confidence--confirmed">confirmed</span>

## Instructions

  An instruction is one opcode byte followed by 0 to 4 operand bytes. Every operand is **signed**: a one-byte literal covers −128 to 127, and a one-byte string offset only reaches the first 128 bytes of the pool. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table class="tight"><thead><tr><th>Opcodes</th><th>Group</th><th>Effect</th></tr></thead><tbody>
    <tr><td class="num">01&amp;ndash;0C</td><td>Local variables</td><td>Push a variable, an array element (index popped), or their address — in 1- and 2-byte slot forms. Arguments are slots 0, 1, …; locals follow.</td></tr>
    <tr><td class="num">0D&amp;ndash;18</td><td>Global variables</td><td>The same six modes on the engine-wide script global table</td></tr>
    <tr><td class="num">19&amp;ndash;1B</td><td>Literals</td><td>Push a 1-, 2- or 4-byte number</td></tr>
    <tr><td class="num">1C&amp;ndash;1E</td><td>Strings</td><td>Push a string, by offset into the pool</td></tr>
    <tr><td class="num">1F, 20, 21</td><td>Memory</td><td><code>deref</code> (read through an address, keeping it), <code>pop</code>, <code>store</code> (write, then push the value again)</td></tr>
    <tr><td class="num">22&amp;ndash;36</td><td>Arithmetic &amp; comparison</td><td>add, sub, mul, div, mod, neg, bitwise not/or/and/xor, shifts, logical not, the six comparisons, and two string comparisons</td></tr>
    <tr><td class="num">37, 38</td><td>Calls</td><td><code>localCall</code> (a function of this script, by index) and <code>externCall</code> (any registered name, with an argument count)</td></tr>
    <tr><td class="num">39</td><td>return</td><td>Pops the return value, drops the frame, pushes the value for the caller</td></tr>
    <tr><td class="num">3A&amp;ndash;3E</td><td>Branches</td><td>Jump; jump if non-zero; jump if zero; and two "keep" forms that leave 1 / 0 on the stack when they jump — the building blocks of <code>||</code> and <code>&amp;&amp;</code></td></tr>
    <tr><td class="num">3F</td><td>yield</td><td>Pause until the engine resumes the script</td></tr>
    <tr><td class="num">40, 41</td><td>Debug</td><td>A 4-byte no-op and <code>printf</code>, whose native does nothing</td></tr>
    <tr><td class="num">42&amp;ndash;47</td><td>—</td><td>Only used by Radiant Dawn: inc, dec, dup, ret0, ret1, assign (see <a class="wl" href="../rd-event-scripts/">Event Scripts (Radiant Dawn)</a>)</td></tr>
  </tbody></table>
</div>

  A branch's target is its own offset + 1 + the operand. Every call leaves exactly one value on the stack; a call made as a statement is followed by `pop`. <span class="confidence confidence--confirmed">confirmed</span>

## How the original compiler shaped the code

  The scripts were compiled from a C-like language, and the output is completely regular:

<div class="table-wrap">
<table class="tight"><thead><tr><th>Source</th><th>Bytecode</th></tr></thead><tbody>
    <tr><td><code>if (c) A else B</code></td><td><code>c · branch-if-zero Else · A · jump End · Else: B · End:</code></td></tr>
    <tr><td><code>while (c) A</code></td><td><code>Top: c · branch-if-zero End · A · jump Top · End:</code></td></tr>
    <tr><td><code>do A while (c);</code></td><td><code>Top: A · c · branch-if-non-zero Top</code></td></tr>
    <tr><td><code>x = e;</code></td><td><code>push-address x · e · store · pop</code></td></tr>
    <tr><td><code>int x = e;</code></td><td><code>push-address x · e · store</code> (no pop)</td></tr>
    <tr><td><code>f(a, b);</code></td><td><code>a · b · call f · pop</code></td></tr>
    <tr><td>end of a function</td><td><code>push 0 · return</code>, always</td></tr>
  </tbody></table>
</div>

  Numbers always use the smallest operand that fits, and a negative number is written as its positive value followed by `neg`.

!!! info "Growing the string pool"
    A string operand is *pool-relative*, not an absolute file address. Appending a string at the pool's end does not change existing offsets, but every structure physically stored after the pool moves and must receive an updated address. <span class="confidence confidence--confirmed">confirmed</span>
