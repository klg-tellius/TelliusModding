---
id: "main-dol"
title: "main.dol"
description: "The native PowerPC executable that turns file data into game behavior"
games: ["path-of-radiance"]
section: "formats"
article_type: "format-reference"
tags: ["Executable","Structure"]
aliases: ["tellius_archive.html#/main-dol"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "formats"
source_path: "formats/main-dol.md"
---
# main.dol

*The native PowerPC executable that turns file data into game behavior*

`main.dol` is the game's executable. Data files describe characters, maps, items, scripts, and assets; native functions in this file decide how those records are loaded and used. Combat formulas, chapter progression, action availability, resource hashing, and the script interpreter all live here.

## How executable data becomes runtime behavior

  The loader copies initialized code and data sections to their declared addresses, clears BSS, and transfers control to native code. File records become game behavior only when these functions load, resolve, combine, and mutate them.

## Layout

  A DOL header lists several code and initialized-data sections. Each entry supplies a file offset, runtime address, and size. A separate BSS range is allocated as zero-filled memory when the program starts, so runtime tables stored there do not exist as initialized bytes in the file.

  The main code section still links Metrowerks' MetroTRK debug monitor, about 23 KB from `TRKNubMainLoop` (US `0x80225E30`) to `0x8022B6A8`. The layout is the same in every build: PAL starts at `0x8022EB8C` and JP at `0x802205E4`. `__start` only calls `InitMetroTRK` when the boot info at `0x800030E8` reports a debugger (values 2 to 4). TRK's message handlers and single-step, interrupt and register-access code are reached only from TRK itself. So on a retail boot that code never runs, and mods can reuse it as space for new code. The Game Code tab's Battle info window puts its two hook routines at `trk_target_step_out_of_range` (US `0x80229040`). <span class="confidence confidence--confirmed">code</span>

## Addresses and references

  PowerPC instructions operate on 32-bit runtime addresses. Constants and globals are often reached by constructing a base address and then loading from a small offset. Small-data areas provide shorter access to frequently used globals. Function calls use branch-and-link instructions, while tables of function pointers support registries and callbacks.

## Relationship to game data

<div class="table-wrap">
<table><thead><tr><th>Native subsystem</th><th>File-backed input</th></tr></thead><tbody>
    <tr><td>Combat resolution</td><td>Character, class, item, and skill records from <a class="wl" href="../fe8data/">FE8Data.bin</a></td></tr>
    <tr><td>Chapter controller</td><td><a class="wl" href="../event-script/">Scripts</a>, <a class="wl" href="../dispo-format/">deployment</a>, <a class="wl" href="../map-format/">maps</a>, and <a class="wl" href="../message-format/">messages</a></td></tr>
    <tr><td>Script virtual machine</td><td>Compiled <code>.cmb</code> modules and registered native <code>externCall</code> functions</td></tr>
    <tr><td>Named-resource lookup</td><td>Symbolic names such as <code>BGM_*</code> cues and <a class="wl" href="../message-format/">message IDs</a>, resolved through a two-hash bucket table</td></tr>
  </tbody></table>
</div>

## Mapped gameplay surface

  The executable's named gameplay surface now covers map actions, combat exchanges, inventory, skills and status, unit stats, AI flow, chapter/map/event/save support, and large parts of UI/rendering and library code. Among 5,808 named semantic functions, 1,367 functions with parameters have fully named formal parameters and no gameplay candidate currently has partially named or default formal parameters. The remaining readability gaps are mostly inside locals, raw structure dereferences, undefined data references, and large dispatcher functions rather than unknown formal calling contracts.

<div class="table-wrap">
<table><thead><tr><th>Domain</th><th>Named candidates</th><th>Reader-facing examples</th></tr></thead><tbody>
    <tr><td>Battle</td><td>240</td><td>Combat exchanges, forecast stats, strike damage, Steal/Chant/Rescue/Unlock/Shoot action checks</td></tr>
    <tr><td>Chapter / map / event / save</td><td>768</td><td>Script loading, event dispatch, map loading, movement ranges, save-block construction</td></tr>
    <tr><td>Items and inventory</td><td>116</td><td>Item usability, convoy variants, inventory compaction, forging result application</td></tr>
    <tr><td>Skills and status</td><td>87</td><td>Movement-cost grids, active skill slots, terrain defense, skill-driven action availability</td></tr>
    <tr><td>Unit stats</td><td>191</td><td>HP, Strength, Magic, Skill, Speed, Luck, Defense, Resistance, movement, support and actor initialization helpers</td></tr>
    <tr><td>AI flow</td><td>46</td><td>Target scoring, click/target computation, ally-target dispatch</td></tr>
  </tbody></table>
</div>

## Example: named runtime configuration

  The executable does not embed every balance constant directly in its instruction stream. Seven small native accessors resolve a runtime resource named `GameData`, map the current difficulty to one of four columns, and read rows controlling battle EXP, promotion effective level, boss and thief bonuses, transformed-unit growth, and a class critical bonus. This pattern separates native formulas from named configuration loaded at runtime.

  In the NTSC-U executable, the seven accessors occupy `0x801F19A0`&ndash;`0x801F1CE8`. These addresses identify `GFEE01` only. The corresponding PAL functions must be matched by their instructions, callers, and behavior rather than by applying a fixed address difference.

  Function addresses identify one regional build only; the durable documentation is the function's behavior, inputs, and relationships rather than a bare address.

## Lining up the regional executables

  The European (`GFEP01`) and Japanese (`GFEJ01`) executables can be lined up with the North American one (`GFEE01`) function by function. This is not a fixed-offset conversion: the distance between corresponding functions grows through the file, because each build carries different language support. Two passes do it. The first matches each function's machine code after masking the operands that naturally differ between builds (branch targets and data addresses). The second aligns each remaining function against the functions lying between its two matched neighbours, by instruction sequence, and checks every match by its calls: the functions it calls must be the counterparts of the functions the US version calls. <span class="confidence confidence--confirmed">engine</span>

  Of the 9,060 US functions, all but 452 have a European counterpart and all but 546 a Japanese one. What remains is code that differs by release: text and language handling (message-file names per language, date formats, glyph drawing), the European 50/60 Hz video-mode screens, and small graphics helpers too alike to tell apart. A matched pair shows that two functions are the same code; what the code does in the game is established separately. See [Regional Releases](../systems/regional-releases.md) for what differs.

  Library code is not safely described as one broad contiguous block per library. MSL string/vector code, for example, appears in several islands with ordinary game code between them. Candidate library regions should therefore be treated as candidate provenance until code patterns, diagnostic strings, SDK state/register access, or source-level matches confirm an exact identity.

## Recovered object and callback structure

  The executable contains many C++-style object families with vtables. Confirmed classes now include UI widgets, list boxes, popup message windows, map-action panels, sound-voice helpers, gauges, render helpers, and placeholder vtable groups for still-unnamed families. Shared vtable methods remain shared base behavior; a function is not assigned to a derived class merely because it appears in that derived table.

  The controller-input path also uses a real callback table. `pad_set_spec` selects one of several status decoders; spec 0 and spec 1 are distinct 0x174-byte functions rather than raw labels, while specs 2 through 5 share the modern decoder. The callbacks decode button bits, sticks, and triggers into a 12-byte PAD status record; `pad_read` writes the error byte separately.

  Not every retained configuration is actually wired up, though. The executable still carries a complete six-language name table and a script-facing call for reading the current language, but in the shipped US disc that call is hardwired to always return the English selection — nothing at runtime reads or writes an actual language choice, even though the data and the plumbing for one still exist.
