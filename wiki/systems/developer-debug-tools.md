---
id: "developer-debug-tools"
title: "Developer & Debug Tools"
description: "A full set of internal testing menus and helpers, built into the shipped disc but never reachable through normal play"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Structure"]
aliases: ["tellius_archive.html#/developer-debug-tools"]
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/developer-debug-tools.md"
system_entries: ["FE9-SYS-014", "FE9-SYS-371", "FE9-SYS-372", "FE9-SYS-373", "FE9-SYS-374", "FE9-SYS-375", "FE9-SYS-376"]
system_reviewed: ["FE9-SYS-371", "FE9-SYS-372", "FE9-SYS-373", "FE9-SYS-374", "FE9-SYS-376"]
system_reviewed_with_gaps: []
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: []
system_gap_work: []
---
# Developer & Debug Tools

<span id="fe9-sys-014"></span> **FE9-SYS-014 — Crash, assertion, and debug output.** Retail code retains diagnostic strings, assertions, timestamps, author metadata, and console logging used to identify failed loads, invalid state, and development provenance. These diagnostics are evidence about the failing subsystem, not instructions to ignore validation: a missing resource, bad section, impossible script state, or failed platform operation should be traced back to its caller and inputs. Exact output destinations and which assertions remain active depend on build and runtime environment.

*A full set of internal testing menus and helpers, built into the shipped disc but never reachable through normal play*

The shipped disc's executable retains a substantial internal testing and debugging layer that ordinary play never reaches: three complete developer-menu trees and two small ones, plus a scattering of standalone debug helpers wired into normal systems like the tactical map and the portrait renderer. None of this is corrupted or vestigial code — every piece described here is complete, functional, and would run correctly if invoked.

## The developer root menus

  The map pause menu can list five developer roots, each named after a developer. Three are complete menu trees; the other two are small. All of them are built when the game starts:

<div class="table-wrap">
<table><thead><tr><th>Menu</th><th>Covers</th></tr></thead><tbody>
    <tr><td>Kaneko</td><td>The largest: five categories (System, Game, Event, Visualize, Display), a Sound test row and the memory-card file rows. Fully mapped below.</td></tr>
    <tr><td>Akiyama</td><td>Base/storage and tutorial-system testing: filling the party's shared storage with a stock item, testing the base-visit flow and its pre-visit report screen, forcing a specific reinforcement group, unlocking every tutorial message in the game at once, and a small text-rendering test tool (see below)</td></tr>
    <tr><td>Murakami</td><td>Dialog-system testing: standalone two-option and three-option dialog boxes, a location-name display test, a tutorial-dialog test, and a row that turns on every extras flag at once. "Glossary" and "Test" are disabled.</td></tr>
    <tr><td>Yamamoto</td><td>One row, "Face test", which starts a portrait test in the first free portrait slot</td></tr>
    <tr><td>(unnamed)</td><td>A single "None" row with no action</td></tr>
  </tbody></table>
</div>

## How the Kaneko menu is built

  Every row is a small menu object with its own label and action. At start-up one routine fills a single array with the rows of every list, each list followed by its own header, and each category row opens its list by pointing at that header. The lists are separate; a few rows, such as the paged flag editor, are reused by more than one list. <span class="confidence confidence--confirmed">engine</span>

## The Kaneko menu's contents

<div class="table-wrap">
<table><thead><tr><th>List</th><th>Rows</th></tr></thead><tbody>
    <tr><td>Root</td><td>System, Game, Event, Visualize, Display, Sound (sound test), and the memory-card rows: write the save to the host PC, suspend save, copy, delete or write a save slot, check that the save file exists, create or delete the whole save file, and list every slot in the debug console</td></tr>
    <tr><td>System</td><td>Memory usage, file usage, ARAM usage, name-registry usage ("IdentBase"), connect to the host file server, sweep files, free-memory check. In the retail build the host-PC rows only print a message, and ARAM usage does nothing.</td></tr>
    <tr><td>Game</td><td>The unit under the cursor (opens the unit editor below), the building under the cursor (opens two rows that put the map object in its first or last pose), open or close the roof over the cursor, convoy size (selecting it empties the convoy), Game settings, TrickyTerrain, Clear Map (wins the chapter), Unit list, Log (chapter and turn history), Bond (support pairs)</td></tr>
    <tr><td>Game settings</td><td>Difficulty, growth mode (random or fixed), number of playthroughs, chapter, total and on-hand gold, bonus experience, turn number, and who plays the enemy, other and partner phases (see below)</td></tr>
    <tr><td>Event</td><td>Messages (message viewer), script demo (event browser), a console list of every script function, and Edit flags, a 5-page grid of flags with 16 per page</td></tr>
    <tr><td>Visualize</td><td>Movie (one row per movie on the disc; selecting it plays it), mini portraits, monitor position adjustment, portrait-screen mode, dialog backgrounds, the controller guide, skill icons, item icons</td></tr>
    <tr><td>Display</td><td>Twelve switches: process tree, performance, 2D primitives, GPU performance, in-game debug info, safe-frame guide, sound test, battle off, skip-prohibited scenes, camera implementation, guide window, debug console</td></tr>
  </tbody></table>
