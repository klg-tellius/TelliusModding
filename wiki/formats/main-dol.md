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

  A separate readability pass over 1,404 gameplay functions rates 1,078 as good, 316 as usable, 9 as noisy, none as hard to read, and one as a decompile failure. The noisiest known gameplay functions are concentrated in the script interpreter, map loading, movement/search helpers, save construction, and combat-exchange execution.

## Example: named runtime configuration

  The executable does not embed every balance constant directly in its instruction stream. Seven small native accessors resolve a runtime resource named `GameData`, map the current difficulty to one of four columns, and read rows controlling battle EXP, promotion effective level, boss and thief bonuses, transformed-unit growth, and a class critical bonus. This pattern separates native formulas from named configuration loaded at runtime.

  In the NTSC-U executable, the seven accessors occupy `0x801F19A0`&ndash;`0x801F1CE8`. These addresses identify `GFEE01` only. The corresponding PAL functions must be matched by their instructions, callers, and behavior rather than by applying a fixed address difference.

  Function addresses identify one regional build only; the durable documentation is the function's behavior, inputs, and relationships rather than a bare address.

## PAL cross-reference and library boundaries

  The PAL `GFEP01` executable can be lined up with the US `GFEE01` executable by matching each function's machine-code body after masking operands that naturally differ between regional builds. This is not a fixed-offset conversion: the address drift grows through the file because the PAL build carries extra language support. The current cross-reference places 8,746 PAL functions in the US executable with call-graph agreement across 32,204 relationships and identifies 5,046 corresponding data addresses.

  That mapping imported many verified SDK, MSL, and MetroTRK names, corrected earlier disc-drive-versus-audio-chip mislabels, created hundreds of previously missing function entries reached only through pointers, and repaired several bad function extents. It is still only an identity map and boundary aid: a matching decompilation proves byte-level correspondence, not the gameplay meaning of a function.

  Library code is not safely described as one broad contiguous block per library. MSL string/vector code, for example, appears in several islands with ordinary game code between them. Candidate library regions should therefore be treated as candidate provenance until code patterns, diagnostic strings, SDK state/register access, or source-level matches confirm an exact identity.

## Recovered object and callback structure

  The executable contains many C++-style object families with vtables. Confirmed classes now include UI widgets, list boxes, popup message windows, map-action panels, sound-voice helpers, gauges, render helpers, and placeholder vtable groups for still-unnamed families. Shared vtable methods remain shared base behavior; a function is not assigned to a derived class merely because it appears in that derived table.

  The controller-input path also uses a real callback table. `pad_set_spec` selects one of several status decoders; spec 0 and spec 1 are distinct 0x174-byte functions rather than raw labels, while specs 2 through 5 share the modern decoder. The callbacks decode button bits, sticks, and triggers into a 12-byte PAD status record; `pad_read` writes the error byte separately.

  Not every retained configuration is actually wired up, though. The executable still carries a complete six-language name table and a script-facing call for reading the current language, but in the shipped US disc that call is hardwired to always return the English selection — nothing at runtime reads or writes an actual language choice, even though the data and the plumbing for one still exist.