</div>

  Three more rows (shadow volume, shadow mapping, none) are built, but no list opens them. <span class="confidence confidence--confirmed">engine</span>

## The unit editor

  The unit row opens an editor for the unit under the cursor. Each of its rows opens a list: <span class="confidence confidence--confirmed">engine</span>

- **Items**: the unit's items with their uses (`uses/max`), adjustable.
- **Parameters**: 18 values changed with L/R: level (1–20), experience (0–99), max HP, HP, the seven stats, constitution, move, laguz gauge (0–20), a targeting-weight value ("Hate"), battle count (the [biorhythm](./biorhythm.md) turn counter), biorhythm and weight.
- **Skills**: one row per skill the unit has; selecting a skill removes it, and selecting an "Empty" row opens a browser of all 98 skills to give one.
- **Weapon Level**: one row per weapon type with the rank points (0–251, where 251 is S) and the rank letter.
- **Conditions**: one row per status counter (poison, sleep, silence and the others), each capped at the largest value its storage holds.
- **JID** and **PID**: give the unit a new class or turn it into another character. A new character also takes that character's default class, promoted or unpromoted to match the unit's previous class.
- **Edit Support**: the support level with each partner, raised or lowered on both units at once.
- **General Doping**: raises the unit's stats.
- The remaining rows show the unit's position, equip a laguz unit's natural weapon ("weapon present"), and play the death sequence ("Funeral").

## Who plays each army's phase

  For each of the four armies the game stores who plays its phase: 0 no phase, 1 the player, 2 the computer. Chapter start sets the player army to 1 and the enemy, other and partner armies to 2, and nothing in the retail scripts changes them. On a phase set to 1 the game runs the player's map controls instead of the AI; on a phase set to 0 it skips that army. The Game settings rows switch the enemy, other and partner values. <span class="confidence confidence--confirmed">engine</span> Whether every army's units can be selected and moved on a player-controlled phase has not been tried in game. <span class="confidence confidence--open">open</span>

## A working battle previewer

  A separate development menu entry starts a full battle previewer: a self-contained process that can display attacker/defender/support combat roles, actions, outcomes, and skill/effect names outside of an actual battle sequence — evidently built as a tool for checking combat presentation without having to trigger a real battle.

## Testing text width

  The second root menu's small text-rendering test tool displays the same short sentence three times, each with one word drawn at a different width (`#X3A` squeezed, `#X46` stretched, and unchanged) — a test of the horizontal text scale described in [the dialogue format](../formats/message-format.md). Selecting any of the three rows only displays the sample text; none of them has any further effect.

## Standalone debug helpers outside the menu system

  Beyond the three menu trees, several debug-only helpers are wired directly into normal gameplay systems:

- A tactical-map debug input handler that can select units, center the camera, and mark/unmark enemies on demand — reading the same debug-input state the menus use, but hooked directly into the ordinary map-input loop rather than gated behind a menu.
- A parallel debug harness built into the portrait rendering system, capable of spawning and stepping through a portrait's fade, slide, and zoom animations independently of any actual dialogue scene calling for them.
- A function that dumps the complete contents of every [army list](./armies-allegiance.md) at once — every unit's slot, position, state, and name, grouped by army — clearly meant as a debugging aid for the allegiance system rather than anything a player would ever see.
- Script-level calls that can directly read or write a unit's fields and push/pop entire unit rosters, exposed the same way ordinary script commands are, but intended for test scripts rather than chapter content.

## Why they stay hidden

  Two separate, dormant switches keep the menus out of normal play, and neither is a missing piece of code. The map pause menu walks a zero-terminated list of root menus; the list holds the ordinary pause menu first and then a zero, so the walk stops before it reaches the five developer roots stored behind it. Moving the roots in front of the zero shows all of them. Separately, the start-up process that launches the game controller runs the production title screen, while a complete development title screen (build information, memory-card import and export, the battle previewer, chapter and difficulty selection, and a "Production version" entry that continues to the normal file menu) sits in the executable with nothing pointing at it. <span class="confidence confidence--confirmed">engine</span>

## Example — starting a chapter directly

  The development title's chapter select hands each of its rows to one routine, which is all it takes to start any chapter. The row is a small menu record whose byte `+4` is a position in the [chapter table](./chapters.md) (`ChapterData`), not a chapter number; a position below 0 or past the last record finds nothing. The routine then: <span class="confidence confidence--confirmed">engine + in game</span>

1. resets the whole party as for a new game, with no units and a random game id from 1 to 30 (the same range a trial map uses);
2. keeps the difficulty byte (`0x803307AE` on the US disc: 0 Normal, 1 Hard, 2 Maniac, 3 Easy) as it was;
3. sets the current chapter number to that record's id;
4. tells the game controller to run its chapter-start step next, the same step a won chapter or a loaded save leads to.

  The chapter then loads and plays from its opening. Only the units the chapter itself deploys or recruits are present, since the army is empty. Any record in the table can be started this way, including records added after the retail ones. In the controller's process script, the title screen is one instruction of the boot step (US `0x802833E4`, a "start and wait" on the title script), and the file menu that follows is one call; the routine's effect survives as long as the file menu is not opened over it. After a game over, the controller goes back to its title step.

## Overlay switches

  The Display category's overlays are plain flag bytes read by the main loop every frame: process tree, performance meter, GPU performance meter, in-game debug information, safe-frame guide, sound-test overlay, 2D-primitive overlay, battle-display off and skip-block visualisation. They start at zero and nothing but the menu sets them. <span class="confidence confidence--confirmed">engine</span>

  None of the labels that resemble item, skill, weapon-rank, or status-condition list viewers lead to such a viewer in this build. The complete registered root/menu records instead route those fields through the shared per-unit editor, while `Glossary` and `Test` return an inert menu code. Unlabelled byte fields remain editor-data questions, not evidence of another resource-viewer system.

## FE9-SYS-371 through FE9-SYS-376 — Review boundaries

<span id="fe9-sys-371"></span> **Developer/debug menus.** The executable builds three root trees over shared record windows, complete callbacks, submenus, editors, toggles, and test dialogs. Dormant pause-menu and development-title routing—not missing implementations—keep them out of production play.

<span id="fe9-sys-372"></span> **Internal battle tool.** The battle previewer constructs attacker, defender, support roles, actions, outcomes, skill/effect names, and full battle presentation outside campaign encounter flow. It is a presentation/test harness, not an alternate authoritative campaign combat system.

<span id="fe9-sys-373"></span> **Chapter jump/test flow.** Development title selection indexes `ChapterData`, resets party state, preserves difficulty, assigns the chapter ID, and routes the ordinary controller to chapter start. Bounds and file-menu overwrite hazards are documented above.

<span id="fe9-sys-374"></span> **Resource viewers and harnesses.** The three registered root trees plus standalone hooks cover map markers/overlays, portraits, battle presentation, text width, process/GPU performance, rosters, memory, safe-frame/console/guide views, and scene debug state. Apparent item/skill/rank/status list labels route to field editors or inert callbacks; they do not identify missing viewer implementations in the retail executable.

<span id="fe9-sys-375"></span> **Logging and assertions.** Diagnostic strings and call sites prove logging/assertion infrastructure, but severity, sinks, retail activation, recovery, and representative failure paths are not catalogued. This remains revision-required together with FE9-SYS-014.

<span id="fe9-sys-376"></span> **Build timestamps and author metadata.** Executable/resource provenance strings preserve build dates, tool/author names, and diagnostic context. They are evidence for distinguishing builds and pipelines, not runtime gameplay settings.

## Rules and lifecycle — access and execution

Boot registers menu records and callbacks. A dormant root or development-title path must be made reachable, after which the ordinary menu framework owns focus and invokes the selected helper. Helpers read or mutate live state directly, display results, and return to their parent; chapter jump instead resets and hands off to the production controller. Tools that change units, flags, convoy, or support rank can affect later saves, so testing must isolate state rather than treating every menu as read-only.

## Interactions and limits

FE9-SYS-371–374 and FE9-SYS-376 are reviewed without blocking gaps. The full registered-menu census and standalone hooks close FE9-SYS-374; absent or inert labels are explicitly classified rather than assumed to hide tools. FE9-SYS-375 remains reviewed with gaps in [Crash, Assertions & Diagnostic Output](./crash-assertions-diagnostics.md), its primary article. This page remains the owner of interactive tools.
